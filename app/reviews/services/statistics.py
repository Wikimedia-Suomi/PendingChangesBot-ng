"""
Statistics service for fetching and managing review statistics.

This module handles fetching review statistics from MediaWiki databases
and caching them locally for analysis.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from pywikibot.data.superset import SupersetQuery

from .parsers import parse_superset_timestamp

if TYPE_CHECKING:
    import pywikibot

    from reviews.models import Wiki

logger = logging.getLogger(__name__)


class StatisticsClient:
    """Client for fetching and managing review statistics."""

    def __init__(self, wiki: Wiki, site: pywikibot.Site):
        """
        Initialize the statistics client.

        Args:
            wiki: The Wiki model instance
            site: The Pywikibot Site instance
        """
        self.wiki = wiki
        self.site = site

    def refresh_statistics(self) -> dict:
        """
        Incrementally update statistics by fetching only new reviews since last update.

        Uses the max_log_id from metadata to continue from where we left off.
        If no metadata exists, performs a full fetch of 30 days.

        Returns:
            dict: Contains 'total_records', 'oldest_timestamp', 'newest_timestamp',
                  'max_log_id', 'is_incremental'
        """
        from django.db import transaction

        from reviews.models import ReviewStatisticsCache, ReviewStatisticsMetadata

        # Check if we have existing metadata with max_log_id
        try:
            metadata = ReviewStatisticsMetadata.objects.get(wiki=self.wiki)
            last_log_id = metadata.max_log_id

            if last_log_id is None:
                logger.info("No max_log_id found for %s, performing full fetch", self.wiki.code)
                return self.fetch_all_statistics(days=30, clear_existing=True)

            logger.info(
                "Incrementally fetching new statistics for %s (from log_id %d)",
                self.wiki.code,
                last_log_id,
            )

            # Fetch only new records
            result = self._fetch_statistics_batch(
                limit=10000, min_log_id=last_log_id, save_to_db=True
            )

            # Update metadata
            if result["total_records"] > 0:
                with transaction.atomic():
                    metadata.total_records = ReviewStatisticsCache.objects.filter(
                        wiki=self.wiki
                    ).count()
                    if result["oldest_timestamp"] and (
                        metadata.oldest_review_timestamp is None
                        or result["oldest_timestamp"] < metadata.oldest_review_timestamp
                    ):
                        metadata.oldest_review_timestamp = result["oldest_timestamp"]
                    if result["newest_timestamp"] and (
                        metadata.newest_review_timestamp is None
                        or result["newest_timestamp"] > metadata.newest_review_timestamp
                    ):
                        metadata.newest_review_timestamp = result["newest_timestamp"]
                    if result["max_log_id"]:
                        metadata.max_log_id = result["max_log_id"]
                    metadata.save()

            logger.info(
                "Incremental update complete for %s: fetched %d new records",
                self.wiki.code,
                result["total_records"],
            )

            return {
                "total_records": result["total_records"],
                "oldest_timestamp": result["oldest_timestamp"],
                "newest_timestamp": result["newest_timestamp"],
                "max_log_id": result["max_log_id"] if result["max_log_id"] else last_log_id,
                "is_incremental": True,
                "batches_fetched": 1,  # Incremental refresh is always single batch
                "batch_limit_reached": False,
            }

        except ReviewStatisticsMetadata.DoesNotExist:
            logger.info("No metadata found for %s, performing full fetch", self.wiki.code)
            result = self.fetch_all_statistics(days=30, clear_existing=True)
            result["is_incremental"] = False
            return result

    def fetch_all_statistics(self, days: int = 30, clear_existing: bool = True) -> dict:
        """
        Fetch review statistics for a specified number of days using pagination.

        This method fetches all available review data for the specified time period,
        making multiple queries if necessary to handle Superset's 10k row limit.

        Args:
            days: Number of days of historical data to fetch (default: 30)
            clear_existing: Whether to clear existing cache before fetching (default: True)

        Returns:
            dict: Contains 'total_records', 'oldest_timestamp', 'newest_timestamp',
                  'max_log_id', 'batches_fetched'
        """
        from datetime import timedelta

        from django.db import transaction
        from django.utils import timezone as dj_timezone

        from reviews.models import ReviewStatisticsCache, ReviewStatisticsMetadata

        logger.info("Fetching %d days of statistics for %s", days, self.wiki.code)

        # Calculate min timestamp (days ago)
        min_date = dj_timezone.now() - timedelta(days=days)
        min_timestamp_str = min_date.strftime("%Y%m%d%H%M%S")

        total_records = 0
        oldest_timestamp = None
        newest_timestamp = None
        max_log_id = None
        batches_fetched = 0
        last_batch_log_id = None

        if clear_existing:
            with transaction.atomic():
                ReviewStatisticsCache.objects.filter(wiki=self.wiki).delete()
                logger.info("Cleared existing statistics cache for %s", self.wiki.code)

        # Fetch in batches until no more data
        previous_max_log_id = None
        while True:
            batches_fetched += 1
            logger.info(
                "Fetching batch %d for %s (min_log_id: %s)",
                batches_fetched,
                self.wiki.code,
                last_batch_log_id,
            )

            result = self._fetch_statistics_batch(
                limit=10000,
                min_timestamp=min_timestamp_str,
                min_log_id=last_batch_log_id,
                save_to_db=True,
            )

            batch_count = result["total_records"]
            total_records += batch_count

            # Update timestamps
            if result["oldest_timestamp"]:
                if oldest_timestamp is None or result["oldest_timestamp"] < oldest_timestamp:
                    oldest_timestamp = result["oldest_timestamp"]
            if result["newest_timestamp"]:
                if newest_timestamp is None or result["newest_timestamp"] > newest_timestamp:
                    newest_timestamp = result["newest_timestamp"]

            # Update max_log_id
            current_max_log_id = result["max_log_id"]
            if current_max_log_id:
                max_log_id = current_max_log_id
                last_batch_log_id = current_max_log_id

            logger.info(
                "Batch %d: fetched %d records (max_log_id: %s)",
                batches_fetched,
                batch_count,
                current_max_log_id,
            )

            # Stop if no records were fetched or max_log_id didn't advance
            if batch_count == 0 or current_max_log_id == previous_max_log_id:
                logger.info("No more data available, stopping pagination")
                break

            previous_max_log_id = current_max_log_id

            # Safety limit: don't fetch more than 50 batches (500k records)
            if batches_fetched >= 50:
                logger.warning(
                    "Reached maximum batch limit (50 batches, %d records) for %s. "
                    "Some data may be missing.",
                    total_records,
                    self.wiki.code,
                )
                break

        # Update metadata
        from django.utils import timezone as dj_timezone

        with transaction.atomic():
            metadata, _ = ReviewStatisticsMetadata.objects.update_or_create(
                wiki=self.wiki,
                defaults={
                    "total_records": total_records,
                    "oldest_review_timestamp": oldest_timestamp,
                    "newest_review_timestamp": newest_timestamp,
                    "max_log_id": max_log_id,
                    "last_data_loaded_at": dj_timezone.now(),
                },
            )

        logger.info(
            "Completed fetching statistics for %s: "
            "%d records in %d batches (oldest: %s, newest: %s, max_log_id: %s)",
            self.wiki.code,
            total_records,
            batches_fetched,
            oldest_timestamp,
            newest_timestamp,
            max_log_id,
        )

        return {
            "total_records": total_records,
            "oldest_timestamp": oldest_timestamp,
            "newest_timestamp": newest_timestamp,
            "max_log_id": max_log_id,
            "batches_fetched": batches_fetched,
            "batch_limit_reached": batches_fetched >= 50,
        }

    def _fetch_statistics_batch(
        self,
        limit: int = 10000,
        min_timestamp: str | None = None,
        min_log_id: int | None = None,
        save_to_db: bool = True,
    ) -> dict:
        """
        Fetch review statistics using the logging table (new approach).

        This method uses the logging table which supports pagination and includes
        historical data for deleted pages. The logging table stores actions (not state),
        so the same revision may appear multiple times if reviewed multiple times.

        Args:
            limit: Maximum number of records to fetch (default: 10000)
            min_timestamp: Minimum log_timestamp to fetch (format: 'YYYYMMDDHHMMSS')
            min_log_id: Minimum log_id to fetch (for pagination)

        Returns:
            dict: Contains 'total_records', 'oldest_timestamp', 'newest_timestamp',
                  'max_log_id'
        """
        from reviews.models import ReviewStatisticsCache

        limit = int(limit)
        if limit <= 0:
            return {
                "total_records": 0,
                "oldest_timestamp": None,
                "newest_timestamp": None,
                "max_log_id": None,
            }

        # Build WHERE clause with optional filters
        where_clauses = [
            "lg.log_namespace = 0",
            "lg.log_type = 'review'",
            "lg.log_action IN ('approve', 'approve2')",
        ]

        if min_timestamp:
            where_clauses.append(f"lg.log_timestamp > BINARY('{min_timestamp}')")
        if min_log_id:
            where_clauses.append(f"lg.log_id > {min_log_id}")

        where_clause = " AND ".join(where_clauses)

        sql_query = f"""
