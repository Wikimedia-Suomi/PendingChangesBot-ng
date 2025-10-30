"""
High-level approval processing functions.
This module provides functions for processing autoreview results and managing
the approval workflow, including batch processing and statistics.
"""

import logging
from collections import Counter
from datetime import datetime
from typing import Dict, List

from .approval_comment import generate_approval_comment

logger = logging.getLogger(__name__)


def process_and_approve_revisions(
    autoreview_results: List[Dict], comment_prefix: str = "", dry_run: bool = True
) -> Dict:
    """
    Process autoreview results and approve revisions with consolidated comment.

    Args:
        autoreview_results: Results from run_autoreview_for_page()
        comment_prefix: Optional prefix for approval comment
        dry_run: If True, only preview without making actual approvals

    Returns:
        Dictionary with processing results including:
        - success: Boolean indicating if processing was successful
        - max_revid: Highest revision ID that can be approved
        - comment: Generated approval comment
        - approved_count: Number of revisions that can be approved
        - total_count: Total number of revisions processed
        - dry_run: Whether this was a dry run
        - timestamp: When processing occurred
    """
    try:
        if not autoreview_results:
            return {
                "success": False,
                "max_revid": None,
                "comment": f"{comment_prefix}No revisions provided".strip(),
                "approved_count": 0,
                "total_count": 0,
                "dry_run": dry_run,
                "timestamp": datetime.now().isoformat(),
                "message": "No revisions provided",
            }

        total_count = len(autoreview_results)
        approved_count = sum(
            1 for r in autoreview_results if r.get("decision", {}).get("status") == "approve"
        )

        if approved_count == 0:
            return {
                "success": False,
                "max_revid": None,
                "comment": f"{comment_prefix}No revisions can be approved".strip(),
                "approved_count": 0,
                "total_count": total_count,
                "dry_run": dry_run,
                "timestamp": datetime.now().isoformat(),
                "message": "No revisions can be approved",
            }

        # Generate approval comment
        max_revid, comment = generate_approval_comment(autoreview_results, comment_prefix)

        result = {
            "success": True,
            "max_revid": max_revid,
            "comment": comment,
            "approved_count": approved_count,
            "total_count": total_count,
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat(),
            "message": f"Successfully processed {approved_count}/{total_count} revisions",
        }

        if not dry_run:
            # TODO: Implement actual approval logic here
            # This would call the actual approval API
            result["message"] += " (approval action performed)"
            logger.info(f"Approved revision {max_revid} with comment: {comment}")
        else:
            result["message"] += " (dry run - no actual approval performed)"
            logger.info(f"Dry run: Would approve revision {max_revid} with comment: {comment}")

        return result

    except Exception as e:
        logger.error(f"Error processing and approving revisions: {e}")
        return {
            "success": False,
            "max_revid": None,
            "comment": f"{comment_prefix}Error processing revisions".strip(),
            "approved_count": 0,
            "total_count": len(autoreview_results),
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat(),
            "message": f"Error: {str(e)}",
        }


def preview_approval_comment(autoreview_results: List[Dict], comment_prefix: str = "") -> Dict:
    """
    Preview approval comment without making any changes.

    Args:
        autoreview_results: Results from run_autoreview_for_page()
        comment_prefix: Optional prefix for approval comment

    Returns:
        Dictionary with preview information
    """
    return process_and_approve_revisions(autoreview_results, comment_prefix, dry_run=True)


def batch_process_pages(
    pages_data: List[Dict], comment_prefix: str = "", dry_run: bool = True
) -> Dict:
    """
    Process multiple pages and their autoreview results in batch.

    Args:
        pages_data: List of dictionaries containing page info and autoreview results
        comment_prefix: Optional prefix for approval comments
        dry_run: If True, only preview without making actual approvals

    Returns:
        Dictionary with batch processing results
    """
    try:
        results = []
        total_pages = len(pages_data)
        successful_pages = 0

        for page_data in pages_data:
            page_id = page_data.get("pageid", "unknown")
            autoreview_results = page_data.get("results", [])

            try:
                result = process_and_approve_revisions(autoreview_results, comment_prefix, dry_run)
                result["pageid"] = page_id
                results.append(result)

                if result["success"]:
                    successful_pages += 1

            except Exception as e:
                logger.error(f"Error processing page {page_id}: {e}")
                results.append(
                    {
                        "success": False,
                        "pageid": page_id,
                        "message": f"Error processing page: {str(e)}",
                        "dry_run": dry_run,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        return {
            "success": successful_pages > 0,
            "total_pages": total_pages,
            "successful_pages": successful_pages,
            "failed_pages": total_pages - successful_pages,
            "results": results,
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat(),
            "message": f"Processed {successful_pages}/{total_pages} pages successfully",
        }

    except Exception as e:
        logger.error(f"Error in batch processing: {e}")
        return {
            "success": False,
            "total_pages": len(pages_data),
            "successful_pages": 0,
            "failed_pages": len(pages_data),
            "results": [],
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat(),
            "message": f"Batch processing error: {str(e)}",
        }


def get_approval_statistics(autoreview_results: List[Dict]) -> Dict:
    """
    Get comprehensive statistics about approval decisions.

    Args:
        autoreview_results: Results from run_autoreview_for_page()

    Returns:
        Dictionary with approval statistics
    """
    try:
        total_revisions = len(autoreview_results)

        # Count by status and reason using Counter
        statuses = [r.get("decision", {}).get("status", "unknown") for r in autoreview_results]
        reasons = [r.get("decision", {}).get("reason", "unknown") for r in autoreview_results]
        status_counts = dict(Counter(statuses))
        reason_counts = dict(Counter(reasons))

        # Get approval-specific stats
        approved_revisions = [
            r for r in autoreview_results if r.get("decision", {}).get("status") == "approve"
        ]
        approved_count = len(approved_revisions)

        # Find revision ID range
        rev_ids = [r["revid"] for r in autoreview_results]
        min_revid = min(rev_ids) if rev_ids else None
        max_revid = max(rev_ids) if rev_ids else None

        # Find highest approvable revision
        approvable_rev_ids = [r["revid"] for r in approved_revisions]
        max_approvable_revid = max(approvable_rev_ids) if approvable_rev_ids else None

        return {
            "total_revisions": total_revisions,
            "approved_count": approved_count,
            "blocked_count": status_counts.get("blocked", 0),
            "manual_count": status_counts.get("manual", 0),
            "error_count": status_counts.get("error", 0),
            "unknown_count": status_counts.get("unknown", 0),
            "min_revid": min_revid,
            "max_revid": max_revid,
            "max_approvable_revid": max_approvable_revid,
            "status_breakdown": status_counts,
            "reason_breakdown": reason_counts,
            "approval_rate": (approved_count / total_revisions * 100) if total_revisions > 0 else 0,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating approval statistics: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}
