"""Tests for broken wikicode detection."""

from __future__ import annotations

from collections import Counter
from unittest import mock

from django.test import TestCase

from reviews.autoreview.utils.broken_wikicode import (
    check_broken_wikicode,
    detect_broken_wikicode_indicators,
    get_localized_media_keywords,
    get_visible_text,
    is_math_article,
)


class GetVisibleTextTests(TestCase):
    """Test visible text extraction from HTML."""

    def test_get_visible_text_basic(self):
        """Test basic visible text extraction."""
        html = "<html><body><p>Hello World</p></body></html>"
        result = get_visible_text(html)
        self.assertIn("Hello World", result)

    def test_get_visible_text_removes_script_tags(self):
        """Test that script tags are removed."""
        html = "<html><body><p>Visible</p><script>alert('hidden');</script></body></html>"
        result = get_visible_text(html)
        self.assertIn("Visible", result)
        self.assertNotIn("alert", result)
        self.assertNotIn("hidden", result)

    def test_get_visible_text_removes_style_tags(self):
        """Test that style tags are removed."""
        html = "<html><body><p>Visible</p><style>.class { color: red; }</style></body></html>"
        result = get_visible_text(html)
        self.assertIn("Visible", result)
        self.assertNotIn("color", result)

    def test_get_visible_text_removes_code_blocks(self):
        """Test that code blocks are excluded to avoid false positives."""
        html = "<html><body><p>Text</p><code>{{ template }}</code></body></html>"
        result = get_visible_text(html)
        self.assertIn("Text", result)
        self.assertNotIn("{{", result)
        self.assertNotIn("template", result)

    def test_get_visible_text_removes_pre_tags(self):
        """Test that pre tags are excluded."""
        html = "<html><body><p>Text</p><pre>[[link]]</pre></body></html>"
        result = get_visible_text(html)
        self.assertIn("Text", result)
        self.assertNotIn("[[", result)

    def test_get_visible_text_removes_tt_tags(self):
        """Test that tt (teletype) tags are excluded."""
        html = "<html><body><p>Text</p><tt>&lt;ref&gt;</tt></body></html>"
        result = get_visible_text(html)
        self.assertIn("Text", result)
        # Should not contain the ref tag from tt element

    def test_get_visible_text_removes_syntaxhighlight_tags(self):
        """Test that syntaxhighlight tags are excluded."""
        html = '<html><body><p>Text</p><syntaxhighlight lang="python">def foo(): pass</syntaxhighlight></body></html>'
        result = get_visible_text(html)
        self.assertIn("Text", result)
        self.assertNotIn("def foo", result)

    def test_get_visible_text_empty_input(self):
        """Test that empty input returns empty string."""
        result = get_visible_text("")
        self.assertEqual(result, "")

    def test_get_visible_text_none_input(self):
        """Test that None input returns empty string."""
        result = get_visible_text(None)
        self.assertEqual(result, "")


class IsMathArticleTests(TestCase):
    """Test math article detection."""

    def test_is_math_article_with_math_class(self):
        """Test detection via math class attribute."""
        html = '<html><body><span class="mw-math">E = mc²</span></body></html>'
        self.assertTrue(is_math_article(html))

    def test_is_math_article_with_math_tag(self):
        """Test detection via math tag."""
        html = "<html><body><math>x = y</math></body></html>"
        self.assertTrue(is_math_article(html))

    def test_is_math_article_with_latex_backslash(self):
        """Test detection via LaTeX backslash."""
        html = r"<html><body><p>Formula: \frac{a}{b}</p></body></html>"
        self.assertTrue(is_math_article(html))

    def test_is_math_article_with_dollar_sign(self):
        """Test detection via dollar sign (inline math)."""
        html = "<html><body><p>Inline math: $x = 2$</p></body></html>"
        self.assertTrue(is_math_article(html))

    def test_is_math_article_false_for_regular_article(self):
        """Test that regular articles are not detected as math."""
        html = "<html><body><p>This is a regular article about history.</p></body></html>"
        self.assertFalse(is_math_article(html))

    def test_is_math_article_empty_input(self):
        """Test that empty input returns False."""
        self.assertFalse(is_math_article(""))

    def test_is_math_article_none_input(self):
        """Test that None input returns False."""
        self.assertFalse(is_math_article(None))


