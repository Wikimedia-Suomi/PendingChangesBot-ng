"""
Comprehensive tests for approval comment generation functionality.
This module tests the new utility functions for generating consolidated
approval comments and processing autoreview results.
"""

from django.test import TestCase
from datetime import datetime

from reviews.utils.approval_comment import (
    generate_approval_comment,
    clean_approval_reason,
    validate_comment_length,
    group_consecutive_revisions,
    format_revision_group
)
from reviews.utils.approval_processor import (
    process_and_approve_revisions,
    preview_approval_comment,
    batch_process_pages,
    get_approval_statistics
)


class ApprovalCommentTests(TestCase):
    """Test cases for approval comment generation functionality."""

    def test_generate_approval_comment_single_revision(self):
        """Test generating approval comment for single revision."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
        ]
        
        rev_id, comment = generate_approval_comment(results)
        
        self.assertEqual(rev_id, 12345)
        self.assertEqual(comment, "rev_id 12345 approved because user was bot")

    def test_generate_approval_comment_multiple_revisions_same_reason(self):
        """Test generating approval comment for multiple revisions with same reason."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was bot"}},
        ]
        
        rev_id, comment = generate_approval_comment(results)
        
        self.assertEqual(rev_id, 12347)  # Highest revision ID
        self.assertEqual(comment, "rev_id 12345, 12346, 12347 approved because user was bot")

    def test_generate_approval_comment_multiple_reasons(self):
        """Test generating approval comment for multiple revisions with different reasons."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "no content change"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
        ]
        
        rev_id, comment = generate_approval_comment(results)
        
        self.assertEqual(rev_id, 12347)  # Highest revision ID
        self.assertIn("rev_id 12345 approved because user was bot", comment)
        self.assertIn("rev_id 12346 approved because no content change", comment)
        self.assertIn("rev_id 12347 approved because user was autoreviewed", comment)

    def test_generate_approval_comment_no_approvals(self):
        """Test generating approval comment when no revisions can be approved."""
        results = [
            {"revid": 12345, "decision": {"status": "blocked", "reason": "user was blocked"}},
            {"revid": 12346, "decision": {"status": "manual", "reason": "requires human review"}},
        ]
        
        rev_id, comment = generate_approval_comment(results)
        
        self.assertIsNone(rev_id)
        self.assertEqual(comment, "No revisions can be approved")

    def test_generate_approval_comment_with_prefix(self):
        """Test generating approval comment with prefix."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
        ]
        
        rev_id, comment = generate_approval_comment(results, "Auto:")
        
        self.assertEqual(rev_id, 12345)
        self.assertEqual(comment, "Auto: rev_id 12345 approved because user was bot")

    def test_clean_approval_reason(self):
        """Test cleaning and normalizing approval reasons."""
        # Test various formats
        self.assertEqual(clean_approval_reason("user was a bot"), "user was bot")
        self.assertEqual(clean_approval_reason("User was bot"), "User was bot")
        self.assertEqual(clean_approval_reason("no content change in last article"), "no content change")
        self.assertEqual(clean_approval_reason("user was auto-reviewed"), "user was autoreviewed")
        self.assertEqual(clean_approval_reason(""), "unknown reason")
        self.assertEqual(clean_approval_reason(None), "unknown reason")

    def test_validate_comment_length(self):
        """Test comment length validation and truncation."""
        short_comment = "This is a short comment"
        self.assertEqual(validate_comment_length(short_comment), short_comment)
        
        # Test truncation (create a very long comment)
        long_comment = "x" * 600
        truncated = validate_comment_length(long_comment)
        self.assertTrue(len(truncated) <= 500)
        self.assertIn("truncated", truncated)

    def test_group_consecutive_revisions(self):
        """Test grouping consecutive revision IDs."""
        # Test consecutive revisions
        self.assertEqual(group_consecutive_revisions([1, 2, 3]), [[1, 2, 3]])
        
        # Test non-consecutive revisions
        self.assertEqual(group_consecutive_revisions([1, 3, 5]), [[1], [3], [5]])
        
        # Test mixed consecutive and non-consecutive
        self.assertEqual(group_consecutive_revisions([1, 2, 5, 6, 7, 10]), [[1, 2], [5, 6, 7], [10]])
        
        # Test empty list
        self.assertEqual(group_consecutive_revisions([]), [])

    def test_format_revision_group(self):
        """Test formatting revision groups."""
        self.assertEqual(format_revision_group([12345]), "12345")
        self.assertEqual(format_revision_group([12345, 12346]), "12345, 12346")
        self.assertEqual(format_revision_group([12345, 12346, 12347]), "12345-12347")
        self.assertEqual(format_revision_group([12345, 12347, 12349]), "12345, 12347, 12349")
        self.assertEqual(format_revision_group([]), "")


