from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reviews.models import EditorProfile, PendingRevision


def is_bot_user(revision: PendingRevision, profile: EditorProfile | None) -> bool:
    """Check if a user is a bot or former bot."""
    superset = revision.superset_data or {}
    if superset.get("rc_bot"):
        return True

    if profile and (profile.is_bot or profile.is_former_bot):
        return True

    return False


def normalize_to_lookup(values: Iterable[str] | None) -> dict[str, str]:
    """Convert list of strings to case-folded lookup dictionary."""
    if not values:
        return {}
    return {str(v).casefold(): str(v) for v in values if v}


def matched_user_groups(
    revision: PendingRevision,
    profile: EditorProfile | None,
    *,
    allowed_groups: dict[str, str],
) -> set[str]:
    """Check which allowed groups the user belongs to."""
    if not allowed_groups:
        return set()

    groups: list[str] = []
    superset = revision.superset_data or {}
    superset_groups = superset.get("user_groups") or []
    if isinstance(superset_groups, list):
        groups.extend(str(group) for group in superset_groups if group)
    if profile and profile.usergroups:
        groups.extend(str(group) for group in profile.usergroups if group)

    return {allowed_groups[g.casefold()] for g in groups if g.casefold() in allowed_groups}
