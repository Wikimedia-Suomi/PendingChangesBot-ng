from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reviews.models import PendingRevision


def blocking_category_hits(revision: PendingRevision, blocking_lookup: dict[str, str]) -> set[str]:
    """Check if revision belongs to any blocking categories."""
    if not blocking_lookup:
        return set()

    categories = list(revision.get_categories())
    page_categories = revision.page.categories or []
    if isinstance(page_categories, list):
        categories.extend(str(category) for category in page_categories if category)

    return {
        blocking_lookup[cat.casefold()] for cat in categories if cat.casefold() in blocking_lookup
    }
