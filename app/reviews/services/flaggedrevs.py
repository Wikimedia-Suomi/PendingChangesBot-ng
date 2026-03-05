from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlaggedStatus:
    """The FlaggedRevs status of a single page."""

    pageid: int
    title: str
    stable_revid: int | None
    pending_since: str | None
    level: str | None
    protection_level: str | None
    has_pending_changes: bool


@dataclass(frozen=True)
class ReviewResult:
    """Outcome of a review API call."""

    success: bool
    revid: int
    message: str


class FlaggedRevsClient:
    """Clean abstraction over the MediaWiki FlaggedRevs API.

    This class wraps FlaggedRevs-specific API calls so the rest of the
    codebase does not need to know about the raw ``action=query&prop=flagged``
    or ``action=review`` parameters.  When upstream Pywikibot gains native
    FlaggedRevs support, this class can be swapped for the Pywikibot
    implementation without changing callers.
    """

    def __init__(self, site: Any):
        self.site = site

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_flagged_status(
        self,
        page_ids: list[int] | None = None,
        titles: list[str] | None = None,
    ) -> list[FlaggedStatus]:
        """Return the flagged-revision status for the given pages.

        Args:
            page_ids: Page IDs to query.
            titles: Page titles to query (ignored when *page_ids* is given).

        Returns:
            A list of :class:`FlaggedStatus` objects.
        """
        if not page_ids and not titles:
            return []

        params: dict[str, Any] = {
            "action": "query",
            "prop": "info|flagged",
            "formatversion": 2,
        }
        if page_ids:
            params["pageids"] = "|".join(str(pid) for pid in page_ids)
        else:
            params["titles"] = "|".join(titles or [])

        request = self.site.simple_request(**params)
        try:
            response = request.submit()
        except Exception:
            logger.exception("Failed to query flagged status")
            return []

        pages = response.get("query", {}).get("pages", [])
        results: list[FlaggedStatus] = []
        for page in pages:
            flagged = page.get("flagged", {})
            pending_since = flagged.get("pending_since")
            results.append(
                FlaggedStatus(
                    pageid=page.get("pageid", 0),
                    title=page.get("title", ""),
                    stable_revid=flagged.get("stable_revid"),
                    pending_since=pending_since,
                    level=flagged.get("level"),
                    protection_level=flagged.get("protection_level"),
                    has_pending_changes=pending_since is not None,
                )
            )
        return results

    def get_pending_pages(self, limit: int = 50) -> list[FlaggedStatus]:
        """Return pages that have outstanding pending changes.

        Uses ``action=query&list=oldreviewedpages`` to find pages whose
        latest revision has not yet been reviewed.
        """
        params: dict[str, Any] = {
            "action": "query",
            "list": "oldreviewedpages",
            "orlimit": min(limit, 500),
            "formatversion": 2,
        }

        request = self.site.simple_request(**params)
        try:
            response = request.submit()
        except Exception:
            logger.exception("Failed to fetch old reviewed pages list")
            return []

        entries = response.get("query", {}).get("oldreviewedpages", [])
        results: list[FlaggedStatus] = []
        for entry in entries:
            results.append(
                FlaggedStatus(
                    pageid=entry.get("pageid", 0),
                    title=entry.get("title", ""),
                    stable_revid=entry.get("stable_revid"),
                    pending_since=entry.get("pending_since"),
                    level=None,
                    protection_level=None,
                    has_pending_changes=True,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def review_revision(
        self,
        revid: int,
        comment: str = "",
        *,
        unapprove: bool = False,
    ) -> ReviewResult:
        """Approve (or un-approve) a revision via the FlaggedRevs API.

        Calls ``action=review`` which requires the ``review`` user right
        and a valid CSRF token.

        Args:
            revid: The revision ID to review.
            comment: Optional edit summary / review comment.
            unapprove: If *True*, un-approve instead of approving.

        Returns:
            A :class:`ReviewResult` indicating success or failure.
        """
        try:
            token = self._get_csrf_token()
        except Exception:
            logger.exception("Failed to obtain CSRF token for review")
            return ReviewResult(
                success=False,
                revid=revid,
                message="Failed to obtain CSRF token.",
            )

        params: dict[str, Any] = {
            "action": "review",
            "revid": revid,
            "token": token,
            "formatversion": 2,
        }
        if comment:
            params["comment"] = comment
        if unapprove:
            params["unapprove"] = 1

        request = self.site.simple_request(**params)
        try:
            response = request.submit()
        except Exception:
            logger.exception("Failed to review revision %s", revid)
            return ReviewResult(
                success=False,
                revid=revid,
                message="API request failed.",
            )

        review_data = response.get("review", {})
        if "revid" in review_data:
            action = "un-approved" if unapprove else "approved"
            return ReviewResult(
                success=True,
                revid=revid,
                message=f"Revision {revid} {action} successfully.",
            )

        error = response.get("error", {})
        return ReviewResult(
            success=False,
            revid=revid,
            message=error.get("info", "Unknown error from review API."),
        )

    # ------------------------------------------------------------------
    # Review log
    # ------------------------------------------------------------------

    def get_review_log(
        self,
        title: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch the review log events for a given page title.

        Returns a list of raw log-event dicts from the API.
        """
        params: dict[str, Any] = {
            "action": "query",
            "list": "logevents",
            "letype": "review",
            "letitle": title,
            "lelimit": min(limit, 500),
            "leprop": "ids|type|details|timestamp|user",
            "formatversion": 2,
        }

        request = self.site.simple_request(**params)
        try:
            response = request.submit()
        except Exception:
            logger.exception("Failed to fetch review log for %s", title)
            return []

        return response.get("query", {}).get("logevents", [])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_csrf_token(self) -> str:
        """Retrieve a CSRF token from the wiki."""
        request = self.site.simple_request(
            action="query",
            meta="tokens",
            type="csrf",
            formatversion=2,
        )
        response = request.submit()
        return response["query"]["tokens"]["csrftoken"]
