from __future__ import annotations

import logging
from typing import Any

import requests
from django.core.management.base import BaseCommand
from django.db.models import QuerySet

from reviews.autoreview.checks.superseded_additions import check_superseded_additions
from reviews.autoreview.context import CheckContext
from reviews.models import PendingRevision

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Benchmark superseded additions test using MediaWiki REST API diffs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of revisions to test (default: 50)",
        )
        parser.add_argument(
            "--wiki",
            type=str,
            help="Wiki code to test (e.g., 'fi' for Finnish Wikipedia)",
        )
        parser.add_argument(
            "--page-id",
            type=int,
            help="Specific page ID to test",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit = options["limit"]
        wiki_code = options.get("wiki")
        page_id = options.get("page_id")

        self.stdout.write(self.style.SUCCESS("\n=== Superseded Additions Benchmark ===\n"))

        # Get revisions to test
        revisions = self._get_test_revisions(limit, wiki_code, page_id)

        if not revisions:
            self.stdout.write(self.style.WARNING("No revisions found to test."))
            return

        self.stdout.write(f"Testing {len(revisions)} revisions...\n")

        # Test results
        results = {
            "total": 0,
            "both_agree": 0,
            "both_positive": 0,
            "both_negative": 0,
            "discrepancies": [],
        }

        for revision in revisions:
            result = self._test_revision(revision)
            if result:
                results["total"] += 1
                if result["agreement"]:
                    results["both_agree"] += 1
                    if result["old_method"] and result["new_method"]:
                        results["both_positive"] += 1
                    elif not result["old_method"] and not result["new_method"]:
                        results["both_negative"] += 1
                else:
                    results["discrepancies"].append(result)

        # Print summary
        self._print_summary(results)

    def _get_test_revisions(
        self, limit: int, wiki_code: str | None, page_id: int | None
    ) -> QuerySet[PendingRevision]:
        """Get revisions to test."""
        revisions = PendingRevision.objects.select_related("page", "page__wiki").all()

        if wiki_code:
            revisions = revisions.filter(page__wiki__code=wiki_code)

        if page_id:
            revisions = revisions.filter(page__pageid=page_id)

        # Only get revisions that have wikitext
        revisions = revisions.exclude(wikitext="")

        # Get revisions with parent
        revisions = revisions.exclude(parentid__isnull=True)

        return revisions[:limit]

    def _test_revision(self, revision: PendingRevision) -> dict | None:
        """Test a single revision."""
        try:
            # Get stable revision
            stable_rev = PendingRevision.objects.filter(
                page=revision.page, revid=revision.page.stable_revid
            ).first()

            if not stable_rev:
                return None

            # Test with old method (current implementation)
            context = CheckContext(
                revision=revision,
                client=None,  # Not needed for superseded check
                profile=None,
                config=revision.page.wiki.configuration,
            )
            old_result = check_superseded_additions(context)
            old_method_superseded = old_result.status == "ok"

            # Test with new method (REST API diff)
            new_method_superseded = self._test_with_rest_api(revision, stable_rev)

            agreement = old_method_superseded == new_method_superseded

            if not agreement:
                # There's a discrepancy
                diff_url = self._get_diff_url(revision, stable_rev)

                return {
                    "revision_id": revision.revid,
                    "page_title": revision.page.title,
                    "wiki": revision.page.wiki.code,
                    "old_method": old_method_superseded,
                    "new_method": new_method_superseded,
                    "agreement": agreement,
                    "diff_url": diff_url,
                    "old_message": old_result.message,
                }

        except Exception as e:
            logger.exception(f"Error testing revision {revision.revid}: {e}")
            return None

        return None

    def _test_with_rest_api(
        self, revision: PendingRevision, stable_rev: PendingRevision
    ) -> bool:
        """Test using MediaWiki REST API diff to check if additions are still present."""
        try:
            wiki = revision.page.wiki
            api_url = f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/{revision.revid}/compare/{stable_rev.revid}"

            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Analyze the diff to see if additions are still present
            diff = data.get("diff", [])
            if not diff:
                return False

            # Check if any text was added in the revision that is still present in stable
            # Type 0 = context (unchanged text)
            # Type 1 = added text
            # Type 2 = deleted text

            additions = []
            for line in diff:
                if line.get("type") == 1:  # Added text
                    additions.append(line.get("text", ""))

            # If there are no additions, not superseded
            if not additions:
                return False

            # Check if additions appear in the stable version (context lines)
            # Simple check: if additions appear as context in diff, they're still present
            for line in diff:
                if line.get("type") == 0:  # Context (present in both)
                    context_text = line.get("text", "")
                    for addition in additions:
                        if addition in context_text or context_text in addition:
                            return True  # Addition is still present

            return False  # Additions were removed/replaced

        except Exception as e:
            logger.exception(f"Error in REST API test for revision {revision.revid}: {e}")
            return False

    def _get_diff_url(self, revision: PendingRevision, stable_rev: PendingRevision) -> str:
        """Generate URL to view the diff."""
        wiki = revision.page.wiki
        return (
            f"https://{wiki.code}.wikipedia.org/w/index.php?"
            f"title={revision.page.title}&diff={stable_rev.revid}&oldid={revision.revid}"
        )

    def _print_summary(self, results: dict) -> None:
        """Print summary of results."""
        self.stdout.write(self.style.SUCCESS("\n=== Results Summary ===\n"))

        self.stdout.write(f"Total revisions tested: {results['total']}")
        self.stdout.write(f"Both methods agree: {results['both_agree']}")
        self.stdout.write(f"  - Both say superseded: {results['both_positive']}")
        self.stdout.write(f"  - Both say NOT superseded: {results['both_negative']}")
        self.stdout.write(f"Discrepancies found: {len(results['discrepancies'])}")

        if results["discrepancies"]:
            self.stdout.write(
                self.style.WARNING("\n=== Discrepancies (Need Human Review) ===\n")
            )

            for disc in results["discrepancies"]:
                old_status = "SUPERSEDED" if disc["old_method"] else "NOT SUPERSEDED"
                new_status = "SUPERSEDED" if disc["new_method"] else "NOT SUPERSEDED"

                self.stdout.write(
                    f"\nRevision: {disc['revision_id']} on {disc['page_title']} ({disc['wiki']})"
                )
                self.stdout.write(f"  Old method: {old_status}")
                self.stdout.write(f"  New method: {new_status}")
                self.stdout.write(f"  Message: {disc['old_message']}")
                self.stdout.write(f"  Diff URL: {disc['diff_url']}")

        agreement_rate = (
            (results["both_agree"] / results["total"] * 100) if results["total"] > 0 else 0
        )
        self.stdout.write(
            self.style.SUCCESS(f"\n\nAgreement rate: {agreement_rate:.1f}%")
        )
