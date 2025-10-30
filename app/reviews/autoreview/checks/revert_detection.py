"""
Revert detection check for already-reviewed edits.

This check detects when a pending edit is a revert to previously reviewed content
by matching SHA1 content hashes and checking for revert tags.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from django.conf import settings

from ..base import CheckResult
from ..decision import AutoreviewDecision

if TYPE_CHECKING:
    from ..context import CheckContext

logger = logging.getLogger(__name__)


def check_revert_detection(context: CheckContext) -> CheckResult:
    """
    Check if a revision is a revert to previously reviewed content.

    Args:
        context: CheckContext containing revision and related data

    Returns:
        CheckResult with status, message, and decision
    """
    # Check if revert detection is enabled
    if not getattr(settings, "ENABLE_REVERT_DETECTION", True):
        return CheckResult(
            check_id="revert-detection",
            check_title="Revert to reviewed version",
            status="skip",
            message="Revert detection is disabled",
            should_stop=False,
        )

    revision = context.revision
    page = revision.page

    # Check for revert tags
    revert_tags = {"mw-manual-revert", "mw-reverted", "mw-rollback", "mw-undo"}
    change_tags = getattr(revision, "change_tags", []) or []

    if not any(tag in change_tags for tag in revert_tags):
        return CheckResult(
            check_id="revert-detection",
            check_title="Revert to reviewed version",
            status="skip",
            message="No revert tags found",
            should_stop=False,
        )

    # Parse change tag parameters to get reverted revision IDs
    reverted_rev_ids = _parse_revert_params(revision)
    if not reverted_rev_ids:
        return CheckResult(
            check_id="revert-detection",
            check_title="Revert to reviewed version",
            status="skip",
            message="No reverted revision IDs found in change tags",
            should_stop=False,
        )

    # Check if any of the reverted revisions were previously reviewed
    reviewed_revisions = _find_reviewed_revisions_by_sha1(context.client, page, reverted_rev_ids)

    if reviewed_revisions:
        sha1 = reviewed_revisions[0]["sha1"]
        return CheckResult(
            check_id="revert-detection",
            check_title="Revert to reviewed version",
            status="ok",
            message=f"Revert to previously reviewed content (SHA1: {sha1})",
            decision=AutoreviewDecision(
                status="approve",
                label="Auto-approved (revert to reviewed)",
                reason="This edit reverts to content that was previously reviewed and approved.",
            ),
            should_stop=False,
        )

    return CheckResult(
        check_id="revert-detection",
        check_title="Revert to reviewed version",
        status="not_ok",
        message="Revert detected but no previously reviewed content found",
        should_stop=False,
    )


def _parse_revert_params(revision) -> list[int]:
    """
    Parse change tag parameters to extract reverted revision IDs.

    Args:
        revision: PendingRevision object

    Returns:
        List of reverted revision IDs
    """
    try:
        # Get change tag parameters from revision
        change_tag_params = getattr(revision, "change_tag_params", [])
        if not change_tag_params:
            return []

        reverted_ids = []

        for param_str in change_tag_params:
            try:
                # Parse JSON parameter
                param_data = json.loads(param_str)

                # Extract reverted revision IDs
                if "oldestRevertedRevId" in param_data:
                    reverted_ids.append(param_data["oldestRevertedRevId"])
                if "newestRevertedRevId" in param_data:
                    reverted_ids.append(param_data["newestRevertedRevId"])
                if "originalRevisionId" in param_data:
                    reverted_ids.append(param_data["originalRevisionId"])

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse change tag param: {param_str}, error: {e}")
                continue

        return list(set(reverted_ids))  # Remove duplicates

    except Exception as e:
        logger.error(f"Error parsing revert params for revision {revision.revid}: {e}")
        return []


def _find_reviewed_revisions_by_sha1(client, page, reverted_rev_ids: list[int]) -> list[dict]:
    """
    Find previously reviewed revisions by SHA1 content hash.

    This implements @zache-fi's suggested Superset approach:
    1. Query MediaWiki database for older reviewed versions by SHA1
    2. Check if any of the reverted revisions were previously reviewed

    Args:
        client: WikiClient instance
        page: PendingPage object
        reverted_rev_ids: List of reverted revision IDs

    Returns:
        List of reviewed revision data
    """
    if not reverted_rev_ids:
        return []

    try:
        # Execute Superset query to find reviewed revisions by SHA1
        # This follows @zache-fi's suggested SQL approach
        revid_list = ",".join(str(revid) for revid in reverted_rev_ids)

        sql_query = f"""
        SELECT
            MAX(rev_id) as max_reviewable_rev_id_by_sha1,
            rev_page,
            content_sha1,
            MAX(fr_rev_id) as max_old_reviewed_id
        FROM
            revision
            LEFT JOIN flaggedrevs ON rev_id=fr_rev_id
            JOIN slots ON slot_revision_id=rev_id
            JOIN content ON slot_content_id=content_id
        WHERE
            rev_id IN ({revid_list})
        GROUP BY
            rev_page, content_sha1
        """

        # Execute query using SupersetQuery
        from pywikibot.data.superset import SupersetQuery

        superset = SupersetQuery(site=client.site)
        results = superset.query(sql_query)

        # Filter results where content was previously reviewed
        reviewed_revisions = []
        for result in results:
            if result.get("max_old_reviewed_id") is not None:
                reviewed_revisions.append(
                    {
                        "sha1": result.get("content_sha1"),
                        "max_reviewed_id": result.get("max_old_reviewed_id"),
                        "max_reviewable_id": result.get("max_reviewable_rev_id_by_sha1"),
                        "page_id": result.get("rev_page"),
                    }
                )

        return reviewed_revisions

    except Exception as e:
        logger.error(f"Error finding reviewed revisions for page {page.pageid}: {e}")
        return []