SELECT
    l.log_id,
    l.log_page       AS page_id,
    l.log_title      AS page_title,
    l.log_user_name  AS reviewer_name,
    a2.actor_name    AS reviewed_user_name,
    l.reviewed_revision_id AS reviewed_revision_id,
    r.rev_id         AS pending_revision_id,
    l.log_timestamp  AS reviewed_timestamp,
    r.rev_timestamp  AS pending_timestamp,
    TIMESTAMPDIFF(DAY, r.rev_timestamp, l.log_timestamp) AS review_delay_days
FROM (
    SELECT
        log_id,
        log_page,
        log_title,
        log_timestamp,
        a1.actor_name AS log_user_name,
        CAST(
            SUBSTRING_INDEX(
                SUBSTRING_INDEX(log_params, 'i:0;i:', -1),
                ';',
                1
            ) AS UNSIGNED
        ) AS reviewed_revision_id,
        CAST(
            SUBSTRING_INDEX(
                SUBSTRING_INDEX(log_params, 'i:1;i:', -1),
                ';',
                1
            ) AS UNSIGNED
        ) AS extracted_id
    FROM logging AS lg
    JOIN actor_logging AS a1
      ON lg.log_actor = a1.actor_id
    WHERE
        {where_clause}
    ORDER BY lg.log_id ASC
    LIMIT {limit}
) AS l
INNER JOIN flaggedrevs AS fr
  ON fr.fr_rev_id = l.reviewed_revision_id
