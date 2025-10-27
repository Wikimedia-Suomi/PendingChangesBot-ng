from __future__ import annotations

import logging
from datetime import datetime

import pywikibot
from django.core.management.base import BaseCommand
from django.db import transaction
from pywikibot.data.superset import SupersetQuery

from reviews.models.flaggedrevs_statistics import FlaggedRevsStatistics, ReviewActivity
from reviews.models.wiki import Wiki

logger = logging.getLogger(__name__)

"""
USAGE:
    python manage.py load_flaggedrevs_statistics  # Incremental update (recommended)
    python manage.py load_flaggedrevs_statistics --wiki fi
    # Update specific wiki only
    python manage.py load_flaggedrevs_statistics --full-refresh  # Delete and reload all data
    python manage.py load_flaggedrevs_statistics --clear  # Clear all data without loading

"""


class Command(BaseCommand):
    help = "Load FlaggedRevs statistics from Superset"

    def add_arguments(self, parser):
        parser.add_argument(
            "--wiki",
            type=str,
            help="Wiki code to load statistics for (e.g., fi). "
            "If not provided, loads for all wikis.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing statistics data before loading",
        )
        parser.add_argument(
            "--full-refresh",
            action="store_true",
            help="Full refresh - delete and reload all data",
        )

    def handle(self, *args, **options):
        wiki_code = options.get("wiki")
        clear = options.get("clear")
        full_refresh = options.get("full_refresh")

        if clear:
            self.stdout.write("Clearing all statistics data...")
            FlaggedRevsStatistics.objects.all().delete()
            ReviewActivity.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Statistics data cleared."))
            return

        if wiki_code:
            try:
                wiki = Wiki.objects.get(code=wiki_code)
                self._load_statistics_for_wiki(wiki, full_refresh)
            except Wiki.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Wiki with code '{wiki_code}' not found."))
                return
        else:
            wikis = Wiki.objects.all()
            for wiki in wikis:
                self._load_statistics_for_wiki(wiki, full_refresh)

        self.stdout.write(self.style.SUCCESS("Statistics loaded successfully!"))

    def _load_statistics_for_wiki(self, wiki: Wiki, full_refresh: bool = False):
        """Load statistics for a single wiki from Superset."""
        self.stdout.write(f"Loading statistics for {wiki.code}...")

        try:
            # Create site for the target wiki to query its Superset database
            wiki_site = pywikibot.Site(code=wiki.code, fam=wiki.family)
            superset = SupersetQuery(site=wiki_site)

            # Load FlaggedRevs statistics (required)
            self._load_flaggedrevs_statistics(wiki, superset, full_refresh)

            # Load review activity
            try:
                self._load_review_activity(wiki, superset, full_refresh)
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠ Review activity loading skipped (Superset timeout/error): "
                        f"{str(e)[:100]}"
                    )
                )
                logger.warning(f"Review activity loading failed for {wiki.code}: {e}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to load statistics for {wiki.code}: {e}"))
            logger.exception(f"Failed to load statistics for {wiki.code}")

    def _load_flaggedrevs_statistics(self, wiki: Wiki, superset: SupersetQuery, full_refresh: bool):
        """Load core FlaggedRevs statistics from flaggedrevs_statistics table."""

        # Add date filtering for incremental loading
        date_filter = ""
        if not full_refresh:
            # Load only data newer than 2020-08-01 to avoid partial days
            date_filter = "WHERE total_ns0.d > 20200801"

        sql_query = f"""
SELECT
    FLOOR(d/100) as yearmonth,
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

        try:
            payload = superset.query(sql_query)
            self.stdout.write(f"  Retrieved {len(payload)} months of statistics data")

            if full_refresh:
                FlaggedRevsStatistics.objects.filter(wiki=wiki).delete()

            saved_count = 0
            skipped_count = 0

            with transaction.atomic():
                for entry in payload:
                    # Parse yearmonth - can be float (201112.0) or string ("201112")
                    raw_yearmonth = entry.get("yearmonth", "")

                    # Convert to string and remove decimal point if present
                    yearmonth_str = str(int(float(raw_yearmonth))) if raw_yearmonth else ""

                    if not yearmonth_str or len(yearmonth_str) != 6:
                        skipped_count += 1
                        continue

                    try:
                        year = int(yearmonth_str[:4])
                        month = int(yearmonth_str[4:6])
                        date = datetime(year, month, 1).date()
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid yearmonth format: {yearmonth_str}")
                        skipped_count += 1
                        continue

                    # Update or create statistics record with averaged values
                    obj, created = FlaggedRevsStatistics.objects.update_or_create(
                        wiki=wiki,
                        date=date,
                        defaults={
                            "total_pages_ns0": self._parse_int(entry.get("totalPages_ns0_avg")),
                            "synced_pages_ns0": self._parse_int(entry.get("syncedPages_ns0_avg")),
                            "reviewed_pages_ns0": self._parse_int(
                                entry.get("reviewedPages_ns0_avg")
                            ),
                            "pending_lag_average": self._parse_float(
                                entry.get("pendingLag_average_avg")
                            ),
                        },
                    )
                    saved_count += 1

            self.stdout.write(
                self.style.SUCCESS(f"  ✓ Saved {saved_count} records (skipped {skipped_count})")
            )

            # Verify data was actually saved
            actual_count = FlaggedRevsStatistics.objects.filter(wiki=wiki).count()
            self.stdout.write(f"  Database now has {actual_count} total records for {wiki.code}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Failed to load FlaggedRevs statistics: {e}"))
            logger.exception("Failed to load FlaggedRevs statistics")

    def _load_review_activity(self, wiki: Wiki, superset: SupersetQuery, full_refresh: bool):
        """Load review activity data from flaggedrevs table."""

        start_date = "20200101000000"  # Start from 2020 for all wikis
        start_year = "2020"

        # Add incremental loading
        date_filter = ""
        if not full_refresh:
            date_filter = "AND fr_timestamp >= 20200801000000"

        sql_query = f"""
