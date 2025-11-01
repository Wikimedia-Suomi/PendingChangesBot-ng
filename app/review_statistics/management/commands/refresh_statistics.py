"""
Management command to incrementally refresh statistics.

Fetches only new review data since last update (using max_log_id).
"""

import pywikibot
from django.core.management.base import BaseCommand
from reviews.models import Wiki

from review_statistics.services import StatisticsClient


class Command(BaseCommand):
    help = "Incrementally refresh review statistics (fetch only new data)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--wiki",
            type=str,
            help=(
                "Wiki code (e.g., 'fi' for Finnish Wikipedia). "
                "If not specified, refreshes all wikis."
            ),
        )

    def handle(self, *args, **options):
        wiki_code = options.get("wiki")

        if wiki_code:
            # Refresh single wiki
            try:
                wiki = Wiki.objects.get(code=wiki_code)
                wikis = [wiki]
            except Wiki.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Wiki '{wiki_code}' not found"))
                return
        else:
            # Refresh all wikis
            wikis = Wiki.objects.all()
            self.stdout.write(f"Refreshing statistics for all {wikis.count()} wikis...\n")

        total_new_records = 0

        for wiki in wikis:
            self.stdout.write(f"\n=== Refreshing Statistics for {wiki.name} ===")

            # Create Pywikibot site and StatisticsClient
            site = pywikibot.Site(code=wiki.code, fam=wiki.family)
            stats_client = StatisticsClient(wiki=wiki, site=site)

            try:
                result = stats_client.refresh_statistics()

                if result.get("is_incremental"):
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ Incremental update: "
                            f"fetched {result['total_records']} new records\n"
                            f"    Max log_id: {result['max_log_id']}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠ No existing data - performed full fetch:\n"
                            f"    {result['total_records']} records in "
                            f"{result.get('batches_fetched', 1)} batches\n"
                            f"    Max log_id: {result['max_log_id']}"
                        )
                    )

                total_new_records += result["total_records"]

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\n\nCompleted! Total new records across all wikis: {total_new_records}"
            )
        )
