from __future__ import annotations

import logging
from datetime import datetime

import pywikibot
from django.core.management.base import BaseCommand
from django.db import transaction
from pywikibot.data.superset import SupersetQuery
from reviews.models.wiki import Wiki

from review_statistics.models import FlaggedRevsStatistics, ReviewActivity

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
        parser.add_argument(
            "--start-year",
            type=int,
            default=2010,
            help="Start year for data loading (default: 2010)",
        )
        parser.add_argument(
            "--resolution",
            type=str,
            choices=["daily", "monthly", "yearly"],
            default="monthly",
            help="Data resolution: daily, monthly (default), or yearly",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            help="Start date for data loading (format: YYYY-MM-DD, default: full data)",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            help="End date for data loading (format: YYYY-MM-DD, default: full data)",
        )

    def handle(self, *args, **options):
        from datetime import datetime

        wiki_code = options.get("wiki")
        clear = options.get("clear")
        full_refresh = options.get("full_refresh")
        start_year = options.get("start_year")
        resolution = options.get("resolution", "monthly")
        start_date = options.get("start_date")
        end_date = options.get("end_date")

        if clear:
            self.stdout.write("Clearing all statistics data...")
            FlaggedRevsStatistics.objects.all().delete()
            ReviewActivity.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Statistics data cleared."))
            return

        # Auto-continue from last month if no parameters provided and data exists
        if not start_date and not start_year and not full_refresh:
            # Check if there's existing data
            existing_data = FlaggedRevsStatistics.objects.all()
            if existing_data.exists():
                # Get the latest date from existing data
                latest_stat = existing_data.order_by("-date").first()
                if latest_stat:
                    latest_date = latest_stat.date
                    # Calculate next month from the latest date
                    if latest_date.month == 12:
                        next_year = latest_date.year + 1
                        next_month = 1
                    else:
                        next_year = latest_date.year
                        next_month = latest_date.month + 1

                    # Set start_date to the first day of the next month
                    start_date = datetime(next_year, next_month, 1).strftime("%Y-%m-%d")
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Auto-continuing from last available data (last date: {latest_date}). "
                            f"Loading from {start_date} onwards."
                        )
                    )
            else:
                # No existing data, use default start year
                start_year = 2010

        # Use default start_year if not set
        if not start_year:
            start_year = 2010

        if wiki_code:
            try:
                wiki = Wiki.objects.get(code=wiki_code)
                self._load_statistics_for_wiki(
                    wiki, full_refresh, start_year, resolution, start_date, end_date
                )
            except Wiki.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Wiki with code '{wiki_code}' not found."))
                return
        else:
            wikis = Wiki.objects.all()
            for wiki in wikis:
                self._load_statistics_for_wiki(
                    wiki, full_refresh, start_year, resolution, start_date, end_date
                )

        self.stdout.write(self.style.SUCCESS("Statistics loaded successfully!"))

    def _load_statistics_for_wiki(
        self,
        wiki: Wiki,
        full_refresh: bool = False,
        start_year: int = 2010,
        resolution: str = "monthly",
        start_date: str = None,
        end_date: str = None,
    ):
        """Load statistics for a single wiki from Superset."""
        self.stdout.write(f"Loading statistics for {wiki.code}...")

        try:
            # Create site for the target wiki to query its Superset database
            wiki_site = pywikibot.Site(code=wiki.code, fam=wiki.family)
            superset = SupersetQuery(site=wiki_site)

            # Load FlaggedRevs statistics (required)
            self._load_flaggedrevs_statistics(
                wiki, superset, full_refresh, start_year, resolution, start_date, end_date
            )

            # Load review activity
            try:
                self._load_review_activity(
                    wiki, superset, full_refresh, start_year, resolution, start_date, end_date
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Review activity loading skipped (Superset timeout/error): "
                        f"{str(e)[:100]}"
                    )
                )
                logger.warning(f"Review activity loading failed for {wiki.code}: {e}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to load statistics for {wiki.code}: {e}"))
            logger.exception(f"Failed to load statistics for {wiki.code}")

    def _load_flaggedrevs_statistics(
        self,
        wiki: Wiki,
        superset: SupersetQuery,
        full_refresh: bool,
        start_year: int = 2010,
        resolution: str = "monthly",
        start_date: str = None,
        end_date: str = None,
    ):
        """Load core FlaggedRevs statistics from flaggedrevs_statistics table."""

        # Determine resolution grouping
        if resolution == "yearly":
            resolution_group = "FLOOR(d/10000)"  # Group by year: 201001 -> 2010
        elif resolution == "daily":
            resolution_group = "d"  # Group by day
        else:  # monthly (default)
            resolution_group = "FLOOR(d/100)"  # Group by month

        # Parse date range if provided
        from datetime import datetime as dt

        start_date_filter = start_year * 10000 + 101  # e.g., 20100101
        end_date_filter = None

        if start_date:
            try:
                parsed_start = dt.strptime(start_date, "%Y-%m-%d")
                start_date_filter = int(parsed_start.strftime("%Y%m%d"))
            except ValueError:
                logger.warning(f"Invalid start_date format: {start_date}, using default")

        if end_date:
            try:
                parsed_end = dt.strptime(end_date, "%Y-%m-%d")
                end_date_filter = int(parsed_end.strftime("%Y%m%d"))
            except ValueError:
                logger.warning(f"Invalid end_date format: {end_date}")

        # Add date filtering for incremental loading
        date_filter = ""
        if not full_refresh:
            # Load data from start_date
            date_filter = f"WHERE total_ns0.d >= {start_date_filter}"
        else:
            date_filter = f"WHERE total_ns0.d >= {start_date_filter}"

        if end_date_filter:
            date_filter += f" AND total_ns0.d <= {end_date_filter}"

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

        try:
            payload = superset.query(sql_query)
            self.stdout.write(f"  Retrieved {len(payload)} months of statistics data")

            if full_refresh:
                FlaggedRevsStatistics.objects.filter(wiki=wiki).delete()

            saved_count = 0
            skipped_count = 0

            with transaction.atomic():
                for entry in payload:
                    # Parse yearmonth based on resolution
                    raw_yearmonth = entry.get("yearmonth", "")
                    yearmonth_str = str(int(float(raw_yearmonth))) if raw_yearmonth else ""

                    if not yearmonth_str:
                        skipped_count += 1
                        continue

                    try:
                        if resolution == "yearly":
                            # Format: YYYY (e.g., 2010)
                            if len(yearmonth_str) == 4:
                                year = int(yearmonth_str)
                                date = datetime(year, 1, 1).date()
                            else:
                                skipped_count += 1
                                continue
                        elif resolution == "daily":
                            # Format: YYYYMMDD (e.g., 20100101)
                            if len(yearmonth_str) == 8:
                                year = int(yearmonth_str[:4])
                                month = int(yearmonth_str[4:6])
                                day = int(yearmonth_str[6:8])
                                date = datetime(year, month, day).date()
                            else:
                                skipped_count += 1
                                continue
                        else:  # monthly (default)
                            # Format: YYYYMM (e.g., 201001)
                            if len(yearmonth_str) == 6:
                                year = int(yearmonth_str[:4])
                                month = int(yearmonth_str[4:6])
                                date = datetime(year, month, 1).date()
                            else:
                                skipped_count += 1
                                continue
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

    def _load_review_activity(
        self,
        wiki: Wiki,
        superset: SupersetQuery,
        full_refresh: bool,
        start_year: int = 2010,
        resolution: str = "monthly",
        start_date: str = None,
        end_date: str = None,
    ):
        """Load review activity data from flaggedrevs table."""

        # Determine resolution grouping
        if resolution == "yearly":
            resolution_group = "FLOOR(d/10000)"  # Group by year
        elif resolution == "daily":
            resolution_group = "d"  # Group by day
        else:  # monthly (default)
            resolution_group = "FLOOR(d/100)"  # Group by month

        # Parse date range if provided
        from datetime import datetime as dt

        start_date_filter = f"{start_year}0101000000"  # e.g., 20100101000000
        end_date_filter = None

        if start_date:
            try:
                parsed_start = dt.strptime(start_date, "%Y-%m-%d")
                start_date_filter = parsed_start.strftime("%Y%m%d%H%M%S")
            except ValueError:
                logger.warning(f"Invalid start_date format: {start_date}, using default")

        if end_date:
            try:
                parsed_end = dt.strptime(end_date, "%Y-%m-%d")
                end_date_filter = parsed_end.strftime("%Y%m%d%H%M%S")
            except ValueError:
                logger.warning(f"Invalid end_date format: {end_date}")

        start_year_str = str(start_year)

        # Add incremental loading
        date_filter = ""
        if not full_refresh:
            # Load recent data only
            date_filter = "AND fr_timestamp >= 20200801000000"
        else:
            if end_date_filter:
                date_filter = f"AND fr_timestamp <= {end_date_filter}"

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
      fr_flags NOT LIKE "%auto%"
      AND fr_timestamp >= {start_date_filter}
      {date_filter}
  GROUP BY d
) as t
GROUP BY yearmonth
ORDER BY yearmonth
"""

        self.stdout.write(f"  Querying review activity (from {start_year_str} onwards)...")

        try:
            payload = superset.query(sql_query)
            self.stdout.write(f"  Retrieved {len(payload)} months of review activity data")

            if full_refresh:
                ReviewActivity.objects.filter(wiki=wiki).delete()

            with transaction.atomic():
                for entry in payload:
                    # Parse yearmonth based on resolution
                    raw_yearmonth = entry.get("yearmonth", "")
                    yearmonth_str = str(int(float(raw_yearmonth))) if raw_yearmonth else ""

                    if not yearmonth_str:
                        continue

                    try:
                        if resolution == "yearly":
                            # Format: YYYY (e.g., 2010)
                            if len(yearmonth_str) == 4:
                                year = int(yearmonth_str)
                                date = datetime(year, 1, 1).date()
                            else:
                                continue
                        elif resolution == "daily":
                            # Format: YYYYMMDD (e.g., 20100101)
                            if len(yearmonth_str) == 8:
                                year = int(yearmonth_str[:4])
                                month = int(yearmonth_str[4:6])
                                day = int(yearmonth_str[6:8])
                                date = datetime(year, month, day).date()
                            else:
                                continue
                        else:  # monthly (default)
                            # Format: YYYYMM (e.g., 201001)
                            if len(yearmonth_str) == 6:
                                year = int(yearmonth_str[:4])
                                month = int(yearmonth_str[4:6])
                                date = datetime(year, month, 1).date()
                            else:
                                continue
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
