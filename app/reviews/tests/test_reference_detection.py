"""Unit tests for reference-only edit detection."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from reviews.autoreview import (
    _check_domain_exists_on_wiki,
    _extract_domain_from_url,
    _extract_references,
    _extract_urls_from_text,
    _get_domains_from_references,
    _is_reference_only_edit,
    _remove_references,
)
from reviews.models import Wiki, WikiConfiguration


class ReferenceExtractionTests(TestCase):
    """Tests for _extract_references function."""

    def test_extract_simple_reference(self):
        """Extract a simple reference tag."""
        wikitext = 'Some text<ref>Citation content</ref> more text'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['content'], 'Citation content')
        self.assertEqual(refs[0]['name'], '')
        self.assertEqual(refs[0]['group'], '')

    def test_extract_named_reference(self):
        """Extract reference with name attribute."""
        wikitext = 'Text<ref name="source1">Citation</ref> more'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['content'], 'Citation')
        self.assertEqual(refs[0]['name'], 'source1')

    def test_extract_grouped_reference(self):
        """Extract reference with group attribute."""
        wikitext = 'Text<ref group="notes">Note content</ref> more'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['content'], 'Note content')
        self.assertEqual(refs[0]['group'], 'notes')

    def test_extract_named_and_grouped_reference(self):
        """Extract reference with both name and group attributes."""
        wikitext = 'Text<ref name="n1" group="notes">Content</ref>'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['name'], 'n1')
        self.assertEqual(refs[0]['group'], 'notes')
        self.assertEqual(refs[0]['content'], 'Content')

    def test_extract_self_closing_reference(self):
        """Extract self-closing reference tag."""
        wikitext = 'Text<ref name="source1"/> more text'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['name'], 'source1')
        self.assertEqual(refs[0]['content'], '')

    def test_extract_multiple_references(self):
        """Extract multiple references."""
        wikitext = (
            'Text<ref>First</ref> more <ref name="second">Second</ref> '
            'and <ref name="second"/> usage'
        )
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 3)
        self.assertEqual(refs[0]['content'], 'First')
        self.assertEqual(refs[1]['content'], 'Second')
        self.assertEqual(refs[2]['content'], '')

    def test_extract_reference_with_multiline_content(self):
        """Extract reference with multiline content."""
        wikitext = '''Text<ref>
Line 1
Line 2
</ref> more'''
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 1)
        self.assertIn('Line 1', refs[0]['content'])
        self.assertIn('Line 2', refs[0]['content'])

    def test_extract_reference_with_special_characters(self):
        """Extract reference with special characters in content."""
        wikitext = 'Text<ref>Content with {{template}} and [[link]]</ref>'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 1)
        self.assertIn('{{template}}', refs[0]['content'])
        self.assertIn('[[link]]', refs[0]['content'])

    def test_extract_empty_wikitext(self):
        """Extract from empty wikitext returns empty list."""
        self.assertEqual(_extract_references(''), [])
        self.assertEqual(_extract_references(None), [])

    def test_extract_no_references(self):
        """Extract from wikitext without references."""
        wikitext = 'Just plain text without any references'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 0)

    def test_case_insensitive_ref_tags(self):
        """Extract references with case variations."""
        wikitext = 'Text<REF>Upper</REF> and <Ref>Mixed</Ref>'
        refs = _extract_references(wikitext)

        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0]['content'], 'Upper')
        self.assertEqual(refs[1]['content'], 'Mixed')


class ReferenceRemovalTests(TestCase):
    """Tests for _remove_references function."""

    def test_remove_simple_reference(self):
        """Remove simple reference tag."""
        wikitext = 'Text<ref>Citation</ref> more text'
        result = _remove_references(wikitext)

        self.assertEqual(result, 'Text more text')

    def test_remove_multiple_references(self):
        """Remove multiple references."""
        wikitext = 'A<ref>1</ref> B<ref>2</ref> C'
        result = _remove_references(wikitext)

        self.assertEqual(result, 'A B C')

    def test_remove_self_closing_references(self):
        """Remove self-closing references."""
        wikitext = 'Text<ref name="x"/> more<ref name="y" /> text'
        result = _remove_references(wikitext)

        self.assertEqual(result, 'Text more text')

    def test_remove_mixed_references(self):
        """Remove mix of standard and self-closing references."""
        wikitext = 'A<ref>Full</ref> B<ref name="x"/> C'
        result = _remove_references(wikitext)

        self.assertEqual(result, 'A B C')

    def test_remove_preserves_other_content(self):
        """Remove references but preserve other content."""
        wikitext = '[[Link]]<ref>Cite</ref> {{Template}}'
        result = _remove_references(wikitext)

        self.assertEqual(result, '[[Link]] {{Template}}')

    def test_remove_empty_wikitext(self):
        """Remove from empty wikitext."""
        self.assertEqual(_remove_references(''), '')
        self.assertEqual(_remove_references(None), '')

    def test_remove_no_references(self):
        """Remove from wikitext without references."""
        wikitext = 'Plain text without references'
        result = _remove_references(wikitext)

        self.assertEqual(result, wikitext)


class ReferenceOnlyEditTests(TestCase):
    """Tests for _is_reference_only_edit function."""

    def test_adding_single_reference(self):
        """Detect adding a single reference."""
        old = 'Some article text.'
        new = 'Some article text.<ref>New citation</ref>'

        result = _is_reference_only_edit(old, new)

        self.assertTrue(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 1)
        self.assertEqual(len(result['modified_refs']), 0)
        self.assertEqual(len(result['removed_refs']), 0)
        self.assertFalse(result['non_ref_changed'])

    def test_adding_multiple_references(self):
        """Detect adding multiple references."""
        old = 'Article text. More.'
        new = 'Article text.<ref>Cite 1</ref> More.<ref>Cite 2</ref>'

        result = _is_reference_only_edit(old, new)

        self.assertTrue(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 2)
        self.assertEqual(len(result['removed_refs']), 0)

    def test_modifying_reference_content(self):
        """Detect modifying reference content."""
        old = 'Text<ref name="s1">Old citation</ref> more'
        new = 'Text<ref name="s1">Updated citation</ref> more'

        result = _is_reference_only_edit(old, new)

        self.assertTrue(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 0)
        self.assertEqual(len(result['modified_refs']), 1)
        self.assertEqual(len(result['removed_refs']), 0)

    def test_removing_reference_not_reference_only(self):
        """Removing reference should not be reference-only."""
        old = 'Text<ref>Citation</ref> more'
        new = 'Text more'

        result = _is_reference_only_edit(old, new)

        self.assertFalse(result['is_reference_only'])
        self.assertEqual(len(result['removed_refs']), 1)

    def test_mixed_content_and_reference_changes(self):
        """Mixed changes should not be reference-only."""
        old = 'Original text.'
        new = 'Modified text.<ref>New citation</ref>'

        result = _is_reference_only_edit(old, new)

        self.assertFalse(result['is_reference_only'])
        self.assertTrue(result['non_ref_changed'])

    def test_replacing_reference(self):
        """Replacing one reference with another."""
        old = 'Text<ref>Old cite</ref> more'
        new = 'Text<ref>New cite</ref> more'

        result = _is_reference_only_edit(old, new)

        # This creates a removed + added ref since content is the key
        self.assertFalse(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 1)
        self.assertEqual(len(result['removed_refs']), 1)

    def test_replacing_named_reference(self):
        """Replacing content of named reference."""
        old = 'Text<ref name="x">Old</ref> more'
        new = 'Text<ref name="x">New</ref> more'

        result = _is_reference_only_edit(old, new)

        # Named refs should be detected as modification
        self.assertTrue(result['is_reference_only'])
        self.assertEqual(len(result['modified_refs']), 1)
        self.assertEqual(len(result['removed_refs']), 0)

    def test_adding_self_closing_reference(self):
        """Detect adding self-closing reference."""
        old = 'Text with<ref name="s1">Full ref</ref> content'
        new = 'Text with<ref name="s1">Full ref</ref> content<ref name="s2"/>'

        result = _is_reference_only_edit(old, new)

        self.assertTrue(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 1)

    def test_whitespace_changes_ignored(self):
        """Whitespace-only changes in non-ref content ignored."""
        old = 'Text  with  spaces.'
        new = 'Text with spaces.<ref>New</ref>'

        result = _is_reference_only_edit(old, new)

        self.assertTrue(result['is_reference_only'])
        self.assertFalse(result['non_ref_changed'])

    def test_no_changes(self):
        """No changes should not be reference-only."""
        text = 'Same text<ref>Same ref</ref>'

        result = _is_reference_only_edit(text, text)

        self.assertFalse(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 0)
        self.assertEqual(len(result['modified_refs']), 0)

    def test_empty_wikitext(self):
        """Handle empty wikitext."""
        result = _is_reference_only_edit('', '')

        self.assertFalse(result['is_reference_only'])

    def test_reference_with_attributes(self):
        """Handle references with name and group attributes."""
        old = 'Text here.'
        new = 'Text here.<ref name="n1" group="notes">Note</ref>'

        result = _is_reference_only_edit(old, new)

        self.assertTrue(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 1)
        self.assertEqual(result['added_refs'][0]['name'], 'n1')
        self.assertEqual(result['added_refs'][0]['group'], 'notes')

    def test_complex_article_with_ref_addition(self):
        """Real-world article with reference addition."""
        old = '''
== Section ==
Article content with [[links]] and {{templates}}.

Another paragraph.

[[Category:Test]]
'''
        new = '''
== Section ==
Article content with [[links]] and {{templates}}.<ref>Source</ref>

Another paragraph.

[[Category:Test]]
'''

        result = _is_reference_only_edit(old, new)

        self.assertTrue(result['is_reference_only'])
        self.assertEqual(len(result['added_refs']), 1)


class URLExtractionTests(TestCase):
    """Tests for URL and domain extraction functions."""

    def test_extract_urls_from_text(self):
        """Extract URLs from text."""
        text = 'See https://example.com/page and http://test.org for more info'
        urls = _extract_urls_from_text(text)

        self.assertEqual(len(urls), 2)
        self.assertIn('https://example.com/page', urls)
        self.assertIn('http://test.org', urls)

    def test_extract_urls_with_paths(self):
        """Extract URLs with paths and parameters."""
        text = 'Link: https://example.com/path/to/page?param=value&other=123'
        urls = _extract_urls_from_text(text)

        self.assertEqual(len(urls), 1)
        self.assertIn('https://example.com/path/to/page?param=value&other=123', urls)

    def test_extract_urls_in_wikitext(self):
        """Extract URLs from wikitext with brackets."""
        text = '[https://example.com Source] and [[Internal link]]'
        urls = _extract_urls_from_text(text)

        self.assertEqual(len(urls), 1)
        self.assertIn('https://example.com', urls)

    def test_extract_no_urls(self):
        """Extract from text without URLs."""
        text = 'Just plain text without any links'
        urls = _extract_urls_from_text(text)

        self.assertEqual(len(urls), 0)

    def test_extract_urls_empty_text(self):
        """Extract from empty text."""
        self.assertEqual(_extract_urls_from_text(''), [])
        self.assertEqual(_extract_urls_from_text(None), [])

    def test_extract_domain_from_url(self):
        """Extract domain from URL."""
        self.assertEqual(
            _extract_domain_from_url('https://example.com/page'),
            'example.com'
        )
        self.assertEqual(
            _extract_domain_from_url('http://test.org'),
            'test.org'
        )
        self.assertEqual(
            _extract_domain_from_url('https://sub.domain.com/path'),
            'sub.domain.com'
        )

    def test_extract_domain_with_port(self):
        """Extract domain from URL with port."""
        self.assertEqual(
            _extract_domain_from_url('http://example.com:8080/page'),
            'example.com'
        )

    def test_extract_domain_case_insensitive(self):
        """Domain extraction is case insensitive."""
        self.assertEqual(
            _extract_domain_from_url('https://EXAMPLE.COM/page'),
            'example.com'
        )

    def test_extract_domain_invalid_url(self):
        """Handle invalid URLs."""
        self.assertEqual(_extract_domain_from_url(''), '')
        self.assertEqual(_extract_domain_from_url(None), '')
        self.assertEqual(_extract_domain_from_url('not a url'), '')

    def test_get_domains_from_references(self):
        """Get domains from list of references."""
        refs = [
            {'content': 'Source: https://example.com/article'},
            {'content': 'See http://test.org and https://another.com'},
            {'content': 'No URLs here'},
        ]
        domains = _get_domains_from_references(refs)

        self.assertEqual(len(domains), 3)
        self.assertIn('example.com', domains)
        self.assertIn('test.org', domains)
        self.assertIn('another.com', domains)

    def test_get_domains_deduplicates(self):
        """Get domains deduplicates repeated domains."""
        refs = [
            {'content': 'Link: https://example.com/page1'},
            {'content': 'Another: https://example.com/page2'},
        ]
        domains = _get_domains_from_references(refs)

        self.assertEqual(len(domains), 1)
        self.assertIn('example.com', domains)

    def test_get_domains_empty_refs(self):
        """Get domains from empty list."""
        self.assertEqual(len(_get_domains_from_references([])), 0)


class DomainVerificationTests(TestCase):
    """Tests for domain verification with Pywikibot."""

    def setUp(self):
        """Set up test wiki."""
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    @mock.patch('reviews.autoreview.pywikibot.Site')
    def test_check_domain_exists_returns_true(self, mock_site_class):
        """Domain exists on wiki returns True."""
        mock_site = mock.Mock()
        mock_site.exturlusage.return_value = iter(['page1'])
        mock_site_class.return_value = mock_site

        result = _check_domain_exists_on_wiki('example.com', self.wiki)

        self.assertTrue(result)
        mock_site.exturlusage.assert_called_once_with(
            'example.com',
            namespaces=[0],
            total=1
        )

    @mock.patch('reviews.autoreview.pywikibot.Site')
    def test_check_domain_not_exists_returns_false(self, mock_site_class):
        """Domain not found on wiki returns False."""
        mock_site = mock.Mock()
        mock_site.exturlusage.return_value = iter([])
        mock_site_class.return_value = mock_site

        result = _check_domain_exists_on_wiki('unknown.com', self.wiki)

        self.assertFalse(result)

    @mock.patch('reviews.autoreview.pywikibot.Site')
    def test_check_domain_network_error_returns_false(self, mock_site_class):
        """Network error returns False for safety."""
        mock_site = mock.Mock()
        mock_site.exturlusage.side_effect = Exception('Network error')
        mock_site_class.return_value = mock_site

        result = _check_domain_exists_on_wiki('example.com', self.wiki)

        self.assertFalse(result)

    def test_check_domain_empty_domain(self):
        """Empty domain returns False."""
        self.assertFalse(_check_domain_exists_on_wiki('', self.wiki))
        self.assertFalse(_check_domain_exists_on_wiki(None, self.wiki))
