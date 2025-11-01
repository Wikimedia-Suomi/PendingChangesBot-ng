"""
Management command to load full statistics for a specified time period.

This clears existing cache and fetches all data for the specified number of days.
"""

import pywikibot
from django.core.management.base import BaseCommand
from reviews.models import Wiki

from review_statistics.services import StatisticsClient


class Command(BaseCommand):
    help = "Load full review statistics for a specified time period (clears existing cache)"

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
            default=30,
            help="Number of days of historical data to fetch (default: 30)",
        )

    def handle(self, *args, **options):
        wiki_code = options["wiki"]
        days = options["days"]

        # Get the wiki
        try:
            wiki = Wiki.objects.get(code=wiki_code)
        except Wiki.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Wiki '{wiki_code}' not found"))
            return

        self.stdout.write(
            self.style.SUCCESS(f"\n=== Loading {days} Days of Statistics for {wiki.name} ===\n")
        )
        self.stdout.write("This will clear existing cache and fetch fresh data...\n")

        # Create Pywikibot site and StatisticsClient
        site = pywikibot.Site(code=wiki.code, fam=wiki.family)
        stats_client = StatisticsClient(wiki=wiki, site=site)

        try:
            result = stats_client.fetch_all_statistics(days=days, clear_existing=True)

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully loaded statistics:\n"
                    f"    Total records: {result['total_records']}\n"
                    f"    Batches fetched: {result['batches_fetched']}\n"
                    f"    Oldest review: {result['oldest_timestamp']}\n"
                    f"    Newest review: {result['newest_timestamp']}\n"
                    f"    Max log_id: {result['max_log_id']}\n"
                )
            )

            if result["batches_fetched"] >= 10:
                self.stdout.write(
                    self.style.WARNING(
                        "\n⚠ Warning: Reached maximum batch limit (10 batches = 100k records).\n"
                        "   Consider reducing the number of days if you need complete data."
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Error loading statistics: {e}"))
            raise
