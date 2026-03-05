from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .checks import get_enabled_checks
from .context import CheckContext
from .decision import AutoreviewDecision
from .utils.redirect import get_redirect_aliases
from .utils.user import normalize_to_lookup

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from reviews.models import EditorProfile, PendingPage, PendingRevision
    from reviews.services import WikiClient


def run_checks_pipeline(
    revision: PendingRevision,
    client: WikiClient,
    profile: EditorProfile | None,
    *,
    auto_groups: dict[str, str],
    blocking_categories: dict[str, str],
    redirect_aliases: list[str],
) -> dict:
    """Run all enabled checks in order, stopping at blocking/approving checks."""
    pipeline_start_time = time.perf_counter()

    context = CheckContext(
        revision=revision,
        client=client,
        profile=profile,
        auto_groups=auto_groups,
        blocking_categories=blocking_categories,
        redirect_aliases=redirect_aliases,
    )

    configuration = revision.page.wiki.configuration
    checks_to_run = get_enabled_checks(configuration)

    tests = []
    for check_info in checks_to_run:
        check_start_time = time.perf_counter()
        result = check_info["function"](context)
        duration_ms = (time.perf_counter() - check_start_time) * 1000

        tests.append(
            {
                "id": result.check_id,
                "title": result.check_title,
                "status": result.status,
                "message": result.message,
                "duration_ms": duration_ms,
            }
        )

        if result.should_stop:
            total_duration_ms = (time.perf_counter() - pipeline_start_time) * 1000
            return {
                "tests": tests,
                "decision": result.decision,
                "total_duration_ms": total_duration_ms,
            }

        if (
            result.check_id == "article-to-redirect-conversion"
            and result.status == "ok"
            and profile
            and profile.is_autopatrolled
        ):
            total_duration_ms = (time.perf_counter() - pipeline_start_time) * 1000
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="approve",
                    label="Would be auto-approved",
                    reason="The user has autopatrol rights that allow auto-approval.",
                ),
                "total_duration_ms": total_duration_ms,
            }

    total_duration_ms = (time.perf_counter() - pipeline_start_time) * 1000
    return {
        "tests": tests,
        "decision": AutoreviewDecision(
            status="manual",
            label="Requires human review",
            reason="In dry-run mode the edit would not be approved automatically.",
        ),
        "total_duration_ms": total_duration_ms,
    }


def run_autoreview_for_page(
    page: PendingPage, log_activity: bool = True, dry_run: bool = True
) -> list[dict]:
    """Run the configured autoreview checks for each pending revision of a page.

    Args:
        page: The page whose pending revisions should be reviewed.
        log_activity: Whether to log decisions to BotActivity.
        dry_run: When *False* and a revision is approved, actually call the
            FlaggedRevs ``action=review`` API.  Defaults to *True* (no real
            reviews are submitted).
    """
    from bot_control.models import BotActivity

    from reviews.models import EditorProfile
    from reviews.services import FlaggedRevsClient, WikiClient

    revisions = list(page.revisions.exclude(revid=page.stable_revid).order_by("timestamp", "revid"))
    if not revisions:
        return []

    usernames = {rev.user_name for rev in revisions if rev.user_name}
    profiles = (
        {
            profile.username: profile
            for profile in EditorProfile.objects.filter(wiki=page.wiki, username__in=usernames)
        }
        if usernames
        else {}
    )

    configuration = page.wiki.configuration
    auto_groups = normalize_to_lookup(configuration.auto_approved_groups)
    blocking_categories = normalize_to_lookup(configuration.blocking_categories)
    redirect_aliases = get_redirect_aliases(page.wiki)
    client = WikiClient(page.wiki)

    results = []
    for revision in revisions:
        profile = profiles.get(revision.user_name or "")
        revision_result = run_checks_pipeline(
            revision,
            client,
            profile,
            auto_groups=auto_groups,
            blocking_categories=blocking_categories,
            redirect_aliases=redirect_aliases,
        )
        decision_status = revision_result["decision"].status

        # If the decision is to approve and we are NOT in dry-run mode,
        # actually submit the review via the FlaggedRevs API.
        review_submitted = False
        review_message = ""
        if decision_status == "approve" and not dry_run:
            try:
                fr_client = FlaggedRevsClient(client.site)
                review_result = fr_client.review_revision(
                    revid=revision.revid,
                    comment="Auto-approved by PendingChangesBot",
                )
                review_submitted = review_result.success
                review_message = review_result.message
                if not review_result.success:
                    logger.warning(
                        "FlaggedRevs review failed for rev %s: %s",
                        revision.revid,
                        review_result.message,
                    )
            except Exception:
                logger.exception(
                    "Failed to submit FlaggedRevs review for rev %s",
                    revision.revid,
                )

        result_data = {
            "revid": revision.revid,
            "tests": revision_result["tests"],
            "decision": {
                "status": decision_status,
                "label": revision_result["decision"].label,
                "reason": revision_result["decision"].reason,
            },
            "total_duration_ms": revision_result["total_duration_ms"],
            "mode": "dry-run" if dry_run else "live",
            "review_submitted": review_submitted,
            "review_message": review_message,
        }
        results.append(result_data)

        # Log activity for statistics tracking
        if log_activity:
            try:
                # Find the determining check (the one that made the decision)
                determining_check = ""
                for test in revision_result["tests"]:
                    if test.get("decision"):
                        determining_check = test.get("id", "")
                        break

                BotActivity.log_activity(
                    wiki_code=page.wiki.code,
                    page_id=page.pageid,
                    page_title=page.title,
                    revision_id=revision.revid,
                    user_name=revision.user_name or "",
                    decision=decision_status,
                    decision_label=revision_result["decision"].label,
                    decision_reason=revision_result["decision"].reason,
                    determining_check=determining_check,
                    total_checks_run=len(revision_result["tests"]),
                    execution_time_ms=revision_result["total_duration_ms"],
                    is_dry_run=dry_run,
                )
            except Exception:  # noqa: S110
                # Don't let logging failures break the autoreview
                pass

    return results


