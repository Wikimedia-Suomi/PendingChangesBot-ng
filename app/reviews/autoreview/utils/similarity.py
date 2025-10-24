from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from .wikitext import extract_additions, get_parent_wikitext, normalize_wikitext

if TYPE_CHECKING:
    from reviews.models import PendingRevision

logger = logging.getLogger(__name__)


def is_addition_superseded(
    revision: PendingRevision,
    current_stable_wikitext: str,
    threshold: float,
) -> dict[str, object]:
    """Check if text additions from a pending revision have been superseded."""
    from reviews.models import PendingRevision as PR

    # If current_stable_wikitext is provided, use it; otherwise fetch the latest
    if current_stable_wikitext:
        latest_wikitext = current_stable_wikitext
    else:
        latest_revision = PR.objects.filter(page=revision.page).order_by("-revid").first()

        if not latest_revision or latest_revision.revid == revision.revid:
            return {
                "is_superseded": False,
                "message": "No stable revision available for comparison.",
            }

        latest_wikitext = latest_revision.get_wikitext()
        if not latest_wikitext:
            return {
                "is_superseded": False,
                "message": "Stable revision wikitext is empty.",
            }

    parent_wikitext = get_parent_wikitext(revision)

    pending_wikitext_getter = getattr(revision, "get_wikitext", None)
    if callable(pending_wikitext_getter):
        pending_wikitext = pending_wikitext_getter()
    else:
        pending_wikitext = getattr(revision, "wikitext", "")

    if not isinstance(pending_wikitext, str):
        pending_wikitext = (
            getattr(revision, "wikitext", "")
            if isinstance(getattr(revision, "wikitext", ""), str)
            else str(pending_wikitext or "")
        )

    if not pending_wikitext:
        return {
            "is_superseded": False,
            "message": "Pending revision has no wikitext to compare.",
        }

    additions = extract_additions(parent_wikitext, pending_wikitext)
    if not additions:
        return {
            "is_superseded": False,
            "message": "No additions detected in pending revision.",
        }

    normalized_latest = normalize_wikitext(latest_wikitext)
    if not normalized_latest:
        return {
            "is_superseded": False,
            "message": "Unable to normalize latest stable wikitext.",
        }

    for addition in additions:
        normalized_addition = normalize_wikitext(addition)

        matcher = SequenceMatcher(None, normalized_addition, normalized_latest)
        significant_match_length = sum(
            block.size for block in matcher.get_matching_blocks()[:-1] if block.size >= 4
        )

        if len(normalized_addition) > 0:
            match_ratio = significant_match_length / len(normalized_addition)
            if match_ratio < threshold:
                logger.info(
                    (
                        "Revision %s appears superseded: addition has %.2f%% match "
                        "(< %.2f%% threshold)"
                    ),
                    revision.revid,
                    match_ratio * 100,
                    threshold * 100,
                )
                return {
                    "is_superseded": True,
                    "message": ("Addition appears superseded: similarity below threshold."),
                }

    return {
        "is_superseded": False,
        "message": "Additions still present or insufficient similarity drop detected.",
    }