SELECT
    FLOOR(d/100) as yearmonth,
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
      fr_flags NOT LIKE "%auto%"
      AND fr_timestamp >= {start_date}
      {date_filter}
  GROUP BY d
) as t
GROUP BY yearmonth
ORDER BY yearmonth
"""

        self.stdout.write(f"  Querying review activity (from {start_year} onwards)...")

        try:
            payload = superset.query(sql_query)
            self.stdout.write(f"  Retrieved {len(payload)} months of review activity data")

            if full_refresh:
                ReviewActivity.objects.filter(wiki=wiki).delete()

            with transaction.atomic():
                for entry in payload:
                    # Parse yearmonth from the query
                    raw_yearmonth = entry.get("yearmonth", "")

                    # Convert to string and remove decimal point if present
                    yearmonth_str = str(int(float(raw_yearmonth))) if raw_yearmonth else ""

                    if not yearmonth_str or len(yearmonth_str) != 6:
                        continue

                    try:
                        year = int(yearmonth_str[:4])
                        month = int(yearmonth_str[4:6])
                        date = datetime(year, month, 1).date()
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid yearmonth format: {yearmonth_str}")
                        continue

                    # Update or create review activity record with averaged values
                    ReviewActivity.objects.update_or_create(
                        wiki=wiki,
                        date=date,
                        defaults={
                            "number_of_reviewers": self._parse_int(
                                entry.get("number_of_reviewers_avg")
                            ),
                            "number_of_reviews": self._parse_int(
                                entry.get("number_of_reviews_avg")
                            ),
                            "number_of_pages": self._parse_int(entry.get("number_of_pages_avg")),
                        },
                    )

            self.stdout.write(
                self.style.SUCCESS(f"  ✓ Loaded {len(payload)} months of review activity data")
            )

        except Exception:
            raise

    def _parse_int(self, value) -> int | None:
        """Parse integer value from Superset response."""
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _parse_float(self, value) -> float | None:
        """Parse float value from Superset response."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
