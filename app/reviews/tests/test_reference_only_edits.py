from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from reviews.autoreview import (
    _check_domain_usage_in_wikipedia,
    _extract_domain,
    _extract_references,
    _extract_urls_from_references,
    _is_reference_only_edit,
    _remove_references,
)
from reviews.models import (
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)


class ReferenceExtractionTests(TestCase):
    """Test reference extraction and parsing functions."""

    def test_extract_references_with_standard_tags(self):
        """Test extracting standard <ref>content</ref> tags."""
        wikitext = """Some text <ref>First reference</ref> more text <ref>Second reference</ref>."""
        refs = _extract_references(wikitext)
        self.assertEqual(len(refs), 2)
        self.assertIn("<ref>First reference</ref>", refs.values())
        self.assertIn("<ref>Second reference</ref>", refs.values())

    def test_extract_references_with_self_closing_tags(self):
        """Test extracting self-closing <ref /> tags."""
        wikitext = """Text <ref name="test" /> more text."""
        refs = _extract_references(wikitext)
        self.assertEqual(len(refs), 1)
        self.assertIn('<ref name="test" />', refs.values())

    def test_extract_references_with_attributes(self):
        """Test extracting references with name and group attributes."""
        wikitext = """
        Text <ref name="citation1">Content</ref>
        and <ref group="note">Note content</ref>
        and <ref name="test" group="notes">More</ref>.
        """
        refs = _extract_references(wikitext)
        self.assertEqual(len(refs), 3)

    def test_extract_references_case_insensitive(self):
        """Test that reference extraction is case-insensitive."""
        wikitext = """<REF>Upper case</REF> and <Ref>Mixed case</Ref>."""
        refs = _extract_references(wikitext)
        self.assertEqual(len(refs), 2)

    def test_extract_references_multiline(self):
        """Test extracting references that span multiple lines."""
        wikitext = """Text <ref>
        This is a
        multiline
        reference
        </ref> more text."""
        refs = _extract_references(wikitext)
        self.assertEqual(len(refs), 1)

    def test_extract_references_empty_wikitext(self):
        """Test extracting from empty wikitext."""
        refs = _extract_references("")
        self.assertEqual(refs, {})

    def test_remove_references_standard_tags(self):
        """Test removing standard reference tags."""
        wikitext = """Text before <ref>Citation</ref> text after."""
        cleaned = _remove_references(wikitext)
        self.assertEqual(cleaned, """Text before  text after.""")

    def test_remove_references_self_closing(self):
        """Test removing self-closing reference tags."""
        wikitext = """Text <ref name="test" /> more text."""
        cleaned = _remove_references(wikitext)
        self.assertEqual(cleaned, """Text  more text.""")

    def test_remove_references_multiple(self):
        """Test removing multiple references."""
        wikitext = """One <ref>A</ref> two <ref>B</ref> three <ref name="c" />."""
        cleaned = _remove_references(wikitext)
        self.assertEqual(cleaned, """One  two  three .""")


class URLExtractionTests(TestCase):
    """Test URL and domain extraction from references."""

    def test_extract_urls_from_references(self):
        """Test extracting URLs from reference content."""
        refs = [
            '<ref>http://example.com/page</ref>',
            '<ref>{{cite web|url=https://test.org/article}}</ref>',
        ]
        urls = _extract_urls_from_references(refs)
        self.assertEqual(len(urls), 2)
        self.assertIn('http://example.com/page', urls)
        self.assertIn('https://test.org/article', urls)

    def test_extract_urls_handles_trailing_punctuation(self):
        """Test that trailing punctuation is removed from URLs."""
        refs = ['<ref>See http://example.com/page.</ref>']
        urls = _extract_urls_from_references(refs)
        self.assertEqual(urls, ['http://example.com/page'])

    def test_extract_urls_with_parentheses(self):
        """Test extracting URLs containing parentheses."""
        refs = ['<ref>http://example.com/page_(test)</ref>']
        urls = _extract_urls_from_references(refs)
        self.assertIn('http://example.com/page_(test)', urls)

    def test_extract_urls_no_urls(self):
        """Test extracting from references without URLs."""
        refs = ['<ref>Plain text reference</ref>']
        urls = _extract_urls_from_references(refs)
        self.assertEqual(urls, [])

    def test_extract_domain_standard_url(self):
        """Test extracting domain from standard URL."""
        url = 'https://www.example.com/path/to/page'
        domain = _extract_domain(url)
        self.assertEqual(domain, 'example.com')

    def test_extract_domain_without_www(self):
        """Test extracting domain without www prefix."""
        url = 'https://example.org/article'
        domain = _extract_domain(url)
        self.assertEqual(domain, 'example.org')

    def test_extract_domain_with_subdomain(self):
        """Test extracting domain with subdomain."""
        url = 'https://blog.example.com/post'
        domain = _extract_domain(url)
        self.assertEqual(domain, 'blog.example.com')

    def test_extract_domain_invalid_url(self):
        """Test extracting from invalid URL."""
        domain = _extract_domain('not a url')
        self.assertIsNone(domain)


