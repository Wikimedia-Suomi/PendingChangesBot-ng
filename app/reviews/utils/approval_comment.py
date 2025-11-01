"""
Core approval comment generation logic.
This module provides functions for generating consolidated approval comments
from autoreview results, with smart grouping and formatting.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum comment length to avoid truncation
MAX_COMMENT_LENGTH = 500


def generate_approval_comment(
    autoreview_results: list[dict], comment_prefix: str = ""
) -> tuple[Optional[int], str]:
    """Generate a consolidated approval comment and select highest approvable revid.

    Args:
        autoreview_results: List of result dicts from run_autoreview_for_page(). Each item typically
            contains keys like 'revid' and 'decision' (with fields such as 'status' and 'reason').
        comment_prefix: Optional string prefixed to the generated comment for clarity/auditing.

    Returns:
        (rev_id, comment) where:
            rev_id: Optional[int] – Highest approvable revision id, or None if none are approvable.
            comment: str – Consolidated comment explaining approvals (possibly prefixed), or a
                message indicating that nothing can be approved.
    """
    try:
        # Filter for approved revisions only
        approved_revisions = [
            result
            for result in autoreview_results
            if result.get("decision", {}).get("status") == "approve"
        ]

        if not approved_revisions:
            return None, f"{comment_prefix}No revisions can be approved".strip()

        # Find the highest (latest) revision ID that can be approved
        max_revid = max(result["revid"] for result in approved_revisions)

        # Group revisions by their approval reason to create concise comments
        reason_groups = {}
        for result in approved_revisions:
            decision = result.get("decision", {})
            reason_raw = decision.get("reason", "no reason provided")
            reason = clean_approval_reason(reason_raw)
            if reason not in reason_groups:
                reason_groups[reason] = []
            reason_groups[reason].append(result["revid"])

        # Generate consolidated comment
        comment_parts = []
        for reason, rev_ids in reason_groups.items():
            if len(rev_ids) == 1:
                comment_parts.append(f"rev_id {rev_ids[0]} approved because {reason}")
            else:
                # Group revisions with same reason (sorted for consistency)
                rev_ids_sorted = sorted(rev_ids)
                comment_parts.append(
                    f"rev_id {', '.join(map(str, rev_ids_sorted))} approved because {reason}"
                )

        comment = ", ".join(comment_parts)

        # Add prefix if provided
        if comment_prefix:
            comment = f"{comment_prefix} {comment}"

        # Validate and truncate if necessary
        comment = validate_comment_length(comment)

        logger.info(
            f"Generated approval comment for {len(approved_revisions)} "
            f"revisions, max_revid: {max_revid}"
        )
        return max_revid, comment

    except Exception as e:
        logger.error(f"Error generating approval comment: {e}")
        return None, f"{comment_prefix}Error generating approval comment".strip()


def clean_approval_reason(reason: str) -> str:
    """
    Clean and normalize approval reasons for consistent formatting.

    Args:
        reason: Raw approval reason from autoreview decision

    Returns:
        Cleaned and normalized reason string
    """
    if not reason:
        return "unknown reason"

    # Clean up common variations
    cleaned = reason.strip()

    # Normalize common phrases
    replacements = {
        "user was a bot": "user was bot",
        "user was bot": "user was bot",
        "no content change in last article": "no content change",
        "user was auto-reviewed": "user was autoreviewed",
        "user was autoreviewed": "user was autoreviewed",
        "ORES score": "ORES score",
    }

    for original, normalized in replacements.items():
        if original.lower() in cleaned.lower():
            cleaned = cleaned.replace(original, normalized)
            break

    return cleaned


def validate_comment_length(comment: str) -> str:
    """
    Validate comment length and truncate if necessary.

    Args:
        comment: Comment string to validate

    Returns:
        Validated comment string (truncated if necessary)
    """
    if len(comment) <= MAX_COMMENT_LENGTH:
        return comment

    # Truncate and add indicator
    truncated = comment[: MAX_COMMENT_LENGTH - 20] + "... (truncated)"
    logger.warning(f"Comment truncated from {len(comment)} to {len(truncated)} characters")
    return truncated


def group_consecutive_revisions(rev_ids: list[int]) -> list[list[int]]:
    """
    Group consecutive revision IDs together.

    Args:
        rev_ids: List of revision IDs

    Returns:
        List of groups, where each group contains consecutive revision IDs
    """
    if not rev_ids:
        return []

    sorted_ids = sorted(rev_ids)
    groups = []
    current_group = [sorted_ids[0]]

    for i in range(1, len(sorted_ids)):
        if sorted_ids[i] == sorted_ids[i - 1] + 1:
            # Consecutive revision
            current_group.append(sorted_ids[i])
        else:
            # Non-consecutive, start new group
            groups.append(current_group)
            current_group = [sorted_ids[i]]

    groups.append(current_group)
    return groups


def format_revision_group(rev_ids: list[int]) -> str:
    """
    Format a group of revision IDs for display.

    Args:
        rev_ids: List of revision IDs

    Returns:
        Formatted string representation
    """
    if not rev_ids:
        return ""

    if len(rev_ids) == 1:
        return str(rev_ids[0])

    # Check if they're consecutive
    if len(rev_ids) == 2 and rev_ids[1] == rev_ids[0] + 1:
        return f"{rev_ids[0]}, {rev_ids[1]}"

    # For more than 2, check if all consecutive
    sorted_ids = sorted(rev_ids)
    if all(sorted_ids[i] == sorted_ids[i - 1] + 1 for i in range(1, len(sorted_ids))):
        return f"{sorted_ids[0]}-{sorted_ids[-1]}"

    # Not all consecutive, list them all
    return ", ".join(map(str, sorted_ids))
