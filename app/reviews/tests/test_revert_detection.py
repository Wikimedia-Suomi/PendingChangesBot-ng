"""
Tests for revert detection functionality.

This module tests the revert detection check that identifies when
a pending edit is a revert to previously reviewed content.
"""

import json
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from reviews.autoreview import (
    _check_revert_detection,
    _find_reviewed_revisions_by_sha1,
    _parse_revert_params,
)
from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration
from reviews.services import WikiClient


class RevertDetectionTests(TestCase):
    """Test cases for revert detection functionality."""

    def setUp(self):
        """Set up test data."""
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        self.config = WikiConfiguration.objects.create(wiki=self.wiki)

        self.page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=12345,
            title="Test Page",
            stable_revid=100,
        )

        self.revision = PendingRevision.objects.create(
            page=self.page,
            revid=200,
            parentid=150,
            user_name="TestUser",
            user_id=1000,
            change_tags=["mw-manual-revert"],
            timestamp=timezone.now(),
            fetched_at=timezone.now(),
            age_at_fetch=0.0,
            sha1="test_sha1",
            wikitext="test wikitext",
        )
        self.revision.change_tag_params = [
            json.dumps(
                {
                    "revertId": 200,
                    "oldestRevertedRevId": 180,
                    "newestRevertedRevId": 190,
                    "originalRevisionId": 175,
                }
            )
        ]
        self.revision.save()

        self.client = Mock(spec=WikiClient)
        self.client.site = Mock()

    def test_revert_detection_disabled(self):
        """Test that revert detection is skipped when disabled."""
        with self.settings(ENABLE_REVERT_DETECTION=False):
            result = _check_revert_detection(self.revision, self.client)

            self.assertEqual(result["status"], "skip")
            self.assertEqual(result["message"], "Revert detection is disabled")

    def test_no_revert_tags(self):
        """Test that revert detection is skipped when no revert tags are present."""
        self.revision.change_tags = ["mw-edit"]
        self.revision.save()

        result = _check_revert_detection(self.revision, self.client)

        self.assertEqual(result["status"], "skip")
        self.assertEqual(result["message"], "No revert tags found")

    def test_parse_revert_params(self):
        """Test parsing of change tag parameters."""
        reverted_ids = _parse_revert_params(self.revision)

        expected_ids = [180, 190, 175]  # From change_tag_params
        self.assertEqual(set(reverted_ids), set(expected_ids))

    def test_parse_revert_params_empty(self):
        """Test parsing when no change tag parameters are present."""
        self.revision.change_tag_params = []
        self.revision.save()

        reverted_ids = _parse_revert_params(self.revision)
        self.assertEqual(reverted_ids, [])

    def test_parse_revert_params_invalid_json(self):
        """Test parsing with invalid JSON in change tag parameters."""
        self.revision.change_tag_params = ["invalid json"]
        self.revision.save()

        reverted_ids = _parse_revert_params(self.revision)
        self.assertEqual(reverted_ids, [])

    @patch("reviews.autoreview.SupersetQuery")
    def test_find_reviewed_revisions_by_sha1_success(self, mock_superset):
        """Test finding reviewed revisions by SHA1."""
        # Mock SupersetQuery results
        mock_superset.return_value.query.return_value = [
            {
                "content_sha1": "abc123",
                "max_old_reviewed_id": 150,
                "max_reviewable_rev_id_by_sha1": 180,
                "rev_page": 12345,
            }
        ]

        reverted_ids = [180, 190]
        reviewed_revisions = _find_reviewed_revisions_by_sha1(self.client, self.page, reverted_ids)

        self.assertEqual(len(reviewed_revisions), 1)
        self.assertEqual(reviewed_revisions[0]["sha1"], "abc123")
        self.assertEqual(reviewed_revisions[0]["max_reviewed_id"], 150)

    @patch("reviews.autoreview.SupersetQuery")
    def test_find_reviewed_revisions_by_sha1_no_results(self, mock_superset):
        """Test when no reviewed revisions are found."""
        mock_superset.return_value.query.return_value = []

        reverted_ids = [180, 190]
        reviewed_revisions = _find_reviewed_revisions_by_sha1(self.client, self.page, reverted_ids)

        self.assertEqual(reviewed_revisions, [])

    @patch("reviews.autoreview._find_reviewed_revisions_by_sha1")
    def test_revert_detection_approve(self, mock_find_reviewed):
        """Test revert detection when revert to reviewed content is found."""
        # Mock finding reviewed revisions
        mock_find_reviewed.return_value = [
            {"sha1": "abc123", "max_reviewed_id": 150, "max_reviewable_id": 180, "page_id": 12345}
        ]

        result = _check_revert_detection(self.revision, self.client)

        self.assertEqual(result["status"], "approve")
        self.assertIn("Revert to previously reviewed content", result["message"])
        self.assertIn("abc123", result["message"])

    @patch("reviews.autoreview._find_reviewed_revisions_by_sha1")
    def test_revert_detection_block(self, mock_find_reviewed):
        """Test revert detection when no reviewed content is found."""
        # Mock no reviewed revisions found
        mock_find_reviewed.return_value = []

        result = _check_revert_detection(self.revision, self.client)

        self.assertEqual(result["status"], "block")
        self.assertEqual(
            result["message"], "Revert detected but no previously reviewed content found"
        )

    def test_revert_detection_no_reverted_ids(self):
        """Test revert detection when no reverted revision IDs are found."""
        self.revision.change_tag_params = []
        self.revision.save()

        result = _check_revert_detection(self.revision, self.client)

        self.assertEqual(result["status"], "skip")
        self.assertEqual(result["message"], "No reverted revision IDs found in change tags")

    def test_revert_detection_metadata(self):
        """Test that revert detection returns proper metadata."""
        with patch("reviews.autoreview._find_reviewed_revisions_by_sha1") as mock_find:
            mock_find.return_value = [{"sha1": "abc123"}]

            result = _check_revert_detection(self.revision, self.client)

            self.assertIn("reverted_rev_ids", result["metadata"])
            self.assertIn("revert_tags", result["metadata"])
            self.assertIn("reviewed_revisions", result["metadata"])
            self.assertEqual(result["metadata"]["revert_tags"], ["mw-manual-revert"])


