"""Tests for reference-only changes detection."""

import re
from unittest.mock import MagicMock

from django.test import TestCase

from reviews.autoreview import (
    _check_reference_only_changes,
    _extract_references,
    _is_reference_only_change,
    _remove_references,
    _normalize_whitespace,
)
from reviews.models import PendingPage, PendingRevision, Wiki


class ReferenceOnlyChangesTest(TestCase):
    def setUp(self):
        """Set up test data."""
        self.wiki = Wiki.objects.create(name="Test Wiki", code="test", family="wikipedia")
        self.page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=123,
            title="Test Page",
            stable_revid=100,
        )
        self.client = MagicMock()

    def test_extract_references(self):
        """Test reference extraction from wikitext."""
        wikitext = """
        Some content here.
        <ref>First reference</ref>
        More content.
        <ref name="test">Named reference</ref>
        <ref>Another reference</ref>
        """
        
        references = _extract_references(wikitext)
        self.assertEqual(len(references), 3)
        self.assertIn("<ref>First reference</ref>", references)
        self.assertIn('<ref name="test">Named reference</ref>', references)
        self.assertIn("<ref>Another reference</ref>", references)

    def test_extract_references_empty(self):
        """Test reference extraction from wikitext with no references."""
        wikitext = "Just some content without references."
        references = _extract_references(wikitext)
        self.assertEqual(len(references), 0)

    def test_remove_references(self):
        """Test removing references from wikitext."""
        wikitext = """
        Content before.
        <ref>Reference content</ref>
        Content after.
        <ref name="test">Named reference</ref>
        More content.
        """
        
        content_without_refs = _remove_references(wikitext)
        self.assertNotIn("<ref>", content_without_refs)
        self.assertNotIn("</ref>", content_without_refs)
        self.assertIn("Content before.", content_without_refs)
        self.assertIn("Content after.", content_without_refs)
        self.assertIn("More content.", content_without_refs)

    def test_remove_standalone_refs(self):
        """Test removing standalone reference tags."""
        wikitext = "Content <ref/> and <ref name='test'/> more content."
        content_without_refs = _remove_references(wikitext)
        self.assertNotIn("<ref/>", content_without_refs)
        self.assertNotIn("<ref name='test'/>", content_without_refs)
        self.assertIn("Content", content_without_refs)
        self.assertIn("more content.", content_without_refs)

    def test_normalize_whitespace(self):
        """Test whitespace normalization."""
        text = "  Multiple   spaces   and\ttabs  "
        normalized = _normalize_whitespace(text)
        self.assertEqual(normalized, "Multiple spaces and tabs")

    def test_is_reference_only_change_true(self):
        """Test detection of reference-only changes."""
        current_wikitext = "Content <ref>New reference</ref> more content."
        parent_wikitext = "Content more content."
        current_refs = ["<ref>New reference</ref>"]
        parent_refs = []
        
        result = _is_reference_only_change(current_wikitext, parent_wikitext, current_refs, parent_refs)
        self.assertTrue(result)

    def test_is_reference_only_change_false_content_changed(self):
        """Test that content changes are detected."""
        current_wikitext = "New content <ref>New reference</ref> more content."
        parent_wikitext = "Old content more content."
        current_refs = ["<ref>New reference</ref>"]
        parent_refs = []
        
        result = _is_reference_only_change(current_wikitext, parent_wikitext, current_refs, parent_refs)
        self.assertFalse(result)

    def test_is_reference_only_change_false_no_ref_changes(self):
        """Test that unchanged references are detected."""
        current_wikitext = "Content <ref>Same reference</ref> more content."
        parent_wikitext = "Content <ref>Same reference</ref> more content."
        current_refs = ["<ref>Same reference</ref>"]
        parent_refs = ["<ref>Same reference</ref>"]
        
        result = _is_reference_only_change(current_wikitext, parent_wikitext, current_refs, parent_refs)
        self.assertFalse(result)

    def test_reference_only_changes_detection(self):
        """Test the main reference-only changes detection function."""
        revision = PendingRevision.objects.create(
            page=self.page,
            revid=101,
            wikitext="Content <ref>New reference</ref> more content.",
            user_name="TestUser",
            sha1="testsha1",
        )
        
        # Mock parent wikitext to have no references
        with self.assertLogs('reviews.autoreview', level='DEBUG') as cm:
            result = _check_reference_only_changes(revision, self.client)
        
        self.assertEqual(result["status"], "manual")
        self.assertIn("only reference changes", result["message"])
        self.assertTrue(result["details"]["content_unchanged"])

    def test_reference_only_changes_with_content(self):
        """Test detection when content also changes."""
        revision = PendingRevision.objects.create(
            page=self.page,
            revid=101,
            wikitext="New content <ref>New reference</ref> more content.",
            user_name="TestUser",
            sha1="testsha1",
        )
        
        # Mock parent wikitext to have different content
        with self.assertLogs('reviews.autoreview', level='DEBUG') as cm:
            result = _check_reference_only_changes(revision, self.client)
        
        self.assertEqual(result["status"], "ok")
        self.assertIn("content changes beyond references", result["message"])

    def test_reference_only_changes_no_changes(self):
        """Test detection when no changes are made."""
        revision = PendingRevision.objects.create(
            page=self.page,
            revid=101,
            wikitext="Same content <ref>Same reference</ref> more content.",
            user_name="TestUser",
            sha1="testsha1",
        )
        
        # Mock parent wikitext to be the same
        with self.assertLogs('reviews.autoreview', level='DEBUG') as cm:
            result = _check_reference_only_changes(revision, self.client)
        
        self.assertEqual(result["status"], "ok")
        self.assertIn("content changes beyond references", result["message"])

    def test_reference_only_changes_error_handling(self):
        """Test error handling in reference-only changes detection."""
        revision = PendingRevision.objects.create(
            page=self.page,
            revid=101,
            wikitext="Some content",
            user_name="TestUser",
            sha1="testsha1",
        )
        
        # Mock client to raise an exception
        self.client.side_effect = Exception("Test error")
        
        with self.assertLogs('reviews.autoreview', level='ERROR') as cm:
            result = _check_reference_only_changes(revision, self.client)
        
        self.assertEqual(result["status"], "error")
        self.assertIn("Reference-only check failed", result["message"])

    def test_reference_pattern_matching(self):
        """Test reference pattern matching in wikitext."""
        test_cases = [
            ("<ref>Simple reference</ref>", ["<ref>Simple reference</ref>"]),
            ('<ref name="test">Named reference</ref>', ['<ref name="test">Named reference</ref>']),
            ("Multiple <ref>First</ref> and <ref>Second</ref> refs", 
             ["<ref>First</ref>", "<ref>Second</ref>"]),
            ("No references here", []),
            ("<ref>Multiline\nreference</ref>", ["<ref>Multiline\nreference</ref>"]),
        ]
        
        for wikitext, expected_refs in test_cases:
            with self.subTest(wikitext=wikitext):
                refs = re.findall(r'<ref[^>]*>.*?</ref>', wikitext, re.DOTALL | re.IGNORECASE)
                self.assertEqual(set(refs), set(expected_refs))
