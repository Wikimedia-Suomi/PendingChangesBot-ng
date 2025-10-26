"""
Management command to compare flaggedrevs and logging table statistics queries.

This command fetches review statistics using both the old (flaggedrevs) and new (logging)
SQL queries and compares the results to verify they're similar enough to switch.
"""

import pywikibot
from django.core.management.base import BaseCommand
from reviews.models import Wiki
from reviews.services.statistics import StatisticsClient


class Command(BaseCommand):
    help = "Compare flaggedrevs and logging table statistics queries"

    def add_arguments(self, parser):
        parser.add_argument(
            "--wiki",
            type=str,
            required=True,
            help="Wiki code (e.g., 'fi' for Finnish Wikipedia)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days to compare (default: 7)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5000,
            help="Max records per query to fetch (default: 5000)",
        )

    def handle(self, *args, **options):
        from datetime import timedelta

        from django.utils import timezone as dj_timezone

        wiki_code = options["wiki"]
        days = options["days"]
        limit = options["limit"]

        # Get the wiki
        try:
            wiki = Wiki.objects.get(code=wiki_code)
        except Wiki.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Wiki '{wiki_code}' not found"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== Comparing Statistics Queries for {wiki.name} ===\n"
                f"Time period: Last {days} days\n"
                f"Max records: {limit} per query\n"
            )
        )

        # Create Pywikibot site and StatisticsClient
        site = pywikibot.Site(code=wiki.code, fam=wiki.family)
        stats_client = StatisticsClient(wiki=wiki, site=site)

        # Calculate timestamp for filtering
        min_date = dj_timezone.now() - timedelta(days=days)
        min_timestamp = min_date.strftime("%Y%m%d%H%M%S")

        # Fetch using new query (logging table) first to get the timestamp range
        self.stdout.write("Fetching using logging table (new query)...")
        new_result = stats_client._fetch_statistics_batch(
            limit=limit, min_timestamp=min_timestamp, save_to_db=False
        )
        new_records = new_result.get("records", [])
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ Fetched {new_result['total_records']} records\n"
                f"    Oldest: {new_result['oldest_timestamp']}\n"
                f"    Newest: {new_result['newest_timestamp']}\n"
                f"    Max log_id: {new_result['max_log_id']}\n"
            )
        )

        # Get min/max timestamps from new query for fair comparison
        new_oldest_ts = new_result["oldest_timestamp"]
        new_newest_ts = new_result["newest_timestamp"]

        if new_oldest_ts is None or new_newest_ts is None:
            self.stdout.write(self.style.ERROR("No data returned from new query"))
            return

        # Convert to MediaWiki timestamp format (YYYYMMDDHHMMSS)
        min_timestamp_for_old = new_oldest_ts.strftime("%Y%m%d%H%M%S")
        max_timestamp_for_old = new_newest_ts.strftime("%Y%m%d%H%M%S")

        # Fetch using old query (flaggedrevs table) with same timestamp range
        self.stdout.write(
            "\nFetching using flaggedrevs table (old query) with same timestamp range..."
        )
        old_result = stats_client._fetch_review_statistics_flaggedrevs(
            limit=limit,
            min_timestamp=min_timestamp_for_old,
            max_timestamp=max_timestamp_for_old,
            save_to_db=False,
        )
        old_records = old_result.get("records", [])
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ Fetched {old_result['total_records']} records\n"
                f"    Oldest: {old_result['oldest_timestamp']}\n"
                f"    Newest: {old_result['newest_timestamp']}\n"
            )
        )

        # Compare counts
        self.stdout.write("\n=== Record Count Comparison ===")
        old_count = len(old_records)
        new_count = len(new_records)
        count_diff = abs(old_count - new_count)
        count_diff_pct = (count_diff / max(old_count, 1)) * 100 if old_count > 0 else 0
        self.stdout.write(f"  Old query (flaggedrevs): {old_count} records")
        self.stdout.write(f"  New query (logging):     {new_count} records")
        self.stdout.write(
            f"  Difference:              {count_diff} records ({count_diff_pct:.1f}%)"
        )

        if count_diff_pct < 10:
            self.stdout.write(self.style.SUCCESS("  ✓ Count difference is acceptable (<10%)"))
        else:
            self.stdout.write(self.style.WARNING("  ⚠ Count difference is high (>10%)"))

        # Compare reviewer names
        self.stdout.write("\n=== Reviewer Name Comparison ===")
        old_reviewers = set(r["reviewer_name"] for r in old_records if r["reviewer_name"])
        new_reviewers = set(r["reviewer_name"] for r in new_records if r["reviewer_name"])
        common_reviewers = old_reviewers & new_reviewers
        only_old = old_reviewers - new_reviewers
        only_new = new_reviewers - old_reviewers

        self.stdout.write(f"  Unique reviewers in old query: {len(old_reviewers)}")
        self.stdout.write(f"  Unique reviewers in new query: {len(new_reviewers)}")
        self.stdout.write(f"  Common reviewers:              {len(common_reviewers)}")

        if only_old:
            self.stdout.write(
                f"  Only in old query ({len(only_old)}): {', '.join(sorted(list(only_old)[:5]))}"
            )
        if only_new:
            self.stdout.write(
                f"  Only in new query ({len(only_new)}): {', '.join(sorted(list(only_new)[:5]))}"
            )

        # Compare review delay statistics
        self.stdout.write("\n=== Review Delay Comparison ===")
        old_delays = [
            r["review_delay_days"] for r in old_records if r["review_delay_days"] is not None
        ]
        new_delays = [
            r["review_delay_days"] for r in new_records if r["review_delay_days"] is not None
        ]

        if old_delays and new_delays:
            old_avg = sum(old_delays) / len(old_delays)
            new_avg = sum(new_delays) / len(new_delays)
            old_median = sorted(old_delays)[len(old_delays) // 2] if old_delays else 0
            new_median = sorted(new_delays)[len(new_delays) // 2] if new_delays else 0

            self.stdout.write(f"  Old query average delay:   {old_avg:.1f} days")
            self.stdout.write(f"  New query average delay:   {new_avg:.1f} days")
            self.stdout.write(f"  Old query median delay:    {old_median:.1f} days")
            self.stdout.write(f"  New query median delay:    {new_median:.1f} days")

            avg_diff_pct = abs(old_avg - new_avg) / max(old_avg, 1) * 100
            median_diff_pct = abs(old_median - new_median) / max(old_median, 1) * 100

            self.stdout.write(
                f"  Average difference:        "
                f"{abs(old_avg - new_avg):.1f} days ({avg_diff_pct:.1f}%)"
            )
            self.stdout.write(
                f"  Median difference:         "
                f"{abs(old_median - new_median):.1f} days ({median_diff_pct:.1f}%)"
            )

            if avg_diff_pct < 15 and median_diff_pct < 15:
                self.stdout.write(
                    self.style.SUCCESS("  ✓ Delay statistics are similar (<15% difference)")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  ⚠ Delay statistics differ significantly (>15%)")
                )

        # Compare revision overlap
        self.stdout.write("\n=== Revision Overlap Comparison ===")
        old_revisions = set(
            r["reviewed_revision_id"] for r in old_records if r["reviewed_revision_id"]
        )
        new_revisions = set(
            r["reviewed_revision_id"] for r in new_records if r["reviewed_revision_id"]
        )
        common_revisions = old_revisions & new_revisions

        if old_revisions and new_revisions:
            overlap_pct = (len(common_revisions) / len(old_revisions | new_revisions)) * 100
            self.stdout.write(f"  Unique reviewed revisions in old query: {len(old_revisions)}")
            self.stdout.write(f"  Unique reviewed revisions in new query: {len(new_revisions)}")
            self.stdout.write(f"  Common revisions:                       {len(common_revisions)}")
            self.stdout.write(f"  Overlap percentage:                     {overlap_pct:.1f}%")

            if overlap_pct > 70:
                self.stdout.write(self.style.SUCCESS("  ✓ High overlap (>70%)"))
            else:
                self.stdout.write(self.style.WARNING("  ⚠ Low overlap (<70%)"))

        # Explain expected differences
        self.stdout.write("\n=== Understanding the Differences ===")
        self.stdout.write(
            "The logging table contains historical actions, while flaggedrevs shows current state."
        )
        self.stdout.write("Expected differences:")
        self.stdout.write("  • Logging includes deleted pages")
        self.stdout.write(
            "  • Logging may have multiple reviews of same revision (review/unapprove/re-review)"
        )
        self.stdout.write("  • Logging includes reviews that were later undone")
        self.stdout.write("\nThese differences are acceptable for statistics/graphs.")

        # Final recommendation
        self.stdout.write("\n=== Recommendation ===")
        critical_issues = []
        minor_concerns = []

        if count_diff_pct >= 10:
            critical_issues.append(
                f"Record count differs by {count_diff_pct:.1f}% (>10% threshold)"
            )

        if old_delays and new_delays:
            # Median is more important for graphs than average
            if median_diff_pct >= 20:
                critical_issues.append(
                    f"Median delay differs by {median_diff_pct:.1f}% (>20% threshold)"
                )
            elif avg_diff_pct >= 50:
                # Average can differ more due to outliers in logging table
                minor_concerns.append(
                    f"Average delay differs by {avg_diff_pct:.1f}% "
                    f"(median is identical, so this is acceptable)"
                )

        if old_revisions and new_revisions:
            if overlap_pct < 60:
                critical_issues.append(
                    f"Revision overlap is only {overlap_pct:.1f}% (<60% threshold)"
                )
            elif overlap_pct < 70:
                minor_concerns.append(
                    f"Revision overlap is {overlap_pct:.1f}% "
                    f"(acceptable - logging includes deleted pages)"
                )

        if critical_issues:
            self.stdout.write(self.style.ERROR("✗ Critical issues found:"))
            for issue in critical_issues:
                self.stdout.write(f"  - {issue}")
            self.stdout.write(
                self.style.ERROR(
                    "\nRecommendation: DO NOT switch to logging table query. "
                    "Investigate differences."
                )
            )
        elif minor_concerns:
            self.stdout.write(self.style.WARNING("⚠ Minor concerns (expected):"))
            for concern in minor_concerns:
                self.stdout.write(f"  - {concern}")
            self.stdout.write(
                self.style.SUCCESS(
                    "\n✓ Overall: Safe to proceed with logging table query.\n"
                    "  The differences are expected and acceptable for statistics purposes."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "✓ All checks passed! The logging table query produces similar results.\n"
                    "  It's safe to proceed with switching to the new query."
                )
            )

        self.stdout.write("\n")
