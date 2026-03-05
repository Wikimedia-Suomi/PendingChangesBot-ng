"""
Statistics service using direct SQL access to wiki replica databases.

This implementation follows Zache's recommendation:
- Opens connections using DNS names when needed
- Closes connections immediately after use
- Avoids exhausting the connection pool
- Uses parameterized queries to prevent SQL injection

This replaces the Pywikibot SupersetQuery approach with direct SQL for better
connection management in production.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .wiki_replica_connection import get_wiki_replica_connection

if TYPE_CHECKING:
    from reviews.models import Wiki

logger = logging.getLogger(__name__)

# Whitelist of allowed resolution groupings (safe SQL expressions, not user input)
RESOLUTION_GROUPS = {
    "yearly": "FLOOR(d/10000)",
    "daily": "d",
    "monthly": "FLOOR(d/100)",
}


class DirectSQLStatisticsClient:
    """Client for fetching statistics using direct SQL connections."""

    def __init__(self, wiki: Wiki):
        """
        Initialize the direct SQL statistics client.

        Args:
            wiki: The Wiki model instance
        """
        self.wiki = wiki
        self.connection_manager = get_wiki_replica_connection(wiki)

    def fetch_flaggedrevs_statistics(
        self,
        start_date_filter: int,
        end_date_filter: int | None = None,
        resolution: str = "monthly",
    ) -> list[dict[str, Any]]:
        """
        Fetch FlaggedRevs statistics using direct SQL access.

        This queries the flaggedrevs_statistics table to get aggregated data
        about total pages, synced pages, reviewed pages, and pending lag.

        Args:
            start_date_filter: Start date as integer (e.g., 20100101)
            end_date_filter: Optional end date as integer
            resolution: Data resolution - 'daily', 'monthly', or 'yearly'

        Returns:
            List of dictionaries containing statistics data
        """
        resolution_group = RESOLUTION_GROUPS.get(resolution, RESOLUTION_GROUPS["monthly"])

        # Build parameterized date filter
        params: list[Any] = [start_date_filter]
        date_filter = "WHERE total_ns0.d >= %s"
        if end_date_filter:
            date_filter += " AND total_ns0.d <= %s"
            params.append(end_date_filter)

        sql_query = f"""
SELECT
    {resolution_group} as yearmonth,
    AVG(totalPages_ns0) AS totalPages_ns0_avg,
    AVG(syncedPages_ns0) AS syncedPages_ns0_avg,
    AVG(reviewedPages_ns0) AS reviewedPages_ns0_avg,
    AVG(pendingLag_average) AS pendingLag_average_avg
FROM
(
  SELECT
    total_ns0.d,
    totalPages_ns0,
    syncedPages_ns0,
    reviewedPages_ns0,
    pendingLag_average
  FROM
  (
    SELECT
      floor(frs_timestamp/1000000) as d,
      AVG(frs_stat_val) AS totalPages_ns0
    FROM flaggedrevs_statistics
    WHERE frs_stat_key = "totalPages-NS:0"
    GROUP BY d
  ) AS total_ns0
  LEFT JOIN
  (
    SELECT
      floor(frs_timestamp/1000000) as d,
      AVG(frs_stat_val) AS syncedPages_ns0
    FROM flaggedrevs_statistics
    WHERE frs_stat_key = "syncedPages-NS:0"
    GROUP BY d
  ) AS syncedpages_ns0
  ON total_ns0.d = syncedpages_ns0.d
  LEFT JOIN
  (
    SELECT
      floor(frs_timestamp/1000000) as d,
      AVG(frs_stat_val) AS reviewedPages_ns0
    FROM flaggedrevs_statistics
    WHERE frs_stat_key = "reviewedPages-NS:0"
    GROUP BY d
  ) AS reviewedpages_ns0
  ON total_ns0.d = reviewedpages_ns0.d
  LEFT JOIN
  (
    SELECT
      floor(frs_timestamp/1000000) as d,
      AVG(frs_stat_val) AS pendingLag_average
    FROM flaggedrevs_statistics
    WHERE frs_stat_key = "pendingLag-average"
    GROUP BY d
  ) AS pendinglag_average
  ON total_ns0.d = pendinglag_average.d
  {date_filter}
) as t
GROUP BY yearmonth
ORDER BY yearmonth
"""

        logger.info(
            "Fetching FlaggedRevs statistics for %s (resolution: %s)",
            self.wiki.code,
            resolution,
        )

        try:
            results = self.connection_manager.execute_query_with_params(sql_query, tuple(params))
            logger.info(
                "Fetched %d records of FlaggedRevs statistics for %s",
                len(results),
                self.wiki.code,
            )
            return results
        except Exception as e:
            logger.exception(
                "Failed to fetch FlaggedRevs statistics for %s: %s",
                self.wiki.code,
                str(e),
            )
            raise

    def fetch_review_activity(
        self,
        start_date_filter: str,
        end_date_filter: str | None = None,
        resolution: str = "monthly",
    ) -> list[dict[str, Any]]:
        """
        Fetch review activity data using direct SQL access.

        This queries the flaggedrevs table to get reviewer activity metrics.

        Args:
            start_date_filter: Start timestamp string (e.g., '20100101000000')
            end_date_filter: Optional end timestamp string
            resolution: Data resolution - 'daily', 'monthly', or 'yearly'

        Returns:
            List of dictionaries containing activity data
        """
        resolution_group = RESOLUTION_GROUPS.get(resolution, RESOLUTION_GROUPS["monthly"])

        # Build parameterized date filter
        params: list[Any] = [start_date_filter]
        end_date_clause = ""
        if end_date_filter:
            end_date_clause = "AND fr_timestamp <= %s"
            params.append(end_date_filter)

        sql_query = f"""
