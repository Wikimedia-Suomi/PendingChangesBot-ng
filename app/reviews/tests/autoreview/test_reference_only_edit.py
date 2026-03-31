from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from django.test import TestCase

from reviews.autoreview.checks.reference_only_edit import check_reference_only_edit
from reviews.autoreview.context import CheckContext
from reviews.autoreview.utils.wikitext import (
    extract_domain_from_url,
    extract_references,
    extract_urls_from_references,
    is_reference_only_edit,
    strip_references,
)
from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class WikitextUtilityTests(TestCase):
    def test_extract_references_basic(self):
        text = "Some text <ref>Citation 1</ref> more text <ref>Citation 2</ref>"
        refs = extract_references(text)
        self.assertEqual(len(refs), 2)
        self.assertIn("<ref>Citation 1</ref>", refs)
        self.assertIn("<ref>Citation 2</ref>", refs)

    def test_extract_references_with_attributes(self):
        text = '<ref name="test">Citation</ref> <ref group="note">Note</ref>'
        refs = extract_references(text)
        self.assertEqual(len(refs), 2)
        self.assertIn('<ref name="test">Citation</ref>', refs)
        self.assertIn('<ref group="note">Note</ref>', refs)

    def test_extract_references_self_closing(self):
        text = 'Text <ref name="cite1" /> more text <ref name="cite2"/>'
        refs = extract_references(text)
        self.assertEqual(len(refs), 2)

    def test_extract_references_multiline(self):
        text = """Text <ref>
        Long citation
        with multiple lines
        </ref> more text"""
        refs = extract_references(text)
        self.assertEqual(len(refs), 1)

    def test_strip_references(self):
        text = "Text <ref>Citation</ref> more text"
        result = strip_references(text)
        self.assertEqual(result, "Text  more text")

    def test_strip_references_self_closing(self):
        text = 'Text <ref name="cite" /> more text'
        result = strip_references(text)
        self.assertNotIn("<ref", result)

    def test_extract_urls_from_references(self):
        refs = [
            "<ref>http://example.com/page</ref>",
            "<ref>Text https://another.org text</ref>",
        ]
        urls = extract_urls_from_references(refs)
        self.assertEqual(len(urls), 2)
        self.assertIn("http://example.com/page", urls)
        self.assertIn("https://another.org", urls)

    def test_extract_domain_from_url(self):
        self.assertEqual(extract_domain_from_url("http://example.com/page"), "example.com")
        self.assertEqual(extract_domain_from_url("https://www.test.org/path"), "test.org")
        self.assertEqual(
            extract_domain_from_url("https://subdomain.example.com"), "subdomain.example.com"
        )

    def test_is_reference_only_edit_adding_reference(self):
        parent = "Some article text here."
        pending = "Some article text here.<ref>New citation</ref>"
        is_ref_only, has_removals, added = is_reference_only_edit(parent, pending)
        self.assertTrue(is_ref_only)
        self.assertFalse(has_removals)
        self.assertEqual(len(added), 1)

    def test_is_reference_only_edit_modifying_reference(self):
        parent = "Text <ref>Old citation</ref> more text"
        pending = "Text <ref>New citation</ref> more text"
        is_ref_only, has_removals, added = is_reference_only_edit(parent, pending)
        self.assertTrue(is_ref_only)
        self.assertTrue(has_removals)
        self.assertEqual(len(added), 1)

    def test_is_reference_only_edit_changing_content(self):
        parent = "Original text <ref>Citation</ref>"
        pending = "Modified text <ref>Citation</ref>"
        is_ref_only, has_removals, added = is_reference_only_edit(parent, pending)
        self.assertFalse(is_ref_only)

    def test_is_reference_only_edit_removing_reference(self):
        parent = "Text <ref>Citation</ref> more text"
        pending = "Text  more text"
        is_ref_only, has_removals, added = is_reference_only_edit(parent, pending)
        self.assertTrue(is_ref_only)
        self.assertTrue(has_removals)
        self.assertEqual(len(added), 0)

    def test_is_reference_only_edit_replacing_reference(self):
        parent = "Text <ref>Old citation</ref> more text"
        pending = "Text <ref>New citation</ref> more text"
        is_ref_only, has_removals, added = is_reference_only_edit(parent, pending)
        self.assertTrue(is_ref_only)
        self.assertTrue(has_removals)
        self.assertEqual(len(added), 1)


