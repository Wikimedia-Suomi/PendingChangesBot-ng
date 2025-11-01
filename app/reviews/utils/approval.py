"""
Utility functions for approving/unapproving pending changes revisions.

This module provides functions to interact with MediaWiki's FlaggedRevs API
for approving or unapproving pending changes revisions.
"""

import logging

from django.conf import settings
from pywikibot import Site
from pywikibot.data.api import Request

logger = logging.getLogger(__name__)


def approve_revision(revid, comment, value=None, unapprove=False):
    """
    Approve or unapprove a pending changes revision.

    Args:
        revid (int): The revision ID for which to set the flags
        comment (str): Comment for the review
        value (int, optional): Flag value for the review. Defaults to None.
        unapprove (bool, optional): If True, revision will be unapproved
                                   rather than approved. Defaults to False.

    Returns:
        dict: Result of the review operation
    """
    try:
        # Get the site (assuming we're working with Finnish Wikipedia)
        site = Site("fi", "wikipedia")

        # Check if we're in dry-run mode
        if getattr(settings, "PENDING_CHANGES_DRY_RUN", True):
            # Get page title to check if it's in test namespace
            page_title = _get_page_title_from_revid(site, revid)

            if page_title and not page_title.startswith("Merkityt_versiot_-kokeilu/"):
                action = "unapprove" if unapprove else "approve"
                logger.info("DRY-RUN: Would %s revision %s on %s", action, revid, page_title)
                return {
                    "result": "success",
                    "dry_run": True,
                    "message": f"DRY-RUN: Would {action} revision {revid}",
                }

        # Prepare API request parameters
        params = {
            "action": "review",
            "revid": revid,
            "comment": comment,
        }

        # Add unapprove parameter if needed
        if unapprove:
            params["unapprove"] = "1"

        # Add value parameter if provided
        if value is not None:
            params["value"] = str(value)

        # Make the API request
        request = Request(site=site, **params)
        result = request.submit()

        # Check if the request was successful
        if "review" in result:
            action_past = "unapproved" if unapprove else "approved"
            logger.info("Successfully %s revision %s", action_past, revid)
            return {
                "result": "success",
                "dry_run": False,
                "message": f"Successfully {action_past} revision {revid}",
                "api_response": result["review"],
            }
        else:
            action = "unapprove" if unapprove else "approve"
            logger.error("Failed to %s revision %s: %s", action, revid, result)
            return {
                "result": "error",
                "dry_run": False,
                "message": f"Failed to {action} revision {revid}",
                "api_response": result,
            }

    except Exception as e:
        action_ing = "unapproving" if unapprove else "approving"
        logger.error("Error %s revision %s: %s", action_ing, revid, e)
        return {
            "result": "error",
            "dry_run": False,
            "message": f"Error {action_ing} revision {revid}: {e}",
        }


def _get_page_title_from_revid(site, revid):
    """
    Get the page title for a given revision ID.

    Args:
        site: Pywikibot site object
        revid (int): Revision ID

    Returns:
        str: Page title or None if not found
    """
    try:
        request = Request(site=site, action="query", prop="revisions", revids=revid, rvprop="title")
        result = request.submit()

        if "query" in result and "pages" in result["query"]:
            for page_id, page_data in result["query"]["pages"].items():
                if "revisions" in page_data:
                    return page_data["title"]

        return None

    except Exception as e:
        logger.error("Error getting page title for revision %s: %s", revid, e)
        return None