SELECT
    {resolution_group} as yearmonth,
    AVG(number_of_reviewers) AS number_of_reviewers_avg,
    AVG(number_of_reviews) AS number_of_reviews_avg,
    AVG(number_of_pages) AS number_of_pages_avg
FROM
(
  SELECT
      FLOOR(fr_timestamp/1000000) AS d,
      COUNT(DISTINCT(fr_user)) AS number_of_reviewers,
      SUM(1) AS number_of_reviews,
      COUNT(DISTINCT(fr_page_id)) AS number_of_pages
  FROM
      flaggedrevs
  WHERE
      fr_flags NOT LIKE "%%auto%%"
      AND fr_timestamp >= %s
      {end_date_clause}
  GROUP BY d
) as t
GROUP BY yearmonth
ORDER BY yearmonth
"""

        logger.info(
            "Fetching review activity for %s (resolution: %s)",
            self.wiki.code,
            resolution,
        )

        try:
            results = self.connection_manager.execute_query_with_params(sql_query, tuple(params))
            logger.info(
                "Fetched %d records of review activity for %s",
                len(results),
                self.wiki.code,
            )
            return results
        except Exception as e:
            logger.exception(
                "Failed to fetch review activity for %s: %s",
                self.wiki.code,
                str(e),
            )
            raise

    def fetch_review_statistics_from_logging(
        self,
        limit: int = 10000,
        min_timestamp: str | None = None,
        min_log_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch review statistics from logging table using direct SQL.

        This is used for the ReviewStatisticsCache model to track individual
        review actions with delay metrics.

        Args:
            limit: Maximum number of records to fetch
            min_timestamp: Minimum log_timestamp (format: 'YYYYMMDDHHMMSS')
            min_log_id: Minimum log_id for pagination

        Returns:
            List of dictionaries containing review statistics
        """
        # Build WHERE clause with parameterized values
        where_clauses = [
            "lg.log_namespace = 0",
            "lg.log_type = 'review'",
            "lg.log_action IN ('approve', 'approve2')",
        ]
        params: list[Any] = []

        if min_timestamp:
            where_clauses.append("lg.log_timestamp > BINARY(%s)")
            params.append(min_timestamp)
        if min_log_id:
            where_clauses.append("lg.log_id > %s")
            params.append(min_log_id)

        where_clause = " AND ".join(where_clauses)

        # LIMIT is also parameterized
        params.append(limit)

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
    GREATEST(0, TIMESTAMPDIFF(DAY, CAST(r.rev_timestamp AS DATETIME), CAST(l.log_timestamp AS DATETIME))) AS review_delay_days
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
    LIMIT %s
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

        logger.info(
            "Fetching review statistics from logging table for %s (limit: %d)",
            self.wiki.code,
            limit,
        )

        try:
            results = self.connection_manager.execute_query_with_params(sql_query, tuple(params))
            logger.info(
                "Fetched %d review records from logging table for %s",
                len(results),
                self.wiki.code,
            )
            return results
        except Exception as e:
            logger.exception(
                "Failed to fetch review statistics from logging for %s: %s",
                self.wiki.code,
                str(e),
            )
            raise


def get_direct_sql_client(wiki: Wiki) -> DirectSQLStatisticsClient:
    """
    Factory function to create a DirectSQLStatisticsClient.

    Args:
        wiki: The Wiki model instance

    Returns:
        DirectSQLStatisticsClient instance
    """
    return DirectSQLStatisticsClient(wiki)
