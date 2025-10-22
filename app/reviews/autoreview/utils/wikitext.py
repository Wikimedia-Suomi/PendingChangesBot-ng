from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reviews.models import PendingRevision

logger = logging.getLogger(__name__)


def normalize_wikitext(text: str) -> str:
    """Normalize wikitext for similarity comparison."""
    if not text:
        return ""

    # TODO: check why text is not always suitable for re.
    text=str(text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<ref[^>]*/>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[Category:[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[(File|Image):[^\]]+\]\]", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_additions(parent_wikitext: str, pending_wikitext: str) -> list[str]:
    """Extract text additions from parent to pending revision."""
    if not pending_wikitext:
        return []

    if not parent_wikitext:
        return [pending_wikitext]

    matcher = SequenceMatcher(None, parent_wikitext, pending_wikitext)
    additions = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            added_text = pending_wikitext[j1:j2]
            if added_text.strip():
                additions.append(added_text)

    return additions


def get_parent_wikitext(revision: PendingRevision) -> str:
    """Get parent revision wikitext from local database."""
    cached_parent = getattr(revision, "parent_wikitext", None)
    if isinstance(cached_parent, str) and cached_parent:
        return cached_parent

    parentid = getattr(revision, "parentid", None)
    if not isinstance(parentid, (int, str)) or not parentid:
        return ""

    try:
        from reviews.models import PendingRevision as PR

        parent_revision = PR.objects.get(page=revision.page, revid=parentid)
        return parent_revision.get_wikitext()
    except Exception:
        logger.warning(
            "Parent revision %s not found in local database for revision %s",
            revision.parentid,
            revision.revid,
        )
        return ""