class ReferenceOnlyEditDetectionTests(TestCase):
    """Test detection of reference-only edits."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

    @mock.patch("reviews.models.pywikibot.Site")
    def test_adding_single_reference(self, mock_site):
        """Test detecting edit that adds a single reference."""
        old_text = "Article content."
        new_text = "Article content.<ref>New citation</ref>"

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=1, title="Test", stable_revid=10
        )

        self._setup_mock_site(mock_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=10,
            parentid=None,
            user_name="User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=11,
            parentid=10,
            user_name="User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Add reference",
            wikitext=new_text,
        )

        is_ref_only, has_removals, refs = _is_reference_only_edit(revision)
        self.assertTrue(is_ref_only)
        self.assertFalse(has_removals)
        self.assertEqual(len(refs), 1)

    @mock.patch("reviews.models.pywikibot.Site")
    def test_modifying_existing_reference(self, mock_site):
        """Test detecting edit that modifies an existing reference."""
        old_text = "Text <ref>Old citation</ref> more text."
        new_text = "Text <ref>Updated citation</ref> more text."

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=2, title="Test2", stable_revid=20
        )

        self._setup_mock_site(mock_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=20,
            parentid=None,
            user_name="User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=21,
            parentid=20,
            user_name="User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Update reference",
            wikitext=new_text,
        )

        is_ref_only, has_removals, refs = _is_reference_only_edit(revision)
        self.assertTrue(is_ref_only)
        self.assertTrue(has_removals)  # Old reference was removed
        self.assertEqual(len(refs), 1)  # New reference was added

    @mock.patch("reviews.models.pywikibot.Site")
    def test_adding_multiple_references(self, mock_site):
        """Test detecting edit that adds multiple references."""
        old_text = "Article text. More text."
        new_text = "Article text.<ref>First</ref> More text.<ref>Second</ref>"

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=3, title="Test3", stable_revid=30
        )

        self._setup_mock_site(mock_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=30,
            parentid=None,
            user_name="User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=31,
            parentid=30,
            user_name="User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Add references",
            wikitext=new_text,
        )

        is_ref_only, has_removals, refs = _is_reference_only_edit(revision)
        self.assertTrue(is_ref_only)
        self.assertFalse(has_removals)
        self.assertEqual(len(refs), 2)

    @mock.patch("reviews.models.pywikibot.Site")
    def test_removing_reference(self, mock_site):
        """Test detecting edit that removes a reference."""
        old_text = "Text <ref>Citation</ref> more text."
        new_text = "Text  more text."

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=4, title="Test4", stable_revid=40
        )

        self._setup_mock_site(mock_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=40,
            parentid=None,
            user_name="User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=41,
            parentid=40,
            user_name="User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Remove reference",
            wikitext=new_text,
        )

        is_ref_only, has_removals, refs = _is_reference_only_edit(revision)
        self.assertTrue(is_ref_only)
        self.assertTrue(has_removals)
        self.assertEqual(len(refs), 0)

    @mock.patch("reviews.models.pywikibot.Site")
    def test_mixed_edit_with_content_and_reference_changes(self, mock_site):
        """Test that mixed edits are not detected as reference-only."""
        old_text = "Original text."
        new_text = "Modified text.<ref>New citation</ref>"

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=5, title="Test5", stable_revid=50
        )

        self._setup_mock_site(mock_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=50,
            parentid=None,
            user_name="User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=51,
            parentid=50,
            user_name="User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Update content",
            wikitext=new_text,
        )

        is_ref_only, has_removals, refs = _is_reference_only_edit(revision)
        self.assertFalse(is_ref_only)

    @mock.patch("reviews.models.pywikibot.Site")
    def test_adding_self_closing_reference(self, mock_site):
        """Test detecting edit that adds self-closing reference tags."""
        old_text = "Text."
        new_text = 'Text.<ref name="citation1" />'

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=6, title="Test6", stable_revid=60
        )

        self._setup_mock_site(mock_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=60,
            parentid=None,
            user_name="User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=61,
            parentid=60,
            user_name="User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Add self-closing ref",
            wikitext=new_text,
        )

        is_ref_only, has_removals, refs = _is_reference_only_edit(revision)
        self.assertTrue(is_ref_only)
        self.assertFalse(has_removals)
        self.assertEqual(len(refs), 1)

    @mock.patch("reviews.models.pywikibot.Site")
    def test_references_with_name_and_group_attributes(self, mock_site):
        """Test references with name and group attributes."""
        old_text = "Text."
        new_text = 'Text.<ref name="test" group="notes">Content</ref>'

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=7, title="Test7", stable_revid=70
        )

        self._setup_mock_site(mock_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=70,
            parentid=None,
            user_name="User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=71,
            parentid=70,
            user_name="User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Add attributed ref",
            wikitext=new_text,
        )

        is_ref_only, has_removals, refs = _is_reference_only_edit(revision)
        self.assertTrue(is_ref_only)

    def _setup_mock_site(self, mock_site, wikitexts):
        """Helper to setup mock site for wikitext fetching."""

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def __init__(self):
                self.call_count = 0
                self.wikitexts = wikitexts

            def simple_request(self, **kwargs):
                if self.call_count < len(self.wikitexts):
                    wikitext = self.wikitexts[self.call_count]
                    self.call_count += 1
                    return FakeRequest(
                        {
                            "query": {
                                "pages": [
                                    {
                                        "revisions": [
                                            {
                                                "slots": {
                                                    "main": {"content": wikitext}
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    )
                return FakeRequest({"query": {"pages": []}})

        mock_site.return_value = FakeSite()


class DomainUsageCheckTests(TestCase):
    """Test domain usage verification in Wikipedia."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

    @mock.patch("reviews.autoreview.logger")
    @mock.patch("reviews.autoreview.pywikibot.Site")
    def test_check_domain_usage_existing_domain(self, mock_site, mock_logger):
        """Test checking a domain that exists in Wikipedia."""

        class FakeSite:
            def exturlusage(self, url, protocol, namespaces, total):
                # Simulate finding the domain
                yield {"title": "Example Page"}

        mock_site.return_value = FakeSite()

        result = _check_domain_usage_in_wikipedia(self.wiki, "example.com")
        self.assertTrue(result)

    @mock.patch("reviews.autoreview.logger")
    @mock.patch("reviews.autoreview.pywikibot.Site")
    def test_check_domain_usage_new_domain(self, mock_site, mock_logger):
        """Test checking a domain that doesn't exist in Wikipedia."""

        class FakeSite:
            def exturlusage(self, url, protocol, namespaces, total):
                # Simulate not finding the domain
                return iter([])

        mock_site.return_value = FakeSite()

        result = _check_domain_usage_in_wikipedia(self.wiki, "newdomain.com")
        self.assertFalse(result)

    @mock.patch("reviews.autoreview.logger")
    @mock.patch("reviews.autoreview.pywikibot.Site")
    def test_check_domain_usage_api_error(self, mock_site, mock_logger):
        """Test that API errors are handled gracefully."""

        class FakeSite:
            def exturlusage(self, url, protocol, namespaces, total):
                raise Exception("API Error")

        mock_site.return_value = FakeSite()

        result = _check_domain_usage_in_wikipedia(self.wiki, "example.com")
        self.assertFalse(result)  # Conservative: require review on error


