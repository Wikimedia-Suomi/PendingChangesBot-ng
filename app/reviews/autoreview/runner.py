from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .checks import get_enabled_checks
from .context import CheckContext
from .decision import AutoreviewDecision
from .utils.redirect import get_redirect_aliases
from .utils.user import normalize_to_lookup

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


def run_autoreview_for_page(page: PendingPage) -> list[dict]:
    """Run the configured autoreview checks for each pending revision of a page."""
    from reviews.models import EditorProfile
    from reviews.services import WikiClient

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
        results.append(
            {
                "revid": revision.revid,
                "tests": revision_result["tests"],
                "decision": {
                    "status": revision_result["decision"].status,
                    "label": revision_result["decision"].label,
                    "reason": revision_result["decision"].reason,
                },
                "total_duration_ms": revision_result["total_duration_ms"],
            }
        )

    return results