JOIN revision AS r
  ON r.rev_page = l.log_page
 AND r.rev_id = (
       SELECT r2.rev_id
       FROM revision AS r2
       WHERE r2.rev_page = l.log_page
         AND r2.rev_id > l.extracted_id
       ORDER BY r2.rev_id ASC
       LIMIT 1
   )
JOIN actor_revision AS a2
  ON a2.actor_id = r.rev_actor
ORDER BY l.log_id ASC
"""

        try:
            from django.db import transaction

            superset = SupersetQuery(site=self.site)
            payload = superset.query(sql_query)

            oldest_timestamp = None
            newest_timestamp = None
            max_log_id = None
            total_records = 0
            records = []

            if save_to_db:
                # Save to database
                with transaction.atomic():
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

                        # Track max log_id for pagination
                        log_id = int(entry.get("log_id") or 0)
                        if max_log_id is None or log_id > max_log_id:
                            max_log_id = log_id

                        # Extract revision IDs
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
            else:
                # Just collect records for comparison
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

                    # Track max log_id for pagination
                    log_id = int(entry.get("log_id") or 0)
                    if max_log_id is None or log_id > max_log_id:
                        max_log_id = log_id

                    records.append(
                        {
                            "log_id": log_id,
                            "reviewer_name": entry.get("reviewer_name", ""),
                            "reviewed_user_name": entry.get("reviewed_user_name", ""),
                            "page_title": entry.get("page_title", ""),
                            "page_id": int(entry.get("page_id") or 0),
                            "reviewed_revision_id": int(entry.get("reviewed_revision_id") or 0),
                            "pending_revision_id": int(entry.get("pending_revision_id") or 0),
                            "reviewed_timestamp": reviewed_ts,
                            "pending_timestamp": pending_ts,
                            "review_delay_days": int(entry.get("review_delay_days") or 0),
                        }
                    )
                    total_records += 1

            logger.info(
                "Fetched %d review statistics records (logging table) for %s "
                "(oldest: %s, newest: %s, max_log_id: %s)",
                total_records,
                self.wiki.code,
                oldest_timestamp,
                newest_timestamp,
                max_log_id,
            )

            result = {
                "total_records": total_records,
                "oldest_timestamp": oldest_timestamp,
                "newest_timestamp": newest_timestamp,
                "max_log_id": max_log_id,
            }
            if not save_to_db:
                result["records"] = records
            return result

        except Exception:
            logger.exception(
                "Failed to fetch review statistics (logging table) for %s", self.wiki.code
            )
            result = {
                "total_records": 0,
                "oldest_timestamp": None,
                "newest_timestamp": None,
                "max_log_id": None,
            }
            if not save_to_db:
                result["records"] = []
            return result

    def _fetch_review_statistics_flaggedrevs(
        self,
        limit: int = 10000,
        min_timestamp: str | None = None,
        max_timestamp: str | None = None,
        save_to_db: bool = True,
    ) -> dict:
        """
        Fetch review statistics from MediaWiki using the flaggedrevs table.

        This is the OLD query method used for comparison purposes only.

        Args:
            limit: Maximum number of records to fetch
            min_timestamp: Minimum fr_timestamp (YYYYMMDDHHMMSS format)
            max_timestamp: Maximum fr_timestamp (YYYYMMDDHHMMSS format)
            save_to_db: Whether to save records to database (default: True)

        Returns:
            dict: Contains 'total_records', 'oldest_timestamp', 'newest_timestamp'
                  If save_to_db=False, also includes 'records' list
        """
        from reviews.models import ReviewStatisticsCache

        limit = int(limit)
        if limit <= 0:
            return {
                "total_records": 0,
                "oldest_timestamp": None,
                "newest_timestamp": None,
                "records": [],
            }

        # Build timestamp filter clause
        timestamp_filter = ""
        if min_timestamp and max_timestamp:
            timestamp_filter = f"""
                AND fr1.fr_timestamp >= BINARY('{min_timestamp}')
                AND fr1.fr_timestamp <= BINARY('{max_timestamp}')
            """
        elif min_timestamp:
            timestamp_filter = f"AND fr1.fr_timestamp >= BINARY('{min_timestamp}')"
        elif max_timestamp:
            timestamp_filter = f"AND fr1.fr_timestamp <= BINARY('{max_timestamp}')"

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
                {timestamp_filter}
            GROUP BY fr1.fr_rev_id
            ORDER BY fr1.fr_timestamp ASC
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
            records = []

            if save_to_db:
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

                        # Extract revision IDs
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
            else:
                # Just collect records for comparison
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

                    records.append(
                        {
                            "reviewer_name": entry.get("reviewer_name", ""),
                            "reviewed_user_name": entry.get("reviewed_user_name", ""),
                            "page_title": entry.get("page_title", ""),
                            "page_id": int(entry.get("page_id") or 0),
                            "reviewed_revision_id": int(entry.get("reviewed_revision_id") or 0),
                            "pending_revision_id": int(entry.get("pending_revision_id") or 0),
                            "reviewed_timestamp": reviewed_ts,
                            "pending_timestamp": pending_ts,
                            "review_delay_days": int(entry.get("review_delay_days") or 0),
                        }
                    )
                    total_records += 1

            logger.info(
                "Fetched %d review statistics records (flaggedrevs table) for %s "
                "(oldest: %s, newest: %s)",
                total_records,
                self.wiki.code,
                oldest_timestamp,
                newest_timestamp,
            )

            result = {
                "total_records": total_records,
                "oldest_timestamp": oldest_timestamp,
                "newest_timestamp": newest_timestamp,
            }
            if not save_to_db:
                result["records"] = records
            return result

        except Exception:
            logger.exception(
                "Failed to fetch review statistics (flaggedrevs table) for %s", self.wiki.code
            )
            result = {
                "total_records": 0,
                "oldest_timestamp": None,
                "newest_timestamp": None,
            }
            if not save_to_db:
                result["records"] = []
            return result

    def fetch_review_statistics(self, limit: int = 10000, save_to_db: bool = True) -> dict:
        """
        Fetch review statistics from MediaWiki database using Superset.

        Based on the SQL query from issue.md which uses the flaggedrevs table
        to find manual reviews and calculate the delay between a pending revision
        and when it was reviewed.

        Args:
            limit: Maximum number of records to fetch (default: 10000)
            save_to_db: Whether to save records to database (default: True)

        Returns:
            dict: Contains 'total_records', 'oldest_timestamp', 'newest_timestamp'
                  If save_to_db=False, also includes 'records' list
        """
        from reviews.models import ReviewStatisticsCache, ReviewStatisticsMetadata

        limit = int(limit)
        if limit <= 0:
            return {
                "total_records": 0,
                "oldest_timestamp": None,
                "newest_timestamp": None,
                "records": [],
            }

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
            records = []

            if save_to_db:
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
            else:
                # Just collect records for comparison
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

                    records.append(
                        {
                            "reviewer_name": entry.get("reviewer_name", ""),
                            "reviewed_user_name": entry.get("reviewed_user_name", ""),
                            "page_title": entry.get("page_title", ""),
                            "page_id": int(entry.get("page_id") or 0),
                            "reviewed_revision_id": int(entry.get("reviewed_revision_id") or 0),
                            "pending_revision_id": int(entry.get("pending_revision_id") or 0),
                            "reviewed_timestamp": reviewed_ts,
                            "pending_timestamp": pending_ts,
                            "review_delay_days": int(entry.get("review_delay_days") or 0),
                        }
                    )
                    total_records += 1

            logger.info(
                "Fetched %d review statistics records for %s (oldest: %s, newest: %s)",
                total_records,
                self.wiki.code,
                oldest_timestamp,
                newest_timestamp,
            )

            result = {
                "total_records": total_records,
                "oldest_timestamp": oldest_timestamp,
                "newest_timestamp": newest_timestamp,
            }
            if not save_to_db:
                result["records"] = records

            return result

        except Exception:
            logger.exception("Failed to fetch review statistics for %s", self.wiki.code)
            result = {"total_records": 0, "oldest_timestamp": None, "newest_timestamp": None}
            if not save_to_db:
                result["records"] = []
            return result
