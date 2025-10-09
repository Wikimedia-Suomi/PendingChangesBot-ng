"""Logic for simulating automatic review decisions for pending revisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import EditorProfile, PendingPage, PendingRevision


@dataclass(frozen=True)
class AutoreviewDecision:
    """Represents the aggregated outcome for a revision."""

    status: str
    label: str
    reason: str


def run_autoreview_for_page(page: PendingPage) -> list[dict]:
    """Run the configured autoreview checks for each pending revision of a page."""

    revisions = list(
        page.revisions.exclude(revid=page.stable_revid)
        .order_by("timestamp", "revid")
    )  # Oldest revision first.
    usernames = {revision.user_name for revision in revisions if revision.user_name}
    profiles = {
        profile.username: profile
        for profile in EditorProfile.objects.filter(
            wiki=page.wiki, username__in=usernames
        )
    }
    configuration = page.wiki.configuration

    auto_groups = _normalize_to_lookup(configuration.auto_approved_groups)
    blocking_categories = _normalize_to_lookup(configuration.blocking_categories)

    results: list[dict] = []
    for revision in revisions:
        profile = profiles.get(revision.user_name or "")
        revision_result = _evaluate_revision(
            revision,
            profile,
            auto_groups=auto_groups,
            blocking_categories=blocking_categories,
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
            }
        )

    return results


def _evaluate_revision(
    revision: PendingRevision,
    profile: EditorProfile | None,
    *,
    auto_groups: dict[str, str],
    blocking_categories: dict[str, str],
) -> dict:
    tests: list[dict] = []

    # Test 1: Bot editors can always be auto-approved.
    if _is_bot_user(revision, profile):
        tests.append(
            {
                "id": "bot-user",
                "title": "Bot user",
                "status": "ok",
                "message": "The edit could be auto-approved because the user is a bot.",
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The user is recognized as a bot.",
            ),
        }

    tests.append(
        {
            "id": "bot-user",
            "title": "Bot user",
            "status": "not_ok",
            "message": "The user is not marked as a bot.",
        }
    )

    # Test 2: Editors in the allow-list can be auto-approved.
    if auto_groups:
        matched_groups = _matched_user_groups(
            revision, profile, allowed_groups=auto_groups
        )
        if matched_groups:
            tests.append(
                {
                    "id": "auto-approved-group",
                    "title": "Auto-approved groups",
                    "status": "ok",
                    "message": "The user belongs to groups: {}.".format(
                        ", ".join(sorted(matched_groups))
                    ),
                }
            )
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="approve",
                    label="Would be auto-approved",
                    reason="The user belongs to groups that are auto-approved.",
                ),
            }

        tests.append(
            {
                "id": "auto-approved-group",
                "title": "Auto-approved groups",
                "status": "not_ok",
                "message": "The user does not belong to auto-approved groups.",
            }
        )
    else:
        if profile and (profile.is_autopatrolled or profile.is_autoreviewed):
            default_rights: list[str] = []
            if profile.is_autopatrolled:
                default_rights.append("Autopatrolled")
            if profile.is_autoreviewed:
                default_rights.append("Autoreviewed")

            tests.append(
                {
                    "id": "auto-approved-group",
                    "title": "Auto-approved groups",
                    "status": "ok",
                    "message": "The user has default auto-approval rights: {}.".format(
                        ", ".join(default_rights)
                    ),
                }
            )
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="approve",
                    label="Would be auto-approved",
                    reason="The user has default rights that allow auto-approval.",
                ),
            }

        tests.append(
            {
                "id": "auto-approved-group",
                "title": "Auto-approved groups",
                "status": "not_ok",
                "message": "The user does not have default auto-approval rights.",
            }
        )

    # Test 3: Blocking categories on the old version prevent automatic approval.
    blocking_hits = _blocking_category_hits(revision, blocking_categories)
    if blocking_hits:
        tests.append(
            {
                "id": "blocking-categories",
                "title": "Blocking categories",
                "status": "fail",
                "message": "The previous version belongs to blocking categories: {}.".format(
                    ", ".join(sorted(blocking_hits))
                ),
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="The previous version belongs to blocking categories.",
            ),
        }

    tests.append(
        {
            "id": "blocking-categories",
            "title": "Blocking categories",
            "status": "ok",
            "message": "The previous version is not in blocking categories.",
        }
    )

    return {
        "tests": tests,
        "decision": AutoreviewDecision(
            status="manual",
            label="Requires human review",
            reason="In dry-run mode the edit would not be approved automatically.",
        ),
    }


def _normalize_to_lookup(values: Iterable[str] | None) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not values:
        return lookup
    for value in values:
        if not value:
            continue
        normalized = str(value).casefold()
        if normalized:
            lookup[normalized] = str(value)
    return lookup


def _is_bot_user(revision: PendingRevision, profile: EditorProfile | None) -> bool:
    """
    Check if a user is a bot or former bot.
    
    Args:
        revision: The pending revision to check
        profile: The editor profile if available
        
    Returns:
        True if the user is a current bot or former bot, False otherwise
    """
    superset = revision.superset_data or {}
    if superset.get("rc_bot"):
        return True
    
    # Check if we have is_bot_edit result (checks both current and former bot status)
    if is_bot_edit(revision):
        return True
    
    return False


def _matched_user_groups(
    revision: PendingRevision,
    profile: EditorProfile | None,
    *,
    allowed_groups: dict[str, str],
) -> set[str]:
    if not allowed_groups:
        return set()

    groups: list[str] = []
    superset = revision.superset_data or {}
    superset_groups = superset.get("user_groups") or []
    if isinstance(superset_groups, list):
        groups.extend(str(group) for group in superset_groups if group)
    if profile and profile.usergroups:
        groups.extend(str(group) for group in profile.usergroups if group)

    matched: set[str] = set()
    for group in groups:
        normalized = group.casefold()
        if normalized in allowed_groups:
            matched.add(allowed_groups[normalized])
    return matched


def _blocking_category_hits(
    revision: PendingRevision, blocking_lookup: dict[str, str]
) -> set[str]:
    if not blocking_lookup:
        return set()

    categories = list(revision.get_categories())
    page_categories = revision.page.categories or []
    if isinstance(page_categories, list):
        categories.extend(str(category) for category in page_categories if category)

    matched: set[str] = set()
    for category in categories:
        normalized = str(category).casefold()
        if normalized in blocking_lookup:
            matched.add(blocking_lookup[normalized])
    return matched


def is_bot_edit(revision: PendingRevision) -> bool:
    """Check if a revision was made by a bot or former bot."""
    if not revision.user_name:
        return False
    try:
        profile = EditorProfile.objects.get(
            wiki=revision.page.wiki,
            username=revision.user_name
        )
        # Check both current bot status and former bot status
        return profile.is_bot or profile.is_former_bot
    except EditorProfile.DoesNotExist:
        return False