class ApprovalProcessorTests(TestCase):
    """Test cases for approval processor functionality."""

    def test_process_and_approve_revisions_success(self):
        """Test successful processing and approval of revisions."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "user was bot"}},
        ]
        
        result = process_and_approve_revisions(results, dry_run=True)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["max_revid"], 12346)
        self.assertEqual(result["approved_count"], 2)
        self.assertEqual(result["total_count"], 2)
        self.assertTrue(result["dry_run"])
        self.assertIn("Successfully processed 2/2 revisions", result["message"])

    def test_process_and_approve_revisions_no_approvals(self):
        """Test processing when no revisions can be approved."""
        results = [
            {"revid": 12345, "decision": {"status": "blocked", "reason": "user was blocked"}},
        ]
        
        result = process_and_approve_revisions(results, dry_run=True)
        
        self.assertFalse(result["success"])
        self.assertIsNone(result["max_revid"])
        self.assertEqual(result["approved_count"], 0)
        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["message"], "No revisions can be approved")

    def test_preview_approval_comment(self):
        """Test preview functionality."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
        ]
        
        result = preview_approval_comment(results)
        
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["max_revid"], 12345)
        self.assertIn("rev_id 12345 approved because user was bot", result["comment"])

    def test_batch_process_pages(self):
        """Test batch processing of multiple pages."""
        pages_data = [
            {
                "pageid": 12345,
                "results": [
                    {"revid": 200, "decision": {"status": "approve", "reason": "user was bot"}},
                ]
            },
            {
                "pageid": 12346,
                "results": [
                    {"revid": 201, "decision": {"status": "approve", "reason": "user was bot"}},
                ]
            }
        ]
        
        result = batch_process_pages(pages_data, dry_run=True)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["total_pages"], 2)
        self.assertEqual(result["successful_pages"], 2)
        self.assertEqual(result["failed_pages"], 0)
        self.assertEqual(len(result["results"]), 2)

    def test_get_approval_statistics(self):
        """Test generating approval statistics."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12347, "decision": {"status": "blocked", "reason": "user was blocked"}},
            {"revid": 12348, "decision": {"status": "manual", "reason": "requires human review"}},
        ]
        
        stats = get_approval_statistics(results)
        
        self.assertEqual(stats["total_revisions"], 4)
        self.assertEqual(stats["approved_count"], 2)
        self.assertEqual(stats["blocked_count"], 1)
        self.assertEqual(stats["manual_count"], 1)
        self.assertEqual(stats["min_revid"], 12345)
        self.assertEqual(stats["max_revid"], 12348)
        self.assertEqual(stats["max_approvable_revid"], 12346)
        self.assertEqual(stats["approval_rate"], 50.0)

    def test_get_approval_statistics_empty(self):
        """Test generating statistics for empty results."""
        stats = get_approval_statistics([])
        
        self.assertEqual(stats["total_revisions"], 0)
        self.assertEqual(stats["approved_count"], 0)
        self.assertEqual(stats["approval_rate"], 0)
        self.assertIsNone(stats["min_revid"])
        self.assertIsNone(stats["max_revid"])
        self.assertIsNone(stats["max_approvable_revid"])

    def test_error_handling(self):
        """Test error handling in various functions."""
        # Test with invalid data
        invalid_results = [
            {"revid": 12345, "decision": {"status": "approve"}},  # Missing reason
        ]
        
        result = process_and_approve_revisions(invalid_results, dry_run=True)
        # The function should handle missing reason gracefully
        self.assertTrue(result["success"])  # Should still succeed but with "unknown reason"
        self.assertEqual(result["approved_count"], 1)


class ApprovalCommentIntegrationTests(TestCase):
    """Integration tests for approval comment functionality."""

    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        # Simulate autoreview results
        autoreview_results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "ORES score goodfaith=0.53, damaging: 0.251"}},
            {"revid": 12348, "decision": {"status": "blocked", "reason": "user was blocked"}},
        ]
        
        # Generate approval comment
        max_revid, comment = generate_approval_comment(autoreview_results, "Auto:")
        
        # Process with approval processor
        result = process_and_approve_revisions(autoreview_results, "Auto:", dry_run=True)
        
        # Get statistics
        stats = get_approval_statistics(autoreview_results)
        
        # Verify results
        self.assertEqual(max_revid, 12347)
        self.assertIn("Auto:", comment)
        self.assertTrue(result["success"])
        self.assertEqual(stats["approved_count"], 3)
        self.assertEqual(stats["blocked_count"], 1)
        self.assertEqual(stats["approval_rate"], 75.0)

    def test_batch_processing_workflow(self):
        """Test batch processing workflow."""
        pages_data = [
            {
                "pageid": 12345,
                "results": [
                    {"revid": 200, "decision": {"status": "approve", "reason": "user was bot"}},
                ]
            },
            {
                "pageid": 12346,
                "results": [
                    {"revid": 201, "decision": {"status": "blocked", "reason": "user was blocked"}},
                ]
            }
        ]
        
        # Process batch
        batch_result = batch_process_pages(pages_data, dry_run=True)
        
        # Verify results
        self.assertTrue(batch_result["success"])
        self.assertEqual(batch_result["total_pages"], 2)
        self.assertEqual(batch_result["successful_pages"], 1)  # Only first page has approvable revisions
        self.assertEqual(batch_result["failed_pages"], 1)
        
        # Check individual page results
        page_results = batch_result["results"]
        self.assertEqual(len(page_results), 2)
        
        # First page should be successful
        self.assertTrue(page_results[0]["success"])
        self.assertEqual(page_results[0]["pageid"], 12345)
        
        # Second page should fail (no approvable revisions)
        self.assertFalse(page_results[1]["success"])
        self.assertEqual(page_results[1]["pageid"], 12346)
