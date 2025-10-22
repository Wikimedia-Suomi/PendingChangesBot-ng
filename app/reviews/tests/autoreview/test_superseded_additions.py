"""Tests for superseded additions check."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from reviews.autoreview.utils.similarity import is_addition_superseded
from reviews.autoreview.utils.wikitext import extract_additions, normalize_wikitext


class SupersededAdditionsTests(TestCase):
    """Test suite for superseded additions detection."""

    def test_normalize_wikitext(self):
        """Test that wikitext normalization removes markup correctly."""
        text = "Some text with [[link|display]] and {{template}} and <ref>citation</ref>"
        normalized = normalize_wikitext(text)
        self.assertEqual(normalized, "Some text with display and and")

    def test_normalize_wikitext_with_categories(self):
        """Test that category links are removed."""
        text = "Article text [[Category:Test]] more text"
        normalized = normalize_wikitext(text)
        self.assertEqual(normalized, "Article text more text")

    def test_extract_additions_simple(self):
        """Test extracting additions from simple text change."""
        parent = "Original text."
        pending = "Original text. New addition."
        additions = extract_additions(parent, pending)
        self.assertEqual(len(additions), 1)
        self.assertIn("New addition.", additions[0])

    def test_extract_additions_no_parent(self):
        """Test extraction when there is no parent revision."""
        parent = ""
        pending = "New article text."
        additions = extract_additions(parent, pending)
        self.assertEqual(additions, ["New article text."])

    def test_extract_additions_multiple(self):
        """Test extracting multiple separate additions."""
        parent = "First paragraph. Third paragraph."
        pending = "First paragraph. Second paragraph. Third paragraph. Fourth paragraph."
        additions = extract_additions(parent, pending)
        self.assertGreaterEqual(len(additions), 2)

    def test_is_addition_superseded_fully_removed(self):
        """Test case 1: Addition was fully removed in current stable."""
        mock_revision = MagicMock()
        mock_revision.page.wiki.code = "fi"
        mock_revision.parent_wikitext = "Original text"
        mock_revision.wikitext = "Original text New addition here"
        mock_revision.get_wikitext.return_value = "Original text New addition here"
        mock_revision.parentid = None

        current_stable = "Original text"
        threshold = 0.7

        result = is_addition_superseded(mock_revision, current_stable, threshold)

        self.assertTrue(result)

    def test_is_addition_superseded_partially_removed(self):
        """Test case 2: Addition was partially removed (majority removed)."""
        mock_revision = MagicMock()
        mock_revision.page.wiki.code = "fi"
        mock_revision.parent_wikitext = "Original text."
        mock_revision.wikitext = "Original text. Addition of many words and sentences here."
        mock_revision.get_wikitext.return_value = (
            "Original text. Addition of many words and sentences here."
        )
        mock_revision.parentid = None

        current_stable = "Original text. Addition of"
        threshold = 0.7

        result = is_addition_superseded(mock_revision, current_stable, threshold)

        self.assertTrue(result)

    def test_is_addition_superseded_content_still_present(self):
        """Test case 4: Addition content is still largely present (not superseded)."""
        mock_revision = MagicMock()
        mock_revision.page.wiki.code = "fi"
        mock_revision.parent_wikitext = "Original text."
        mock_revision.wikitext = "Original text. New section with important details."
        mock_revision.get_wikitext.return_value = (
            "Original text. New section with important details."
        )
        mock_revision.parentid = None  # No parent means extract_additions will return the full text

        current_stable = "Original text. New section with important details."
        threshold = 0.7

        result = is_addition_superseded(mock_revision, current_stable, threshold)

        self.assertFalse(result)