class RevertDetectionIntegrationTests(TestCase):
    """Integration tests for revert detection with real data."""

    def setUp(self):
        """Set up integration test data."""
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        self.config = WikiConfiguration.objects.create(wiki=self.wiki)

    def test_revert_detection_with_real_revision(self):
        """Test revert detection with a real revision setup."""
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=12345,
            title="Test Page",
            stable_revid=100,
        )

        # Create a revision with revert tags
        revision = PendingRevision.objects.create(
            page=page,
            revid=200,
            parentid=150,
            user_name="TestUser",
            user_id=1000,
            change_tags=["mw-manual-revert", "mw-reverted"],
            timestamp=timezone.now(),
            fetched_at=timezone.now(),
            age_at_fetch=0.0,
            sha1="test_sha1",
            wikitext="test wikitext",
        )
        revision.change_tag_params = [
            json.dumps(
                {
                    "revertId": 200,
                    "oldestRevertedRevId": 180,
                    "newestRevertedRevId": 190,
                    "originalRevisionId": 175,
                }
            )
        ]
        revision.save()

        # Mock the client
        client = Mock(spec=WikiClient)
        client.site = Mock()

        # Test with SupersetQuery mock
        with patch("reviews.autoreview.SupersetQuery") as mock_superset:
            mock_superset.return_value.query.return_value = [
                {
                    "content_sha1": "test_sha1",
                    "max_old_reviewed_id": 150,
                    "max_reviewable_rev_id_by_sha1": 180,
                    "rev_page": 12345,
                }
            ]

            result = _check_revert_detection(revision, client)

            self.assertEqual(result["status"], "approve")
            self.assertIn("test_sha1", result["message"])
            self.assertEqual(len(result["metadata"]["reverted_rev_ids"]), 3)
            self.assertEqual(len(result["metadata"]["revert_tags"]), 2)