def review_single_revision(
    revid: int,
    wiki_code: str,
    *,
    log_activity: bool = True,
    dry_run: bool = True,
) -> dict:
    """Review a single revision by its revision ID.

    This is the main entrypoint for reviewing one specific revision.  It
    loads the revision from the database, runs the full check pipeline,
    optionally submits the review via the FlaggedRevs API, and logs the
    result to :class:`~bot_control.models.BotActivity`.

    Args:
        revid: The MediaWiki revision ID to review.
        wiki_code: The wiki code (e.g. ``"fi"``) that owns the revision.
        log_activity: Whether to write a BotActivity record.
        dry_run: When *False* and the decision is ``"approve"``, actually
            submit the review.  Defaults to *True* (no real reviews).

    Returns:
        A dict with keys ``revid``, ``tests``, ``decision``, ``mode``,
        ``review_submitted``, ``review_message``, and
        ``total_duration_ms``.

    Raises:
        ValueError: If the revision or its wiki cannot be found in the DB.
    """
    from bot_control.models import BotActivity

    from reviews.models import EditorProfile, PendingRevision, Wiki
    from reviews.services import FlaggedRevsClient, WikiClient

    try:
        wiki = Wiki.objects.get(code=wiki_code)
    except Wiki.DoesNotExist:
        raise ValueError(f"Wiki with code '{wiki_code}' not found.")

    revision = (
        PendingRevision.objects.select_related("page", "page__wiki")
        .filter(page__wiki=wiki, revid=revid)
        .first()
    )
    if revision is None:
        raise ValueError(f"Revision {revid} not found in the database for wiki '{wiki_code}'.")

    page = revision.page
    profile = (
        EditorProfile.objects.filter(wiki=wiki, username=revision.user_name).first()
        if revision.user_name
        else None
    )

    configuration = wiki.configuration
    auto_groups = normalize_to_lookup(configuration.auto_approved_groups)
    blocking_categories = normalize_to_lookup(configuration.blocking_categories)
    redirect_aliases = get_redirect_aliases(wiki)
    client = WikiClient(wiki)

    revision_result = run_checks_pipeline(
        revision,
        client,
        profile,
        auto_groups=auto_groups,
        blocking_categories=blocking_categories,
        redirect_aliases=redirect_aliases,
    )
    decision_status = revision_result["decision"].status

    # Submit review if approved and not dry-run
    review_submitted = False
    review_message = ""
    if decision_status == "approve" and not dry_run:
        try:
            fr_client = FlaggedRevsClient(client.site)
            review_result = fr_client.review_revision(
                revid=revision.revid,
                comment="Auto-approved by PendingChangesBot",
            )
            review_submitted = review_result.success
            review_message = review_result.message
            if not review_result.success:
                logger.warning(
                    "FlaggedRevs review failed for rev %s: %s",
                    revision.revid,
                    review_result.message,
                )
        except Exception:
            logger.exception(
                "Failed to submit FlaggedRevs review for rev %s",
                revision.revid,
            )

    result_data = {
        "revid": revision.revid,
        "tests": revision_result["tests"],
        "decision": {
            "status": decision_status,
            "label": revision_result["decision"].label,
            "reason": revision_result["decision"].reason,
        },
        "total_duration_ms": revision_result["total_duration_ms"],
        "mode": "dry-run" if dry_run else "live",
        "review_submitted": review_submitted,
        "review_message": review_message,
    }

    if log_activity:
        try:
            determining_check = ""
            for test in revision_result["tests"]:
                if test.get("decision"):
                    determining_check = test.get("id", "")
                    break

            BotActivity.log_activity(
                wiki_code=wiki.code,
                page_id=page.pageid,
                page_title=page.title,
                revision_id=revision.revid,
                user_name=revision.user_name or "",
                decision=decision_status,
                decision_label=revision_result["decision"].label,
                decision_reason=revision_result["decision"].reason,
                determining_check=determining_check,
                total_checks_run=len(revision_result["tests"]),
                execution_time_ms=revision_result["total_duration_ms"],
                is_dry_run=dry_run,
            )
        except Exception:  # noqa: S110
            pass

    return result_data
