"""
Tests for approval utility function.
This module tests the generate_approval_comment function that
determines the highest approvable revision ID and generates consolidated approval comments.
"""

from django.test import TestCase

from reviews.utils.approval_comment import generate_approval_comment


class ApprovalUtilityTests(TestCase):
    """Test cases for the approval utility function."""

    def test_no_approved_revisions(self):
        """Test when no revisions can be approved."""
        results = [
            {"revid": 12345, "decision": {"status": "blocked", "reason": "user was blocked"}},
            {"revid": 12346, "decision": {"status": "manual", "reason": "requires human review"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertIsNone(rev_id)
        self.assertEqual(comment, "No revisions can be approved")

    def test_single_approved_revision(self):
        """Test with a single approved revision."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12345)
        self.assertEqual(comment, "rev_id 12345 approved because user was bot")

    def test_multiple_approved_revisions_same_reason(self):
        """Test with multiple approved revisions having the same reason."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was bot"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12347)  # Highest revision ID
        self.assertEqual(comment, "rev_id 12345, 12346, 12347 approved because user was bot")

    def test_multiple_approved_revisions_different_reasons(self):
        """Test with multiple approved revisions having different reasons."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {
                "revid": 12346,
                "decision": {"status": "approve", "reason": "no content change in last article"},
            },
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12347)  # Highest revision ID
        # Check that all reasons are included
        self.assertIn("rev_id 12345 approved because user was bot", comment)
        self.assertIn("rev_id 12346 approved because no content change", comment)
        self.assertIn("rev_id 12347 approved because user was autoreviewed", comment)

    def test_mixed_approved_and_non_approved_revisions(self):
        """Test with mix of approved and non-approved revisions."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "blocked", "reason": "user was blocked"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
            {"revid": 12348, "decision": {"status": "manual", "reason": "requires human review"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12347)  # Highest approved revision ID
        self.assertIn("rev_id 12345 approved because user was bot", comment)
        self.assertIn("rev_id 12347 approved because user was autoreviewed", comment)
        self.assertNotIn("user was blocked", comment)
        self.assertNotIn("requires human review", comment)

    def test_ores_score_approval_reason(self):
        """Test with ORES score approval reason."""
        results = [
            {
                "revid": 12345,
                "decision": {
                    "status": "approve",
                    "reason": "ORES score goodfaith=0.53, damaging: 0.251",
                },
            },
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12345)
        self.assertEqual(
            comment, "rev_id 12345 approved because ORES score goodfaith=0.53, damaging: 0.251"
        )

    def test_revert_detection_approval_reason(self):
        """Test with revert detection approval reason."""
        results = [
            {
                "revid": 12345,
                "decision": {
                    "status": "approve",
                    "reason": "Revert to previously reviewed content (SHA1: abc123)",
                },
            },
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12345)
        self.assertEqual(
            comment,
            "rev_id 12345 approved because Revert to previously reviewed content (SHA1: abc123)",
        )

    def test_consecutive_revisions_same_reason_grouping(self):
        """Test that consecutive revisions with same reason are grouped properly."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
            {"revid": 12348, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
            {"revid": 12349, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12349)  # Highest revision ID
        self.assertIn("rev_id 12345, 12346 approved because user was bot", comment)
        self.assertIn("rev_id 12347, 12348, 12349 approved because user was autoreviewed", comment)

    def test_non_consecutive_revisions_same_reason(self):
        """Test with non-consecutive revisions having the same reason."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12349, "decision": {"status": "approve", "reason": "user was bot"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12349)  # Highest revision ID
        self.assertEqual(comment, "rev_id 12345, 12347, 12349 approved because user was bot")

    def test_empty_results(self):
        """Test with empty results list."""
        results = []

        rev_id, comment = generate_approval_comment(results)

        self.assertIsNone(rev_id)
        self.assertEqual(comment, "No revisions can be approved")

    def test_comment_format_example_from_issue(self):
        """Test the specific example format mentioned in the issue."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {
                "revid": 12346,
                "decision": {"status": "approve", "reason": "no content change in last article"},
            },
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
            {"revid": 12348, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
            {
                "revid": 12349,
                "decision": {
                    "status": "approve",
                    "reason": "ORES score goodfaith=0.53, damaging: 0.251",
                },
            },
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12349)
        # Verify the format matches the issue example
        expected_parts = [
            "rev_id 12345 approved because user was bot",
            "rev_id 12346 approved because no content change",
            "rev_id 12347, 12348 approved because user was autoreviewed",
            "rev_id 12349 approved because ORES score goodfaith=0.53, damaging: 0.251",
        ]

        for part in expected_parts:
            self.assertIn(part, comment)

        # Verify the comment is properly formatted with commas
        self.assertEqual(comment, ", ".join(expected_parts))

    def test_revision_id_sorting(self):
        """Test that revision IDs are properly sorted in comments."""
        results = [
            {"revid": 12349, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "user was bot"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12349)  # Highest revision ID
        self.assertEqual(comment, "rev_id 12345, 12347, 12349 approved because user was bot")

    def test_edge_case_single_revision_with_long_reason(self):
        """Test edge case with single revision having a very long approval reason."""
        long_reason = (
            "This is a very long approval reason that might contain special characters "
            "like @#$%^&*() and numbers 123456789"
        )
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": long_reason}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12345)
        self.assertEqual(comment, f"rev_id 12345 approved because {long_reason}")

    def test_multiple_groups_with_single_revisions(self):
        """Test multiple groups where each group has only one revision."""
        results = [
            {"revid": 12345, "decision": {"status": "approve", "reason": "reason A"}},
            {"revid": 12346, "decision": {"status": "approve", "reason": "reason B"}},
            {"revid": 12347, "decision": {"status": "approve", "reason": "reason C"}},
        ]

        rev_id, comment = generate_approval_comment(results)

        self.assertEqual(rev_id, 12347)
        self.assertIn("rev_id 12345 approved because reason A", comment)
        self.assertIn("rev_id 12346 approved because reason B", comment)
        self.assertIn("rev_id 12347 approved because reason C", comment)
