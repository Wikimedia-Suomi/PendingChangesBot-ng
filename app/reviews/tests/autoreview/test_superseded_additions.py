"""Tests for superseded additions check."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from reviews import autoreview


class SupersededAdditionsTests(TestCase):
    """Test suite for superseded additions detection."""

    def test_normalize_wikitext(self):
        """Test that wikitext normalization removes markup correctly."""
        text = "Some text with [[link|display]] and {{template}} and <ref>citation</ref>"
        normalized = autoreview._normalize_wikitext(text)
        self.assertEqual(normalized, "Some text with display and and")

    def test_normalize_wikitext_with_categories(self):
        """Test that category links are removed."""
        text = "Article text [[Category:Test]] more text"
        normalized = autoreview._normalize_wikitext(text)
        self.assertEqual(normalized, "Article text more text")

    def test_extract_additions_simple(self):
        """Test extracting additions from simple text change."""
        parent = "Original text."
        pending = "Original text. New addition."
        additions = autoreview._extract_additions(parent, pending)
        self.assertEqual(len(additions), 1)
        self.assertIn("New addition.", additions[0])

    def test_extract_additions_no_parent(self):
        """Test extraction when there is no parent revision."""
        parent = ""
        pending = "New article text."
        additions = autoreview._extract_additions(parent, pending)
        self.assertEqual(additions, ["New article text."])

    def test_extract_additions_multiple(self):
        """Test extracting multiple separate additions."""
        parent = "First paragraph. Third paragraph."
        pending = "First paragraph. Second paragraph. Third paragraph. Fourth paragraph."
        additions = autoreview._extract_additions(parent, pending)
        self.assertGreaterEqual(len(additions), 2)

    def test_is_addition_superseded_fully_removed(self):
        """Test case 1: Addition was fully removed in current stable."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article intro. User added this content about topic X. More text."
        )
        mock_revision.page = MagicMock()

        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = "Article intro. More text."

        with (
            patch("reviews.autoreview.utils.wikitext.get_parent_wikitext") as mock_parent,
            patch("reviews.models.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article intro. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            current_stable = "Article intro. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            self.assertTrue(result)

    def test_is_addition_superseded_partially_removed(self):
        """Test case 2: Addition was partially removed (majority removed)."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article text. User added a very long detailed sentence about "
            "topic X with lots of information and details here. More text."
        )
        mock_revision.page = MagicMock()

        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = "Article text. User added info. More text."

        with (
            patch("reviews.autoreview.utils.wikitext.get_parent_wikitext") as mock_parent,
            patch("reviews.models.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article text. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            current_stable = "Article text. User added info. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            self.assertTrue(result)

    def test_is_addition_superseded_content_still_present(self):
        """Test case 4: Addition content is still largely present (not superseded)."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = "Article text. User added information about X. More text."
        mock_revision.page = MagicMock()

        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = (
            "Article text. User added information about X. Even more text. More text."
        )

        with (
            patch("reviews.autoreview.utils.wikitext.get_parent_wikitext") as mock_parent,
            patch("reviews.models.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article text. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            current_stable = "Article text. User added information about X. Even more text. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            self.assertFalse(result)

