"""
Management command to benchmark superseded additions detection.

Compares the current similarity-based method against word-level diff tracking
using the MediaWiki REST API.

Usage:
    python manage.py benchmark_superseded --wiki=fi --sample-size=50
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.core.management.base import BaseCommand
from pywikibot.comms import http

from reviews.models import PendingPage, PendingRevision, Wiki

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Benchmark superseded additions detection methods."""

    help = "Compare similarity-based vs word-level diff superseded detection"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--wiki",
            type=str,
            required=True,
            help="Wiki language code to benchmark (e.g., 'fi', 'en')",
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=50,
            help="Number of revisions to test (default: 50)",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=0.2,
            help="Similarity threshold to test (default: 0.2)",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="benchmark_results.json",
            help="Output file for results (default: benchmark_results.json)",
        )

    def handle(self, *args, **options):
        """Run the benchmark comparison."""
        wiki_code = options["wiki"]
        sample_size = options["sample_size"]
        threshold = options["threshold"]
        output_file = options["output"]

        try:
            wiki = Wiki.objects.get(code=wiki_code)
        except Wiki.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"Wiki with code '{wiki_code}' not found. "
                    f"Available wikis: {', '.join(Wiki.objects.values_list('code', flat=True))}"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Benchmarking superseded detection on {wiki.code}.{wiki.family}"
            )
        )
        self.stdout.write(f"Sample size: {sample_size}")
        self.stdout.write(f"Threshold: {threshold}")

        # Warning about data requirements
        self.stdout.write(
            self.style.WARNING(
                "\nNote: This command requires that pending revisions data has been "
                "loaded into the database first. If you haven't done so, please load "
                "data via the web interface before running this benchmark."
            )
        )

        # Get sample of pending revisions with parent revisions
        revisions = self._get_sample_revisions(wiki, sample_size)

        if not revisions:
            self.stdout.write(
                self.style.ERROR(
                    "\nNo suitable revisions found for benchmarking. "
                    "This may be because:\n"
                    "  1. No data has been loaded for this wiki yet\n"
                    "  2. There are no revisions with parent revisions available\n"
                    "  3. There are no revisions that have been superseded\n\n"
                    "Please ensure data has been loaded via the web interface first."
                )
            )
            return

        self.stdout.write(f"\nFound {len(revisions)} revisions to test")

        # Run comparison
        results = []
        for i, revision in enumerate(revisions, 1):
            self.stdout.write(f"\nProcessing {i}/{len(revisions)}: r{revision.revid}")

            result = self._compare_methods(revision, wiki, threshold)
            results.append(result)

            # Show inline summary
            similarity_decision = "APPROVE" if result["similarity_superseded"] else "REVIEW"
            wordlevel_decision = "APPROVE" if result["wordlevel_superseded"] else "REVIEW"
            match = "✓" if similarity_decision == wordlevel_decision else "✗"

            self.stdout.write(
                f"  Similarity: {similarity_decision} | "
                f"Word-level: {wordlevel_decision} | "
                f"Match: {match}"
            )

        # Calculate statistics
        stats = self._calculate_statistics(results)

        # Output results
        self._output_results(results, stats, output_file)

        # Print summary
        self._print_summary(stats)

    def _get_sample_revisions(self, wiki: Wiki, sample_size: int) -> list[PendingRevision]:
        """Get sample of revisions suitable for testing."""
        # Get revisions that:
        # 1. Have a parent revision (so we can compare additions)
        # 2. Are not the latest revision (so we can check if superseded)
        # 3. Have a stable revision to compare against

        revisions = (
            PendingRevision.objects.filter(
                page__wiki=wiki,
                parentid__isnull=False,
            )
            .exclude(revid=0)
            .select_related("page", "page__wiki", "page__wiki__configuration")
            .order_by("-revid")[:sample_size * 3]  # Get extra to filter
        )

        # Filter to only revisions where there are later revisions
        suitable = []
        for rev in revisions:
            latest = (
                PendingRevision.objects.filter(page=rev.page)
                .order_by("-revid")
                .first()
            )
            if latest and latest.revid > rev.revid:
                suitable.append(rev)
                if len(suitable) >= sample_size:
                    break

        return suitable

    def _compare_methods(
        self, revision: PendingRevision, wiki: Wiki, threshold: float
    ) -> dict[str, Any]:
        """Compare similarity-based vs word-level diff methods."""
        from reviews.autoreview.utils.wikitext import (
            extract_additions,
            get_parent_wikitext,
            normalize_wikitext,
        )
        from reviews.autoreview.utils.similarity import is_addition_superseded

        # Get stable revision
        stable_revision = PendingRevision.objects.filter(
            page=revision.page, revid=revision.page.stable_revid
        ).first()

        if not stable_revision:
            return self._create_error_result(revision, "No stable revision found")

        current_stable_wikitext = stable_revision.get_wikitext()

        # Method 1: Current similarity-based approach
        try:
            result = is_addition_superseded(
                revision, current_stable_wikitext, threshold
            )
            similarity_superseded = result.get("is_superseded", False)
        except Exception as e:
            logger.error(f"Similarity method failed for r{revision.revid}: {e}")
            similarity_superseded = None

        # Method 2: Word-level diff tracking
        try:
            wordlevel_superseded = self._check_wordlevel_superseded(
                revision, wiki, threshold
            )
        except Exception as e:
            logger.error(f"Word-level method failed for r{revision.revid}: {e}")
            wordlevel_superseded = None

        # Get addition details for analysis
        parent_wikitext = get_parent_wikitext(revision)
        pending_wikitext = revision.get_wikitext()
        additions = extract_additions(parent_wikitext, pending_wikitext)
        normalized_additions = [normalize_wikitext(a) for a in additions if len(normalize_wikitext(a)) >= 20]

        return {
            "revid": revision.revid,
            "pageid": revision.page.pageid,
            "page_title": revision.page.title,
            "user": revision.user_name,
            "timestamp": revision.timestamp.isoformat() if revision.timestamp else None,
            "similarity_superseded": similarity_superseded,
            "wordlevel_superseded": wordlevel_superseded,
            "agreement": similarity_superseded == wordlevel_superseded,
            "addition_count": len(additions),
            "significant_addition_count": len(normalized_additions),
            "diff_url": self._get_diff_url(wiki, revision),
        }

    def _check_wordlevel_superseded(
        self, revision: PendingRevision, wiki: Wiki, threshold: float
    ) -> bool:
        """
        Check if additions are superseded using MediaWiki REST API word-level diff.

        This uses the visual diff API which tracks word-level changes including
        block moves.
        """
        # Get the parent revision ID
        if not revision.parentid:
            return False

        # Get latest revision
        latest = PendingRevision.objects.filter(page=revision.page).order_by("-revid").first()
        if not latest or latest.revid == revision.revid:
            return False

        # Fetch word-level diff between parent and pending revision
        # This tells us what words were added
        added_words = self._get_added_words_from_diff(
            wiki, revision.parentid, revision.revid
        )

        if not added_words:
            return False

        # Fetch word-level diff between parent and latest stable
        # This tells us what's currently in the latest version
        stable_words = self._get_added_words_from_diff(
            wiki, revision.parentid, latest.revid
        )

        # Calculate how many of the originally added words are still present
        # in the latest version
        if not stable_words:
            # None of the additions made it to stable - fully superseded
            return True

        # Calculate overlap
        added_set = set(added_words)
        stable_set = set(stable_words)
        overlap = added_set & stable_set

        if len(added_set) == 0:
            return False

        retention_ratio = len(overlap) / len(added_set)

        # If retention is below threshold, consider superseded
        # (inverse of similarity threshold logic)
        return retention_ratio < threshold

    def _get_added_words_from_diff(
        self, wiki: Wiki, from_revid: int, to_revid: int
    ) -> list[str]:
        """
        Fetch word-level diff from MediaWiki REST API.

        Returns list of words that were added in the to_revid compared to from_revid.
        """
        # MediaWiki REST API endpoint for visual diff
        # Format: https://{wiki.code}.{wiki.family}/w/rest.php/v1/revision/{from}/compare/{to}

        base_url = f"https://{wiki.code}.{wiki.family}.org/w/rest.php/v1/revision"
        url = f"{base_url}/{from_revid}/compare/{to_revid}"

        headers = {
            "User-Agent": "PendingChangesBot/1.0 (https://github.com/Wikimedia-Suomi/PendingChangesBot-ng)",
            "Accept": "application/json",
        }

        try:
            response = http.fetch(url, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    f"MediaWiki REST API returned {response.status_code} for {url}"
                )
                return []

            data = json.loads(response.text)

            # Extract added words from the diff
            # The REST API returns HTML with specific classes for additions
            return self._parse_diff_for_additions(data)

        except Exception as e:
            logger.error(f"Failed to fetch word-level diff from {url}: {e}")
            return []

    def _parse_diff_for_additions(self, diff_data: dict) -> list[str]:
        """
        Parse MediaWiki REST API diff response to extract added words.

        The REST API returns a structure with 'diff' HTML content where additions
        are marked with specific classes.
        """
        from bs4 import BeautifulSoup

        # Get the diff HTML
        diff_html = diff_data.get("diff", "")
        if not diff_html:
            return []

        soup = BeautifulSoup(diff_html, "lxml")

        # Find all additions (ins tags or diffchange-inline elements)
        added_words = []

        # Look for inserted text (usually in <ins> tags)
        for ins in soup.find_all("ins"):
            text = ins.get_text()
            # Split into words and filter
            words = [w.strip() for w in text.split() if len(w.strip()) > 2]
            added_words.extend(words)

        # Also check for diffchange classes (refined changes)
        for change in soup.find_all(class_="diffchange-inline"):
            if change.name != "del":  # Skip deletions
                text = change.get_text()
                words = [w.strip() for w in text.split() if len(w.strip()) > 2]
                added_words.extend(words)

        return added_words

    def _create_error_result(self, revision: PendingRevision, error: str) -> dict:
        """Create error result entry."""
        return {
            "revid": revision.revid,
            "pageid": revision.page.pageid,
            "page_title": revision.page.title,
            "error": error,
            "similarity_superseded": None,
            "wordlevel_superseded": None,
            "agreement": None,
        }

    def _get_diff_url(self, wiki: Wiki, revision: PendingRevision) -> str:
        """Generate diff URL for manual review."""
        return (
            f"https://{wiki.code}.{wiki.family}.org/w/index.php"
            f"?diff={revision.revid}&oldid={revision.parentid}"
        )

    def _calculate_statistics(self, results: list[dict]) -> dict[str, Any]:
        """Calculate statistics from benchmark results."""
        total = len(results)
        if total == 0:
            return {}

        # Filter out errors
        valid_results = [r for r in results if r.get("agreement") is not None]
        valid_count = len(valid_results)

        if valid_count == 0:
            return {"error": "No valid results"}

        # Agreement statistics
        agreements = sum(1 for r in valid_results if r["agreement"])
        disagreements = valid_count - agreements

        # Method-specific statistics
        similarity_approvals = sum(
            1 for r in valid_results if r["similarity_superseded"] is True
        )
        wordlevel_approvals = sum(
            1 for r in valid_results if r["wordlevel_superseded"] is True
        )

        # Disagreement analysis
        similarity_only = sum(
            1
            for r in valid_results
            if r["similarity_superseded"] is True
            and r["wordlevel_superseded"] is False
        )
        wordlevel_only = sum(
            1
            for r in valid_results
            if r["similarity_superseded"] is False
            and r["wordlevel_superseded"] is True
        )

        return {
            "total_tested": total,
            "valid_results": valid_count,
            "errors": total - valid_count,
            "agreements": agreements,
            "disagreements": disagreements,
            "agreement_rate": agreements / valid_count if valid_count > 0 else 0,
            "similarity_approvals": similarity_approvals,
            "wordlevel_approvals": wordlevel_approvals,
            "similarity_only_approvals": similarity_only,
            "wordlevel_only_approvals": wordlevel_only,
        }

    def _output_results(
        self, results: list[dict], stats: dict, output_file: str
    ) -> None:
        """Write results to JSON file."""
        output = {
            "statistics": stats,
            "results": results,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        self.stdout.write(
            self.style.SUCCESS(f"\nResults written to {output_file}")
        )

    def _print_summary(self, stats: dict) -> None:
        """Print summary statistics."""
        if "error" in stats:
            self.stdout.write(self.style.ERROR(f"\nError: {stats['error']}"))
            return

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("BENCHMARK SUMMARY"))
        self.stdout.write("=" * 60)

        self.stdout.write(f"\nTotal revisions tested: {stats['total_tested']}")
        self.stdout.write(f"Valid results: {stats['valid_results']}")
        self.stdout.write(f"Errors: {stats['errors']}")

        self.stdout.write("\n" + "-" * 60)
        self.stdout.write("AGREEMENT ANALYSIS")
        self.stdout.write("-" * 60)

        agreement_rate = stats['agreement_rate'] * 100
        self.stdout.write(f"\nAgreements: {stats['agreements']}")
        self.stdout.write(f"Disagreements: {stats['disagreements']}")
        self.stdout.write(
            self.style.SUCCESS(f"Agreement rate: {agreement_rate:.1f}%")
        )

        self.stdout.write("\n" + "-" * 60)
        self.stdout.write("METHOD COMPARISON")
        self.stdout.write("-" * 60)

        self.stdout.write(
            f"\nSimilarity-based approvals: {stats['similarity_approvals']}"
        )
        self.stdout.write(
            f"Word-level diff approvals: {stats['wordlevel_approvals']}"
        )

        self.stdout.write("\n" + "-" * 60)
        self.stdout.write("DISAGREEMENT BREAKDOWN")
        self.stdout.write("-" * 60)

        self.stdout.write(
            f"\nOnly similarity approved: {stats['similarity_only_approvals']}"
        )
        self.stdout.write(
            f"Only word-level approved: {stats['wordlevel_only_approvals']}"
        )

        self.stdout.write("\n" + "=" * 60)
