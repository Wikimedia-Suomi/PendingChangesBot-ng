from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from reviewer.utils.is_living_person import is_living_person

if TYPE_CHECKING:
    from reviews.models import PendingRevision

logger = logging.getLogger(__name__)


def is_living_person_article(revision: PendingRevision) -> bool:
    """Check if article is about a living person."""
    try:
        return is_living_person(revision.page.wiki.code, revision.page.title)
    except Exception as e:
        logger.warning(
            f"Error checking if {revision.page.title} is living person: {e}. "
            "Assuming not a living person for safety."
        )
        return False
