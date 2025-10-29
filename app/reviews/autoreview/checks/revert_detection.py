"""
Revert detection check for already-reviewed edits.

This check detects when a pending edit is a revert to previously reviewed content
by matching SHA1 content hashes and checking for revert tags.
"""

import json
import logging
from typing import Any

from django.conf import settings

from ..utils.ores import CheckContext

logger = logging.getLogger(__name__)


def check_revert_detection(context: CheckContext) -> dict[str, Any]:
    """
    Check if a revision is a revert to previously reviewed content.

    Args:
        context: CheckContext containing revision and related data

    Returns:
        Dict with check result including status, message, and metadata
    """
    # Check if revert detection is enabled
    if not getattr(settings, 'ENABLE_REVERT_DETECTION', True):
        return {
            "status": "skip",
            "message": "Revert detection is disabled",
            "metadata": {}
        }
    
    revision = context.revision
    page = revision.page
    
    # Check for revert tags
    revert_tags = {"mw-manual-revert", "mw-reverted", "mw-rollback", "mw-undo"}
    change_tags = getattr(revision, 'change_tags', [])
    
    if not any(tag in change_tags for tag in revert_tags):
        return {
            "status": "skip",
            "message": "No revert tags found",
            "metadata": {"change_tags": change_tags}
        }
    
    # Parse change tag parameters to get reverted revision IDs
    reverted_rev_ids = _parse_revert_params(revision)
    if not reverted_rev_ids:
        return {
            "status": "skip",
            "message": "No reverted revision IDs found in change tags",
            "metadata": {"change_tags": change_tags}
        }
    
    # Check if any of the reverted revisions were previously reviewed
    reviewed_revisions = _find_reviewed_revisions_by_sha1(
        context.client, page, reverted_rev_ids
    )
    
    if reviewed_revisions:
        return {
            "status": "approve",
            "message": f"Revert to previously reviewed content (SHA1: {reviewed_revisions[0]['sha1']})",
            "metadata": {
                "reverted_rev_ids": reverted_rev_ids,
                "reviewed_revisions": reviewed_revisions,
                "revert_tags": [tag for tag in change_tags if tag in revert_tags]
            }
        }
    
    return {
        "status": "block",
        "message": "Revert detected but no previously reviewed content found",
        "metadata": {
            "reverted_rev_ids": reverted_rev_ids,
            "revert_tags": [tag for tag in change_tags if tag in revert_tags]
        }
    }


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
        change_tag_params = getattr(revision, 'change_tag_params', [])
        if not change_tag_params:
            return []
        
        reverted_ids = []
        
        for param_str in change_tag_params:
            try:
                # Parse JSON parameter
                param_data = json.loads(param_str)
                
                # Extract reverted revision IDs
                if 'oldestRevertedRevId' in param_data:
                    reverted_ids.append(param_data['oldestRevertedRevId'])
                if 'newestRevertedRevId' in param_data:
                    reverted_ids.append(param_data['newestRevertedRevId'])
                if 'originalRevisionId' in param_data:
                    reverted_ids.append(param_data['originalRevisionId'])
                    
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse change tag param: {param_str}, error: {e}")
                continue
        
        return list(set(reverted_ids))  # Remove duplicates
        
    except Exception as e:
        logger.error(f"Error parsing revert params for revision {revision.revid}: {e}")
        return []


def _find_reviewed_revisions_by_sha1(
    client, page, reverted_rev_ids: list[int]
) -> list[dict]:
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
        revid_list = ",".join(str(int(revid)) for revid in reverted_rev_ids)

        # ids are validated as integers above; safe to embed
        sql_query = (
            "SELECT \n"
            "    MAX(rev_id) as max_reviewable_rev_id_by_sha1, \n"
            "    rev_page, \n"
            "    content_sha1, \n"
            "    MAX(fr_rev_id) as max_old_reviewed_id \n"
            "FROM \n"
            "    revision \n"
            "    LEFT JOIN flaggedrevs ON rev_id=fr_rev_id\n"
            "    JOIN slots ON slot_revision_id=rev_id\n"
            "    JOIN content ON slot_content_id=content_id\n"
            "WHERE \n"
            f"    rev_id IN ({revid_list})"  # noqa: S608
            "\nGROUP BY \n"
            "    rev_page, content_sha1\n"
        )
        
        # Execute query using SupersetQuery
        from pywikibot.data.superset import SupersetQuery
        superset = SupersetQuery(site=client.site)
        results = superset.query(sql_query)
        
        # Filter results where content was previously reviewed
        reviewed_revisions = []
        for result in results:
            if result.get('max_old_reviewed_id') is not None:
                reviewed_revisions.append({
                    'sha1': result.get('content_sha1'),
                    'max_reviewed_id': result.get('max_old_reviewed_id'),
                    'max_reviewable_id': result.get('max_reviewable_rev_id_by_sha1'),
                    'page_id': result.get('rev_page')
                })
        
        return reviewed_revisions
        
    except Exception as e:
        logger.error(f"Error finding reviewed revisions for page {page.pageid}: {e}")
        return []