class ReferenceOnlyEditAutoApprovalTests(TestCase):
    """Test auto-approval logic for reference-only edits."""

    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.models.pywikibot.Site")
    def test_reference_only_edit_without_urls_auto_approved(
        self, mock_models_site, mock_autoreview_site
    ):
        """Reference-only edit without URLs should be auto-approved."""
        old_text = "Article text."
        new_text = "Article text.<ref>Smith, John. ''Book Title''. 2020.</ref>"

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=100, title="Test Article", stable_revid=1000
        )

        self._setup_mock_site(mock_models_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=1000,
            parentid=None,
            user_name="Editor1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=1001,
            parentid=1000,
            user_name="Editor2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Add reference",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        self.assertEqual(result["decision"]["status"], "approve")
        self.assertIn("reference", result["decision"]["reason"].lower())

    @mock.patch("reviews.services.WikiClient.get_rendered_html")
    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.models.pywikibot.Site")
    def test_reference_only_edit_with_known_domain_auto_approved(
        self, mock_models_site, mock_autoreview_site, mock_get_html
    ):
        """Reference-only edit with known domain should be auto-approved."""
        mock_get_html.return_value = "<p>No errors</p>"
        old_text = "Article text."
        new_text = (
            "Article text.<ref>{{cite web|url=https://example.com/page}}</ref>"
        )

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=101, title="Test Article 2", stable_revid=2000
        )

        self._setup_mock_site(mock_models_site, [old_text, new_text])
        self._setup_mock_exturlusage(mock_autoreview_site, True)

        PendingRevision.objects.create(
            page=page,
            revid=2000,
            parentid=None,
            user_name="Editor1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=2001,
            parentid=2000,
            user_name="Editor2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Add web reference",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        self.assertEqual(result["decision"]["status"], "approve")

    @mock.patch("reviews.services.WikiClient.get_rendered_html")
    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.models.pywikibot.Site")
    def test_reference_only_edit_with_new_domain_requires_review(
        self, mock_models_site, mock_autoreview_site, mock_get_html
    ):
        """Reference-only edit with new domain should require manual review."""
        mock_get_html.return_value = "<p>No errors</p>"
        old_text = "Article text."
        new_text = (
            "Article text.<ref>{{cite web|url=https://newdomain.com/page}}</ref>"
        )

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=102, title="Test Article 3", stable_revid=3000
        )

        self._setup_mock_site(mock_models_site, [old_text, new_text])
        self._setup_mock_exturlusage(mock_autoreview_site, False)

        PendingRevision.objects.create(
            page=page,
            revid=3000,
            parentid=None,
            user_name="Editor1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=3001,
            parentid=3000,
            user_name="Editor2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Add reference with new domain",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        self.assertEqual(result["decision"]["status"], "manual")
        self.assertIn("new", result["decision"]["reason"].lower())

    @mock.patch("reviews.models.pywikibot.Site")
    def test_reference_removal_requires_review(self, mock_models_site):
        """Removing references should require manual review."""
        old_text = "Article text.<ref>Old citation</ref>"
        new_text = "Article text."

        page = PendingPage.objects.create(
            wiki=self.wiki, pageid=103, title="Test Article 4", stable_revid=4000
        )

        self._setup_mock_site(mock_models_site, [old_text, new_text])

        PendingRevision.objects.create(
            page=page,
            revid=4000,
            parentid=None,
            user_name="Editor1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="old",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=4001,
            parentid=4000,
            user_name="Editor2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="new",
            comment="Remove reference",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        self.assertEqual(result["decision"]["status"], "manual")
        self.assertIn("remove", result["decision"]["reason"].lower())

    def _setup_mock_site(self, mock_site, wikitexts):
        """Helper to setup mock site for wikitext fetching."""

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def __init__(self):
                self.call_count = 0
                self.wikitexts = wikitexts

            def simple_request(self, **kwargs):
                if self.call_count < len(self.wikitexts):
                    wikitext = self.wikitexts[self.call_count]
                    self.call_count += 1
                    return FakeRequest(
                        {
                            "query": {
                                "pages": [
                                    {
                                        "revisions": [
                                            {
                                                "slots": {
                                                    "main": {"content": wikitext}
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    )
                return FakeRequest({"query": {"pages": []}})

        mock_site.return_value = FakeSite()

    def _setup_mock_exturlusage(self, mock_site, domain_exists):
        """Helper to setup mock site for domain checking."""

        class FakeSite:
            def __init__(self, exists):
                self.exists = exists

            def exturlusage(self, url, protocol, namespaces, total):
                if self.exists:
                    yield {"title": "Example Page"}
                else:
                    return iter([])

        mock_site.return_value = FakeSite(domain_exists)
