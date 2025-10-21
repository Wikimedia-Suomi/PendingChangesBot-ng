from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

import pywikibot
from django.db import transaction
from django.utils import timezone as dj_timezone
from pywikibot.data.superset import SupersetQuery

from .parsers import (
    parse_optional_int,
    parse_superset_list,
    parse_superset_timestamp,
    prepare_superset_metadata,
)
from .types import RevisionPayload
from .user_blocks import was_user_blocked_after

if TYPE_CHECKING:
    from reviews.models import (
        EditorProfile,
        PendingPage,
        PendingRevision,
        Wiki,
    )

logger = logging.getLogger(__name__)

os.environ.setdefault("PYWIKIBOT2_NO_USER_CONFIG", "1")
os.environ.setdefault("PYWIKIBOT_NO_USER_CONFIG", "2")


class WikiClient:
    """Client responsible for synchronising data for a wiki."""

    def __init__(self, wiki: Wiki):
        self.wiki = wiki
        self.site = pywikibot.Site(code=wiki.code, fam=wiki.family)

    def has_manual_unapproval(self, page_title: str, revid: int) -> bool:
        """Check if the most recent review action for a revision is an un-approval."""
        try:
            request = self.site.simple_request(
                action="query",
                list="logevents",
                letype="review",
                letitle=page_title,
                lelimit=50,
                leprop="ids|type|details|timestamp|user",
                formatversion=2,
            )
            response = request.submit()
            log_events = response.get("query", {}).get("logevents", [])

            for event in log_events:
                params = event.get("params", {})
                event_revid = params.get("0")

                if event_revid == revid:
                    action = event.get("action")
                    if action in ("unapprove", "unapprove2"):
                        logger.info(
                            "Revision %s was manually un-approved (action: %s) at %s",
                            revid,
                            action,
                            event.get("timestamp"),
                        )
                        return True
                    else:
                        logger.info(
                            "Revision %s has review action '%s' at %s (not un-approved)",
                            revid,
                            action,
                            event.get("timestamp"),
                        )
                        return False

            return False
        except Exception:
            logger.exception(
                "Failed to check review log for page %s, revision %s",
                page_title,
                revid,
            )
            return False

    def is_user_blocked_after_edit(self, username: str, edit_timestamp: datetime) -> bool:
        """Check if user was blocked after making an edit."""
        year = edit_timestamp.year
        return was_user_blocked_after(self.wiki.code, self.wiki.family, username, year)

    def get_rendered_html(self, revid: int) -> str:
        """Fetch the rendered HTML for a specific revision."""
        from reviews.models import PendingRevision

        if not revid:
            return ""

        try:
            revision = PendingRevision.objects.get(page__wiki=self.wiki, revid=revid)
            if revision.rendered_html:
                return revision.rendered_html
        except PendingRevision.DoesNotExist:
            revision = None
        except Exception:
            revision = None

        request = self.site.simple_request(
            action="parse",
            oldid=revid,
            prop="text",
            formatversion=2,
        )
        try:
            response = request.submit()
            html = response.get("parse", {}).get("text", "")
            html_content = html if isinstance(html, str) else ""
            if revision and html_content:
                revision.rendered_html = html_content
                revision.save(update_fields=["rendered_html"])
            return html_content
        except Exception:
            return ""

    def fetch_pending_pages(self, limit: int = 10000) -> list[PendingPage]:
        """Fetch the pending pages using Superset and cache them in the database."""
        from reviews.models import PendingPage, PendingRevision

        limit = int(limit)
        if limit <= 0:
            return []

        sql_query = f"""
SELECT
   page_title,
   page_namespace,
   page_is_redirect,
   fp_page_id,
   fp_pending_since,
   fp_stable,
   rev_id,
   rev_timestamp,
   rev_len,
   rev_parent_id,
   rev_deleted,
   rev_sha1,
   comment_text,
   a.actor_name,
   a.actor_user,
   group_concat(DISTINCT(ctd_name)) AS change_tags,
   group_concat(DISTINCT(ug_group)) AS user_groups,
   group_concat(DISTINCT(ufg_group)) AS user_former_groups,
   group_concat(DISTINCT(cl_to)) AS page_categories,
   rc_bot,
   rc_patrolled,
   pp_value as wikibase_item
FROM
   (SELECT fp.* FROM page,flaggedpages as fp
   WHERE fp_page_id=page_id AND page_namespace=0 AND fp_pending_since IS NOT NULL
   ORDER BY fp_pending_since DESC LIMIT {limit}) AS fp,
   revision AS r
       LEFT JOIN change_tag ON r.rev_id=ct_rev_id
       LEFT JOIN change_tag_def ON ct_tag_id = ctd_id
       LEFT JOIN recentchanges ON rc_this_oldid = r.rev_id AND rc_source="mw.edit"
   ,
   page AS p
       LEFT JOIN categorylinks ON cl_from = page_id
       LEFT JOIN page_props ON pp_page = page_id AND pp_propname="wikibase_item",
   comment_revision,
   actor_revision AS a
   LEFT JOIN user_groups ON a.actor_user=ug_user
   LEFT JOIN user_former_groups ON a.actor_user=ufg_user
WHERE
   fp_pending_since IS NOT NULL
   AND r.rev_page=fp_page_id
   AND page_id=fp_page_id
   AND page_namespace=0
   AND r.rev_id>=fp_stable
   AND r.rev_actor=a.actor_id
   AND r.rev_comment_id=comment_id
GROUP BY r.rev_id
ORDER BY fp_pending_since, rev_id DESC
"""

        superset = SupersetQuery(site=self.site)
        payload = superset.query(sql_query)
        pages: list[PendingPage] = []
        pages_by_id: dict[int, PendingPage] = {}

        with transaction.atomic():
            PendingRevision.objects.filter(page__wiki=self.wiki).delete()
            PendingPage.objects.filter(wiki=self.wiki).delete()
            for entry in payload:
                pageid = entry.get("fp_page_id")
                try:
                    pageid_int = int(pageid)
                except (TypeError, ValueError):
                    continue
                page_categories = parse_superset_list(entry.get("page_categories"))

                page = pages_by_id.get(pageid_int)
                if page is None:
                    pending_since = parse_superset_timestamp(entry.get("fp_pending_since"))
                    page = PendingPage.objects.create(
                        wiki=self.wiki,
                        pageid=pageid_int,
                        title=entry.get("page_title", ""),
                        stable_revid=int(entry.get("fp_stable") or 0),
                        pending_since=pending_since,
                        categories=page_categories,
                        wikidata_id=entry.get("wikibase_item", ""),
                    )
                    pages_by_id[pageid_int] = page
                    pages.append(page)
                elif page_categories != (page.categories or []):
                    page.categories = page_categories
                    page.save(update_fields=["categories"])

                revid = entry.get("rev_id")
                try:
                    revid_int = int(revid)
                except (TypeError, ValueError):
                    continue

                superset_revision_timestamp = parse_superset_timestamp(entry.get("rev_timestamp"))
                if superset_revision_timestamp is None:
                    superset_revision_timestamp = dj_timezone.now()

                payload_entry = RevisionPayload(
                    revid=revid_int,
                    parentid=parse_optional_int(entry.get("rev_parent_id")),
                    user=entry.get("actor_name"),
                    userid=parse_optional_int(entry.get("actor_user")),
                    timestamp=superset_revision_timestamp,
                    comment=entry.get("comment_text", "") or "",
                    sha1=entry.get("rev_sha1", "") or "",
                    tags=parse_superset_list(entry.get("change_tags")),
                    superset_data=prepare_superset_metadata(entry),
                )
                self._save_revision(page, payload_entry)

        return pages

    def _save_revision(self, page: PendingPage, payload: RevisionPayload) -> PendingRevision | None:
        from reviews.models import PendingPage, PendingRevision

        existing_page = (
            PendingPage.objects.filter(pk=page.pk).only("id").first() if page.pk else None
        )
        if existing_page is None:
            logger.warning(
                "Pending page %s was deleted before saving revision %s", page.pk, payload.revid
            )
            return None

        age = dj_timezone.now() - payload.timestamp
        defaults = {
            "parentid": payload.parentid,
            "user_name": payload.user or "",
            "user_id": payload.userid,
            "timestamp": payload.timestamp,
            "age_at_fetch": age,
            "sha1": payload.sha1,
            "comment": payload.comment,
            "change_tags": payload.tags,
            "wikitext": "",
        }
        if payload.superset_data is not None:
            defaults["superset_data"] = payload.superset_data

        revision, _ = PendingRevision.objects.update_or_create(
            page=existing_page,
            revid=payload.revid,
            defaults=defaults,
        )
        if payload.user:
            self.ensure_editor_profile(payload.user, payload.superset_data)
        return revision

    def ensure_editor_profile(
        self, username: str, superset_data: dict | None = None
    ) -> EditorProfile:
        from reviews.models import EditorProfile

        profile, created = EditorProfile.objects.get_or_create(
            wiki=self.wiki,
            username=username,
            defaults={
                "usergroups": [],
                "is_blocked": False,
                "is_bot": False,
                "is_former_bot": False,
                "is_autopatrolled": False,
                "is_autoreviewed": False,
            },
        )
        if not superset_data:
            return profile

        autoreviewed_groups = {"autoreview", "autoreviewer", "editor", "reviewer", "sysop", "bot"}
        groups = sorted(superset_data.get("user_groups") or [])
        former_groups = sorted(superset_data.get("user_former_groups") or [])

        profile.usergroups = groups
        profile.is_bot = "bot" in groups or bool(superset_data.get("rc_bot"))
        profile.is_former_bot = "bot" in former_groups
        profile.is_autopatrolled = "autopatrolled" in groups
        profile.is_autoreviewed = bool(autoreviewed_groups & set(groups))
        profile.is_blocked = bool(superset_data.get("user_blocked", False))
        profile.save(
            update_fields=[
                "usergroups",
                "is_blocked",
                "is_bot",
                "is_former_bot",
                "is_autopatrolled",
                "is_autoreviewed",
                "fetched_at",
            ]
        )
        return profile

    def refresh(self) -> list[PendingPage]:
        return self.fetch_pending_pages()

    def fetch_review_statistics(self, limit: int = 10000) -> dict:
        """
        Fetch review statistics from MediaWiki database using Superset.

        Based on the SQL query from issue.md which uses the flaggedrevs table
        to find manual reviews and calculate the delay between a pending revision
        and when it was reviewed.

        Returns:
            dict: Contains 'total_records', 'oldest_timestamp', 'newest_timestamp'
        """
        from reviews.models import ReviewStatisticsCache, ReviewStatisticsMetadata

        limit = int(limit)
        if limit <= 0:
            return {"total_records": 0, "oldest_timestamp": None, "newest_timestamp": None}

        sql_query = f"""
SELECT
   page_title,
   t.fr_page_id AS page_id,
   a1.actor_name AS reviewer_name,
   a2.actor_name AS reviewed_user_name,
   t.fr_rev_id AS reviewed_revision_id,
   r2.rev_id AS pending_revision_id,
   t.fr_timestamp AS reviewed_timestamp,
   r2.rev_timestamp AS pending_timestamp,
   TIMESTAMPDIFF(DAY, r2.rev_timestamp, fr_timestamp) AS review_delay_days
FROM (
    SELECT
        fr.*,
        MIN(r.rev_id) AS min_rev_id
    FROM (
            SELECT
                fr1.fr_rev_id,
                MAX(fr2.fr_rev_id) AS last_fr_rev_id,
                fr1.fr_page_id,
                fr1.fr_timestamp,
                fr1.fr_user
            FROM
                flaggedrevs AS fr1,
                flaggedrevs AS fr2
            WHERE
                fr1.fr_page_id=fr2.fr_page_id
                AND fr1.fr_rev_id>fr2.fr_rev_id
                AND fr1.fr_flags NOT LIKE "%auto%"
            GROUP BY fr1.fr_rev_id
            ORDER BY fr1.fr_rev_id DESC
            LIMIT {limit}
        ) AS fr,
        revision AS r
        WHERE
            fr.fr_rev_id >= r.rev_id
            AND fr.fr_page_id=r.rev_page
            AND fr.last_fr_rev_id < r.rev_id
        GROUP BY fr.fr_rev_id
    ) AS t,
    revision AS r2,
    page,
    actor a1,
    actor a2
WHERE
    t.min_rev_id=r2.rev_id
    AND r2.rev_page=page_id
    AND page_namespace=0
    AND a1.actor_user=fr_user
    AND a2.actor_id=rev_actor
"""

        try:
            superset = SupersetQuery(site=self.site)
            payload = superset.query(sql_query)

            oldest_timestamp = None
            newest_timestamp = None
            total_records = 0

            with transaction.atomic():
                # Clear existing statistics for this wiki
                ReviewStatisticsCache.objects.filter(wiki=self.wiki).delete()

                for entry in payload:
                    # Parse timestamps
                    reviewed_ts = parse_superset_timestamp(entry.get("reviewed_timestamp"))
                    pending_ts = parse_superset_timestamp(entry.get("pending_timestamp"))

                    if reviewed_ts is None or pending_ts is None:
                        continue

                    # Track oldest and newest timestamps
                    if oldest_timestamp is None or reviewed_ts < oldest_timestamp:
                        oldest_timestamp = reviewed_ts
                    if newest_timestamp is None or reviewed_ts > newest_timestamp:
                        newest_timestamp = reviewed_ts

                    # Extract revision IDs directly from query results
                    reviewed_revid = int(entry.get("reviewed_revision_id") or 0)
                    pending_revid = int(entry.get("pending_revision_id") or 0)

                    # Use update_or_create to handle potential duplicates
                    _, created = ReviewStatisticsCache.objects.update_or_create(
                        wiki=self.wiki,
                        reviewed_revision_id=reviewed_revid,
                        defaults={
                            "reviewer_name": entry.get("reviewer_name", ""),
                            "reviewed_user_name": entry.get("reviewed_user_name", ""),
                            "page_title": entry.get("page_title", ""),
                            "page_id": int(entry.get("page_id") or 0),
                            "pending_revision_id": pending_revid,
                            "reviewed_timestamp": reviewed_ts,
                            "pending_timestamp": pending_ts,
                            "review_delay_days": int(entry.get("review_delay_days") or 0),
                        },
                    )
                    if created:
                        total_records += 1

                # Update or create metadata
                metadata, _ = ReviewStatisticsMetadata.objects.update_or_create(
                    wiki=self.wiki,
                    defaults={
                        "total_records": total_records,
                        "oldest_review_timestamp": oldest_timestamp,
                        "newest_review_timestamp": newest_timestamp,
                    },
                )

            logger.info(
                "Fetched %d review statistics records for %s (oldest: %s, newest: %s)",
                total_records,
                self.wiki.code,
                oldest_timestamp,
                newest_timestamp,
            )

            return {
                "total_records": total_records,
                "oldest_timestamp": oldest_timestamp,
                "newest_timestamp": newest_timestamp,
            }

        except Exception:
            logger.exception("Failed to fetch review statistics for %s", self.wiki.code)
            return {"total_records": 0, "oldest_timestamp": None, "newest_timestamp": None}
