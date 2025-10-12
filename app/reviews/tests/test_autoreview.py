"""Tests for autoreview logic, especially broken wikicode detection."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TestCase

from reviews.autoreview import (
    check_broken_wikicode,
    detect_broken_wikicode_indicators,
    get_localized_media_keywords,
    is_math_article,
)
from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class BrokenWikicodeDetectionTests(TestCase):
    """Test the broken wikicode indicator detection functions."""

    def test_detect_template_syntax(self):
        """Test detection of broken template syntax {{ }}."""
        html = "Some text {{Template}} and more {{Another}}"
        indicators = detect_broken_wikicode_indicators(html)
        self.assertEqual(indicators["{{"], 2)
        self.assertEqual(indicators["}}"], 2)

    def test_detect_internal_link_syntax(self):
        """Test detection of broken internal link syntax [[ ]]."""
        html = "Link to [[Page]] and [[Another Page]]"
        indicators = detect_broken_wikicode_indicators(html)
        self.assertEqual(indicators["[["], 2)
        self.assertEqual(indicators["]]"], 2)

    def test_detect_reference_tags(self):
        """Test detection of broken reference tags."""
        html = "Text with <ref>citation</ref> and <REF>another</REF>"
        indicators = detect_broken_wikicode_indicators(html)
        self.assertEqual(indicators["<ref"], 2)
        self.assertEqual(indicators["</ref"], 2)

    def test_detect_div_tags(self):
        """Test detection of broken div tags."""
        html = "Content <div>section</div> and <DIV>another</DIV>"
        indicators = detect_broken_wikicode_indicators(html)
        self.assertEqual(indicators["<div"], 2)
        self.assertEqual(indicators["</div"], 2)

    def test_detect_span_tags(self):
        """Test detection of broken span tags."""
        html = "Text <span>inline</span> and <SPAN>more</SPAN>"
        indicators = detect_broken_wikicode_indicators(html)
        self.assertEqual(indicators["<span"], 2)
        self.assertEqual(indicators["</span"], 2)

    def test_detect_file_syntax_english(self):
        """Test detection of broken File/Image syntax in English."""
        html = "Image [File:Example.jpg] and [Image:Another.png]"
        indicators = detect_broken_wikicode_indicators(html, "en")
        self.assertEqual(indicators["[File:"], 1)
        self.assertEqual(indicators["[Image:"], 1)

    def test_detect_category_syntax_english(self):
        """Test detection of broken Category syntax in English."""
        html = "Category [Category:Example] visible"
        indicators = detect_broken_wikicode_indicators(html, "en")
        self.assertEqual(indicators["[Category:"], 1)

    def test_detect_section_headers_non_math(self):
        """Test detection of == in non-math articles."""
        html = "Section == heading == visible"
        indicators = detect_broken_wikicode_indicators(html)
        self.assertGreater(indicators["=="], 0)

    def test_skip_section_headers_in_math_articles(self):
        """Test that == is not counted in math articles."""
        html = '<math>x == y</math> and more == stuff'
        indicators = detect_broken_wikicode_indicators(html)
        self.assertEqual(indicators.get("==", 0), 0)  # Should be skipped

    def test_empty_html_returns_empty_counter(self):
        """Test that empty HTML returns empty Counter."""
        indicators = detect_broken_wikicode_indicators("")
        self.assertEqual(len(indicators), 0)

    def test_clean_html_returns_mostly_zeros(self):
        """Test that clean HTML has no/minimal indicators."""
        html = "<p>This is clean HTML content without broken wikicode.</p>"
        indicators = detect_broken_wikicode_indicators(html)
        # Should have minimal or no indicators
        total = sum(indicators.values())
        self.assertEqual(total, 0)


class LocalizationTests(TestCase):
    """Test localized media keyword detection."""

    def test_get_english_keywords(self):
        """Test that English keywords are always included."""
        keywords = get_localized_media_keywords("en")
        self.assertIn("File", keywords)
        self.assertIn("Image", keywords)
        self.assertIn("Category", keywords)

    def test_get_finnish_localized_keywords(self):
        """Test Finnish localized keywords."""
        keywords = get_localized_media_keywords("fi")
        self.assertIn("Tiedosto", keywords)
        self.assertIn("Kuva", keywords)
        self.assertIn("Luokka", keywords)
        # English should also be present
        self.assertIn("File", keywords)

    def test_get_german_localized_keywords(self):
        """Test German localized keywords."""
        keywords = get_localized_media_keywords("de")
        self.assertIn("Datei", keywords)
        self.assertIn("Bild", keywords)
        self.assertIn("Kategorie", keywords)

    def test_detect_localized_file_syntax_finnish(self):
        """Test detection of Finnish file syntax."""
        html = "Image [Tiedosto:Esimerkki.jpg] visible"
        indicators = detect_broken_wikicode_indicators(html, "fi")
        self.assertEqual(indicators["[Tiedosto:"], 1)

    def test_detect_localized_category_syntax_finnish(self):
        """Test detection of Finnish category syntax."""
        html = "Category [Luokka:Esimerkki] visible"
        indicators = detect_broken_wikicode_indicators(html, "fi")
        self.assertEqual(indicators["[Luokka:"], 1)


class MathArticleDetectionTests(TestCase):
    """Test math article detection heuristics."""

    def test_detect_math_tag(self):
        """Test detection of <math> tags."""
        html = '<p>Formula: <math>x^2 + y^2 = z^2</math></p>'
        self.assertTrue(is_math_article(html))

    def test_detect_math_tag_case_insensitive(self):
        """Test detection of <MATH> tags (case insensitive)."""
        html = '<p>Formula: <MATH>x = y</MATH></p>'
        self.assertTrue(is_math_article(html))

    def test_detect_latex_style_math(self):
        """Test detection of LaTeX-style math $...$."""
        html = '<p>Inline math $x + y = z$ in text</p>'
        self.assertTrue(is_math_article(html))

    def test_detect_mathematical_symbols(self):
        """Test detection of mathematical symbols."""
        html = '<p>Sum ∑ and integral ∫</p>'
        self.assertTrue(is_math_article(html))

    def test_non_math_article(self):
        """Test that regular articles are not marked as math."""
        html = '<p>This is a regular article about history.</p>'
        self.assertFalse(is_math_article(html))


class BrokenWikicodeCheckTests(TestCase):
    """Test the integrated broken wikicode check."""

    def setUp(self):
        """Set up test wiki and pages."""
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            api_endpoint="https://test.example/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

        self.page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=123,
            title="Test Page",
            stable_revid=1000,
        )

    @mock.patch.object(PendingRevision, "get_rendered_html")
    def test_no_broken_wikicode(self, mock_html):
        """Test revision with no broken wikicode."""
        mock_html.return_value = "<p>Clean HTML content</p>"

        revision = PendingRevision.objects.create(
            page=self.page,
            revid=1001,
            timestamp="2025-01-01T00:00:00Z",
            wikitext="Test",
            sha1="abc123",
            age_at_fetch=timedelta(minutes=5),
        )

        result = check_broken_wikicode(revision, None)
        self.assertEqual(result["id"], "broken-wikicode")
        self.assertEqual(result["status"], "ok")
        self.assertIn("No broken wikicode", result["message"])

    @mock.patch.object(PendingRevision, "get_rendered_html")
    def test_new_broken_wikicode_detected(self, mock_html):
        """Test detection of newly introduced broken wikicode."""
        # Parent has no indicators
        parent = PendingRevision.objects.create(
            page=self.page,
            revid=1000,
            timestamp="2025-01-01T00:00:00Z",
            wikitext="Clean",
            sha1="abc123",
            age_at_fetch=timedelta(minutes=5),
        )

        # Current revision has broken wikicode
        current = PendingRevision.objects.create(
            page=self.page,
            revid=1001,
            timestamp="2025-01-01T00:01:00Z",
            wikitext="Broken {{Template",
            sha1="def456",
            age_at_fetch=timedelta(minutes=5),
        )

        # Mock HTML responses
        def html_side_effect():
            # This is called twice - first for current, then for parent
            # We need to differentiate which one is being called
            # The mock is called as a bound method, so we check call count
            call_count = mock_html.call_count
            if call_count == 1:  # First call is for current revision
                return "<p>Broken {{Template content</p>"
            else:  # Second call is for parent revision
                return "<p>Clean content</p>"

        mock_html.side_effect = html_side_effect

        result = check_broken_wikicode(current, parent)
        self.assertEqual(result["id"], "broken-wikicode")
        self.assertEqual(result["status"], "fail")
        self.assertIn("New broken wikicode detected", result["message"])
        self.assertIn("{{", result["message"])

    @mock.patch.object(PendingRevision, "get_rendered_html")
    def test_existing_broken_wikicode_not_increased(self, mock_html):
        """Test that existing broken wikicode (not increased) is reported as OK."""
        parent = PendingRevision.objects.create(
            page=self.page,
            revid=1000,
            timestamp="2025-01-01T00:00:00Z",
            wikitext="{{Template",
            sha1="abc123",
            age_at_fetch=timedelta(minutes=5),
        )

        current = PendingRevision.objects.create(
            page=self.page,
            revid=1001,
            timestamp="2025-01-01T00:01:00Z",
            wikitext="{{Template",  # Same broken wikicode
            sha1="def456",
            age_at_fetch=timedelta(minutes=5),
        )

        # Both have same broken wikicode
        mock_html.return_value = "<p>{{Template content</p>"

        result = check_broken_wikicode(current, parent)
        self.assertEqual(result["id"], "broken-wikicode")
        self.assertEqual(result["status"], "ok")
        self.assertIn("no new ones introduced", result["message"])

    @mock.patch.object(PendingRevision, "get_rendered_html")
    def test_no_parent_with_indicators_shows_warning(self, mock_html):
        """Test that indicators without parent show warning."""
        mock_html.return_value = "<p>Broken {{Template content</p>"

        revision = PendingRevision.objects.create(
            page=self.page,
            revid=1001,
            timestamp="2025-01-01T00:00:00Z",
            wikitext="{{Template",
            sha1="abc123",
            age_at_fetch=timedelta(minutes=5),
        )

        result = check_broken_wikicode(revision, None)
        self.assertEqual(result["id"], "broken-wikicode")
        self.assertEqual(result["status"], "warning")
        self.assertIn("no parent revision to compare", result["message"])


class RealWorldExamplesTests(TestCase):
    """Test with real-world broken wikicode examples from the issue."""

    def test_finnish_wikipedia_riihimaki_example(self):
        """Test detection based on the Riihimäki example."""
        # From: https://fi.wikipedia.org/w/index.php?title=Riihimäki&oldid=23392595
        html = '''
        <p>Riihimäki {{cite web|url=http://example.com}} is a town</p>
        '''
        indicators = detect_broken_wikicode_indicators(html, "fi")
        self.assertGreater(indicators["{{"], 0)
        self.assertGreater(indicators["}}"], 0)

    def test_finnish_wikipedia_bracket_example(self):
        """Test detection based on the bracket example."""
        # From: https://fi.wikipedia.org/wiki/Luettelo_valtionpäämiesten_virkasyytteistä
        html = '''
        <p>Some content ]] visible in the text</p>
        '''
        indicators = detect_broken_wikicode_indicators(html, "fi")
        self.assertGreater(indicators["]]"], 0)