class GetLocalizedMediaKeywordsTests(TestCase):
    """Test localized media keyword retrieval."""

    def test_get_localized_media_keywords_english(self):
        """Test English keywords."""
        keywords = get_localized_media_keywords("en")
        self.assertEqual(keywords, ["File", "Image", "Category"])

    def test_get_localized_media_keywords_finnish(self):
        """Test Finnish keywords."""
        keywords = get_localized_media_keywords("fi")
        self.assertEqual(keywords, ["Tiedosto", "Kuva", "Luokka"])

    def test_get_localized_media_keywords_german(self):
        """Test German keywords."""
        keywords = get_localized_media_keywords("de")
        self.assertEqual(keywords, ["Datei", "Bild", "Kategorie"])

    def test_get_localized_media_keywords_french(self):
        """Test French keywords."""
        keywords = get_localized_media_keywords("fr")
        self.assertEqual(keywords, ["Fichier", "Image", "Catégorie"])

    def test_get_localized_media_keywords_unknown_language(self):
        """Test that unknown language defaults to English."""
        keywords = get_localized_media_keywords("unknown")
        self.assertEqual(keywords, ["File", "Image", "Category"])


class DetectBrokenWikicodeIndicatorsTests(TestCase):
    """Test broken wikicode indicator detection."""

    def test_detect_template_syntax(self):
        """Test detection of template syntax {{}}."""
        html = "<html><body><p>Text with {{ template syntax }}</p></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertEqual(result["{{"], 1)
        self.assertEqual(result["}}"], 1)

    def test_detect_link_syntax(self):
        """Test detection of internal link syntax [[]]."""
        html = "<html><body><p>Text with [[ link syntax ]]</p></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertEqual(result["[["], 1)
        self.assertEqual(result["]]"], 1)

    def test_detect_ref_tags(self):
        """Test detection of broken ref tags."""
        html = "<html><body><p>Text with &lt;ref&gt;citation&lt;/ref&gt;</p></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertGreater(result["<ref"], 0)
        self.assertGreater(result["</ref"], 0)

    def test_detect_div_tags(self):
        """Test detection of broken div tags."""
        html = "<html><body><p>Text with &lt;div&gt;content&lt;/div&gt;</p></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertGreater(result["<div"], 0)
        self.assertGreater(result["</div"], 0)

    def test_detect_span_tags(self):
        """Test detection of broken span tags."""
        html = "<html><body><p>Text with &lt;span&gt;content&lt;/span&gt;</p></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertGreater(result["<span"], 0)
        self.assertGreater(result["</span"], 0)

    def test_detect_file_syntax_english(self):
        """Test detection of broken File: syntax in English."""
        html = "<html><body><p>Text with [File:example.jpg]</p></body></html>"
        result = detect_broken_wikicode_indicators(html, wiki_lang="en")
        self.assertGreater(result["[File:"], 0)

    def test_detect_category_syntax_finnish(self):
        """Test detection of broken Category: syntax in Finnish."""
        html = "<html><body><p>Teksti [Luokka:esimerkki]</p></body></html>"
        result = detect_broken_wikicode_indicators(html, wiki_lang="fi")
        self.assertGreater(result["[Luokka:"], 0)

    def test_section_headers_not_detected_in_math_articles(self):
        """Test that == is not flagged in math articles."""
        html = '<html><body><p class="mw-math">x == y</p></body></html>'
        result = detect_broken_wikicode_indicators(html)
        self.assertEqual(result["=="], 0)

    def test_section_headers_detected_in_regular_articles(self):
        """Test that == is flagged in regular articles."""
        html = "<html><body><p>Text with == section header ==</p></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertGreater(result["=="], 0)

    def test_code_blocks_excluded(self):
        """Test that indicators in code blocks are not counted."""
        html = "<html><body><p>Regular text</p><code>{{ not counted }}</code></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertEqual(result["{{"], 0)

    def test_empty_html_returns_empty_counter(self):
        """Test that empty HTML returns empty Counter."""
        result = detect_broken_wikicode_indicators("")
        self.assertEqual(result, Counter())

    def test_multiple_indicators(self):
        """Test detection of multiple different indicators."""
        html = "<html><body><p>{{ template }} [[ link ]] &lt;ref&gt;cite&lt;/ref&gt;</p></body></html>"
        result = detect_broken_wikicode_indicators(html)
        self.assertGreater(result["{{"], 0)
        self.assertGreater(result["[["], 0)
        self.assertGreater(result["<ref"], 0)


class CheckBrokenWikicodeTests(TestCase):
    """Test broken wikicode check with threshold logic."""

    def test_no_broken_wikicode_in_clean_html(self):
        """Test that clean HTML returns no broken wikicode."""
        html = "<html><body><p>This is a clean article with no broken syntax.</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None)
        self.assertFalse(has_broken)
        self.assertEqual(details, "")

    def test_single_indicator_low_count_ignored(self):
        """Test that single indicator with low count (<3) is ignored as noise."""
        html = "<html><body><p>One {{ template</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None)
        self.assertFalse(has_broken)

    def test_single_indicator_high_count_detected(self):
        """Test that single indicator with count >= 3 is detected."""
        html = "<html><body><p>{{ one {{ two {{ three</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None)
        self.assertTrue(has_broken)
        self.assertIn("{{", details)

    def test_multiple_indicator_types_detected(self):
        """Test that multiple indicator types (2+) are detected."""
        html = "<html><body><p>{{ template [[ link</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None)
        self.assertTrue(has_broken)
        self.assertIn("{{", details)
        self.assertIn("[[", details)

    def test_compares_with_parent_html(self):
        """Test that only NEW indicators are flagged when parent exists."""
        parent_html = "<html><body><p>{{ existing template</p></body></html>"
        current_html = "<html><body><p>{{ existing {{ new {{ another {{ fourth</p></body></html>"
        has_broken, details = check_broken_wikicode(current_html, parent_html)
        # Parent has 1, current has 4, so NEW count is 3 (4-1=3)
        # Need NEW count >= 3 to trigger for single type
        self.assertTrue(has_broken)

    def test_no_new_indicators_compared_to_parent(self):
        """Test that pre-existing indicators are not flagged."""
        parent_html = "<html><body><p>{{ template [[ link <ref>cite</ref></p></body></html>"
        current_html = parent_html  # Same content
        has_broken, details = check_broken_wikicode(current_html, parent_html)
        self.assertFalse(has_broken)

    def test_details_message_format(self):
        """Test that details message has correct format."""
        html = "<html><body><p>{{ one {{ two [[ link</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None)
        self.assertTrue(has_broken)
        self.assertIn("Introduced broken wikicode:", details)
        self.assertIn("{{: 2", details)
        self.assertIn("[[: 1", details)

    def test_empty_current_html(self):
        """Test that empty current HTML returns no broken wikicode."""
        has_broken, details = check_broken_wikicode("", None)
        self.assertFalse(has_broken)

    def test_threshold_logic_edge_case_two_types_one_each(self):
        """Test that 2 types with 1 count each triggers detection."""
        html = "<html><body><p>{{ template [[ link</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None)
        # 2 types = detected
        self.assertTrue(has_broken)

    def test_threshold_logic_edge_case_one_type_two_count(self):
        """Test that 1 type with 2 count does not trigger detection."""
        html = "<html><body><p>{{ one {{ two</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None)
        # 1 type, count=2 (< 3) = ignored
        self.assertFalse(has_broken)

    def test_localized_keywords_in_detection(self):
        """Test that localized keywords are properly detected."""
        html = "<html><body><p>[Tiedosto:example.jpg]</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None, wiki_lang="fi")
        # Single indicator but only count of 1 - should be ignored
        self.assertFalse(has_broken)

        # Multiple indicators - should be detected
        html = "<html><body><p>[Tiedosto:a.jpg] {{ template</p></body></html>"
        has_broken, details = check_broken_wikicode(html, None, wiki_lang="fi")
        self.assertTrue(has_broken)
