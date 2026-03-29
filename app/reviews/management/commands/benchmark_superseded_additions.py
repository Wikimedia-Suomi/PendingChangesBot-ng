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
        parser.add_argument(
            "--use-blocks",
            action="store_true",
            help="Group consecutive edits by same editor as blocks",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit = options["limit"]
        wiki_code = options.get("wiki")
        page_id = options.get("page_id")
        use_blocks = options.get("use_blocks", False)

        # Suppress verbose logging during benchmark
        logging.getLogger("reviews").setLevel(logging.CRITICAL)
        logging.getLogger("requests").setLevel(logging.CRITICAL)
        logging.getLogger("").setLevel(logging.CRITICAL)  # Root logger

        self.stdout.write(self.style.SUCCESS("\n=== Superseded Additions Benchmark ===\n"))

        # Get revisions to test
        revisions = self._get_test_revisions(limit, wiki_code, page_id)

        if not revisions:
            self.stdout.write(self.style.WARNING("No revisions found to test."))
            return

        # Test results
        results = {
            "total": 0,
            "both_agree": 0,
            "both_positive": 0,
            "both_negative": 0,
            "discrepancies": [],
        }

        if use_blocks:
            # Block-based comparison
            self.stdout.write("Grouping revisions into edit blocks...\n")
            blocks = self._group_consecutive_edits(list(revisions))
            self.stdout.write(f"Testing {len(blocks)} edit blocks...\n")

            for block in blocks:
                result = self._test_revision_block(block)
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
        else:
            # Individual revision comparison
            self.stdout.write(f"Testing {len(revisions)} revisions...\n")

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

        # Order by user and timestamp for block grouping
        revisions = revisions.order_by("page", "user_name", "timestamp")

        return revisions[:limit]

    def _group_consecutive_edits(
        self, revisions: list[PendingRevision]
    ) -> list[list[PendingRevision]]:
        """Group consecutive edits by the same editor on the same page."""
        if not revisions:
            return []

        blocks = []
        current_block = [revisions[0]]
        current_user = revisions[0].user_name
        current_page = revisions[0].page

        for revision in revisions[1:]:
            # Check if same user and same page
            if revision.user_name == current_user and revision.page == current_page:
                current_block.append(revision)
            else:
                # Start new block
                blocks.append(current_block)
                current_block = [revision]
                current_user = revision.user_name
                current_page = revision.page

        # Add the last block
        if current_block:
            blocks.append(current_block)

        return blocks

    def _test_revision_block(self, block: list[PendingRevision]) -> dict | None:
        """Test a block of consecutive edits by the same editor."""
        if not block:
            return None

        try:
            # Use first and last revision in block
            first_revision = block[0]
            last_revision = block[-1]

            # Get stable revision
            stable_rev = PendingRevision.objects.filter(
                page=last_revision.page, revid=last_revision.page.stable_revid
            ).first()

            if not stable_rev:
                return None

            # Test with old method (test each revision)
            old_results = []
            for revision in block:
                context = CheckContext(
                    revision=revision,
                    client=None,
                    profile=None,
                    auto_groups={},
                    blocking_categories={},
                    redirect_aliases=[],
                )
                result = check_superseded_additions(context)
                old_results.append(result.status == "ok")

            # Block is superseded if ANY revision is superseded
            old_method_superseded = any(old_results)

            # Test with new method (treat block as single edit)
            new_method_superseded = self._test_block_with_rest_api(
                first_revision, last_revision, stable_rev
            )

            agreement = old_method_superseded == new_method_superseded

            if not agreement:
                # There's a discrepancy
                diff_url = self._get_diff_url(first_revision, stable_rev)
                revision_ids = [str(rev.revid) for rev in block]

                return {
                    "revision_id": f"Block: {', '.join(revision_ids)}",
                    "page_title": first_revision.page.title,
                    "wiki": first_revision.page.wiki.code,
                    "old_method": old_method_superseded,
                    "new_method": new_method_superseded,
                    "agreement": agreement,
                    "diff_url": diff_url,
                    "old_message": f"Block of {len(block)} edits",
                }

            return {
                "revision_id": f"Block: {', '.join(revision_ids)}",
                "page_title": first_revision.page.title,
                "wiki": first_revision.page.wiki.code,
                "old_method": old_method_superseded,
                "new_method": new_method_superseded,
                "agreement": agreement,
                "diff_url": diff_url,
                "old_message": f"Block of {len(block)} edits",
            }

        except Exception:
            # Silently handle errors
            return None

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
                auto_groups={},
                blocking_categories={},
                redirect_aliases=[],
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

        except Exception:
            # Silently handle errors
            return None

    def _get_user_additions(self, revision: PendingRevision, wiki) -> list[dict]:
        """Get text that user actually added (excluding moves)."""
        try:
            parent_to_revision_url = (
                f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/"
                f"{revision.parentid}/compare/{revision.revid}"
            )

            response = requests.get(parent_to_revision_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            diff = data.get("diff", [])

            # Extract added text, filtering out moves
            additions = []
            for line in diff:
                line_type = line.get("type")
                text = line.get("text", "").strip()

                # Type 1 = added text
                # Check if it's a pure addition (not a move)
                # MediaWiki marks moves differently, but we do basic filtering
                if line_type == 1 and text:
                    # Check if this text appears in nearby deletions (likely a move)
                    is_move = self._is_likely_move(text, diff, line)
                    if not is_move:
                        additions.append({"text": text, "line": line})

            return additions

        except Exception:
            # Silently handle errors (API limitations, missing revisions, etc.)
            return []

    def _is_likely_move(self, text: str, diff: list, current_line: dict) -> bool:
        """Check if added text is likely a move rather than new addition."""
        # Look for this text in nearby deletions (within 5 lines)
        current_line_num = current_line.get("lineNumber", 0)

        for line in diff:
            if line.get("type") == 2:  # Deletion
                deleted_text = line.get("text", "").strip()
                line_num = line.get("lineNumber", 0)

                # Check if similar text was deleted nearby
                if abs(line_num - current_line_num) <= 5:
                    # Use similarity check
                    if text in deleted_text or deleted_text in text:
                        return True
                    # Check Levenshtein-like similarity
                    if self._text_similarity(text, deleted_text) > 0.8:
                        return True

        return False

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate basic text similarity ratio."""
        if not text1 or not text2:
            return 0.0

        # Simple similarity: common characters / max length
        text1_words = set(text1.lower().split())
        text2_words = set(text2.lower().split())

        if not text1_words or not text2_words:
            return 0.0

        common = text1_words & text2_words
        total = text1_words | text2_words

        return len(common) / len(total) if total else 0.0

    def _test_with_rest_api(self, revision: PendingRevision, stable_rev: PendingRevision) -> bool:
        """Test using MediaWiki REST API diff to check if additions are still present."""
        try:
            wiki = revision.page.wiki

            # Step 1: Get what the user actually added (parent → revision)
            user_additions = self._get_user_additions(revision, wiki)

            if not user_additions:
                # No additions made, consider as superseded (nothing to check)
                return True

            # Step 2: Check if user's additions still exist in stable version
            # Compare revision → stable
            revision_to_stable_url = (
                f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/"
                f"{revision.revid}/compare/{stable_rev.revid}"
            )

            response = requests.get(revision_to_stable_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            diff = data.get("diff", [])
            if not diff:
                # No changes from revision to stable = additions still present
                return False

            # Get all deletions from revision → stable
            deletions = []
            for line in diff:
                if line.get("type") == 2:  # Deleted text
                    deletions.append(line.get("text", "").strip())

            # Check if user's additions were deleted (superseded)
            superseded_count = 0
            for addition in user_additions:
                addition_text = addition["text"]

                # Check if this addition appears in deletions
                for deletion in deletions:
                    # More sophisticated matching
                    if self._texts_match(addition_text, deletion):
                        superseded_count += 1
                        break

            # Consider superseded if majority of additions were removed
            superseded_ratio = superseded_count / len(user_additions)
            return superseded_ratio > 0.5  # More than 50% of additions removed

        except Exception:
            # Silently handle API errors
            return False

    def _test_block_with_rest_api(
        self,
        first_revision: PendingRevision,
        last_revision: PendingRevision,
        stable_rev: PendingRevision,
    ) -> bool:
        """Test a block of edits using REST API."""
        try:
            wiki = first_revision.page.wiki

            # Compare first parent → last revision to get all block additions
            block_additions_url = (
                f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/"
                f"{first_revision.parentid}/compare/{last_revision.revid}"
            )

            response = requests.get(block_additions_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            diff = data.get("diff", [])

            # Extract all additions in the block
            block_additions = []
            for line in diff:
                if line.get("type") == 1:
                    text = line.get("text", "").strip()
                    if text:
                        block_additions.append(text)

            if not block_additions:
                return True

            # Compare last revision → stable
            to_stable_url = (
                f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/"
                f"{last_revision.revid}/compare/{stable_rev.revid}"
            )

            response = requests.get(to_stable_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            diff = data.get("diff", [])
            if not diff:
                return False

            deletions = [line.get("text", "").strip() for line in diff if line.get("type") == 2]

            # Check if block additions were deleted
            superseded_count = 0
            for addition in block_additions:
                for deletion in deletions:
                    if self._texts_match(addition, deletion):
                        superseded_count += 1
                        break

            superseded_ratio = superseded_count / len(block_additions)
            return superseded_ratio > 0.5

        except Exception:
            # Silently handle API errors
            return False

    def _texts_match(self, text1: str, text2: str) -> bool:
        """Check if two texts match (improved from simple substring)."""
        if not text1 or not text2:
            return False

        # Normalize texts
        text1 = text1.lower().strip()
        text2 = text2.lower().strip()

        # Exact match
        if text1 == text2:
            return True

        # Substring match (both ways)
        if text1 in text2 or text2 in text1:
            return True

        # Word-level similarity
        similarity = self._text_similarity(text1, text2)
        return similarity > 0.7  # 70% word overlap

    def _get_diff_url(self, revision: PendingRevision, stable_rev: PendingRevision) -> str:
        """Generate URL to view the diff."""
        wiki = revision.page.wiki
        return (
            f"https://{wiki.code}.wikipedia.org/w/index.php?"
            f"title={revision.page.title}&diff={stable_rev.revid}&oldid={revision.revid}"
        )

    def _safe_str(self, text: str) -> str:
        """Convert text to ASCII-safe string for console output."""
        try:
            # Try to encode/decode to catch encoding issues
            return str(text).encode("ascii", errors="replace").decode("ascii")
        except Exception:
            return str(text)

    def _print_summary(self, results: dict) -> None:
        """Print summary of results."""
        self.stdout.write(self.style.SUCCESS("\n=== Results Summary ===\n"))

        self.stdout.write(f"Total revisions tested: {results['total']}")
        self.stdout.write(f"Both methods agree: {results['both_agree']}")
        self.stdout.write(f"  - Both say superseded: {results['both_positive']}")
        self.stdout.write(f"  - Both say NOT superseded: {results['both_negative']}")
        self.stdout.write(f"Discrepancies found: {len(results['discrepancies'])}")

        if results["discrepancies"]:
            self.stdout.write(self.style.WARNING("\n=== Discrepancies (Need Human Review) ===\n"))

            for disc in results["discrepancies"]:
                old_status = "SUPERSEDED" if disc["old_method"] else "NOT SUPERSEDED"
                new_status = "SUPERSEDED" if disc["new_method"] else "NOT SUPERSEDED"

                # Use ASCII-safe versions for console output
                page_title = self._safe_str(disc["page_title"])
                message = self._safe_str(disc["old_message"])
                diff_url = self._safe_str(disc["diff_url"])

                self.stdout.write(
                    f"\nRevision: {disc['revision_id']} on {page_title} ({disc['wiki']})"
                )
                self.stdout.write(f"  Old method: {old_status}")
                self.stdout.write(f"  New method: {new_status}")
                self.stdout.write(f"  Message: {message}")
                self.stdout.write(f"  Diff URL: {diff_url}")

        agreement_rate = (
            (results["both_agree"] / results["total"] * 100) if results["total"] > 0 else 0
        )
        self.stdout.write(self.style.SUCCESS(f"\n\nAgreement rate: {agreement_rate:.1f}%"))