class ReferenceOnlyEditCheckTests(TestCase):
    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

        self.page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1,
            title="Test Page",
            stable_revid=100,
        )

    def _create_revision(self, revid, parentid, wikitext, parent_wikitext=None):
        revision = PendingRevision.objects.create(
            page=self.page,
            revid=revid,
            parentid=parentid,
            user_name="TestEditor",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="test",
            comment="Test edit",
            change_tags=[],
            wikitext=wikitext,
            categories=[],
        )

        # Store parent wikitext for testing
        if parent_wikitext is not None:
            revision.parent_wikitext = parent_wikitext

        return revision

    def test_adding_single_reference_without_url(self):
        parent_wikitext = "Article content here."
        pending_wikitext = "Article content here.<ref>Smith, John (2020). Book Title.</ref>"

        revision = self._create_revision(101, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()
        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")
        self.assertTrue(result.should_stop)
        self.assertIn("reference", result.message.lower())

    def test_adding_reference_with_known_domain(self):
        parent_wikitext = "Article content."
        pending_wikitext = "Article content.<ref>http://example.com/citation</ref>"

        revision = self._create_revision(102, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()
        mock_client.has_domain_been_used.return_value = True

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")
        self.assertTrue(result.should_stop)
        mock_client.has_domain_been_used.assert_called_once_with("example.com", exclude_page_id=1)

    def test_adding_reference_with_new_domain(self):
        parent_wikitext = "Article content."
        pending_wikitext = "Article content.<ref>http://newdomain.com/source</ref>"

        revision = self._create_revision(103, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()
        mock_client.has_domain_been_used.return_value = False

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "not_ok")
        self.assertEqual(result.decision.status, "manual")
        self.assertTrue(result.should_stop)
        self.assertIn("new domain", result.message.lower())

    def test_modifying_existing_reference(self):
        parent_wikitext = "Text <ref>Old citation</ref> more text"
        pending_wikitext = "Text <ref>Updated citation</ref> more text"

        revision = self._create_revision(104, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")

    def test_adding_multiple_references(self):
        parent_wikitext = "Article text. More text."
        pending_wikitext = "Article text.<ref>Citation 1</ref> More text.<ref>Citation 2</ref>"

        revision = self._create_revision(105, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")
        self.assertTrue(result.should_stop)

    def test_removing_reference_only(self):
        parent_wikitext = "Text <ref>Citation</ref> more text"
        pending_wikitext = "Text  more text"

        revision = self._create_revision(106, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "not_ok")
        self.assertEqual(result.decision.status, "manual")
        self.assertIn("only removes references", result.message.lower())

    def test_mixed_content_and_reference_changes(self):
        parent_wikitext = "Original content <ref>Citation</ref>"
        pending_wikitext = "Modified content <ref>New citation</ref>"

        revision = self._create_revision(107, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "skip")
        self.assertIn("beyond references", result.message.lower())

    def test_self_closing_reference_tags(self):
        parent_wikitext = "Article text."
        pending_wikitext = 'Article text.<ref name="cite1" />'

        revision = self._create_revision(108, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")

    def test_references_with_name_attribute(self):
        parent_wikitext = "Article text."
        pending_wikitext = 'Article text.<ref name="smith2020">Smith (2020)</ref>'

        revision = self._create_revision(109, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")

    def test_references_with_group_attribute(self):
        parent_wikitext = "Article text."
        pending_wikitext = 'Article text.<ref group="note">Footnote text</ref>'

        revision = self._create_revision(110, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")

    def test_multiple_domains_mixed_known_and_new(self):
        parent_wikitext = "Article text. More text."
        pending_wikitext = (
            "Article text.<ref>http://known.com/page</ref> "
            "More text.<ref>http://newdomain.org/page</ref>"
        )

        revision = self._create_revision(111, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()
        # First domain is known, second is new
        mock_client.has_domain_been_used.side_effect = [True, False]

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "not_ok")
        self.assertEqual(result.decision.status, "manual")
        self.assertIn("new domain", result.message.lower())

    def test_no_parent_revision(self):
        pending_wikitext = "New article.<ref>Citation</ref>"

        revision = self._create_revision(112, None, pending_wikitext, "")

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        # Should handle gracefully - may skip or process as new content
        self.assertIn(result.status, ["skip", "ok"])

    def test_replacing_reference_with_different_one(self):
        parent_wikitext = "Text <ref>Old source</ref> more text"
        pending_wikitext = "Text <ref>New source</ref> more text"

        revision = self._create_revision(113, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")

    def test_partial_reference_removal(self):
        parent_wikitext = "Text.<ref>Ref1</ref> More.<ref>Ref2</ref> End.<ref>Ref3</ref>"
        pending_wikitext = "Text.<ref>Ref1</ref> More. End.<ref>Ref3</ref>"

        revision = self._create_revision(114, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "not_ok")
        self.assertEqual(result.decision.status, "manual")
        self.assertIn("only removes references", result.message.lower())

    def test_adding_and_modifying_references_together(self):
        parent_wikitext = "Text. More."
        pending_wikitext = "Text.<ref>New ref 1</ref> More.<ref>New ref 2</ref>"

        revision = self._create_revision(115, 100, pending_wikitext, parent_wikitext)

        mock_client = MagicMock()

        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_reference_only_edit(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")
