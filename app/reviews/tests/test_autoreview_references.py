"""Integration tests for reference-only edit autoreview functionality."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class ReferenceOnlyAutoreviewTests(TestCase):
    """Integration tests for reference-only edit detection in autoreview."""

    def setUp(self):
        """Set up test wiki and client."""
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    @mock.patch('reviews.autoreview._check_domain_exists_on_wiki')
    @mock.patch('reviews.models.pywikibot.Site')
    def test_adding_reference_without_url_should_approve(
        self, mock_site, mock_check_domain
    ):
        """Adding reference without URL should auto-approve."""
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=100,
            title="Test Article",
            stable_revid=1000,
        )

        old_text = "Article content here."
        new_text = "Article content here.<ref>Smith, John. Book Title. 2023.</ref>"

        PendingRevision.objects.create(
            page=page,
            revid=1000,
            parentid=None,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="oldhash",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=1001,
            parentid=1000,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="newhash",
            comment="Added reference",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]

        self.assertEqual(result["decision"]["status"], "approve")
        self.assertIn("reference", result["decision"]["reason"].lower())

    @mock.patch('reviews.autoreview._check_domain_exists_on_wiki')
    @mock.patch('reviews.models.pywikibot.Site')
    def test_adding_reference_with_verified_domain_should_approve(
        self, mock_site, mock_check_domain
    ):
        """Adding reference with verified domain should auto-approve."""
        mock_check_domain.return_value = True

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=101,
            title="Test Article 2",
            stable_revid=2000,
        )

        old_text = "Article content."
        new_text = "Article content.<ref>https://example.com/source</ref>"

        PendingRevision.objects.create(
            page=page,
            revid=2000,
            parentid=None,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="oldhash",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=2001,
            parentid=2000,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="newhash",
            comment="Added reference with URL",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]

        self.assertEqual(result["decision"]["status"], "approve")
        mock_check_domain.assert_called_once_with('example.com', self.wiki)

    @mock.patch('reviews.autoreview._check_domain_exists_on_wiki')
    @mock.patch('reviews.models.pywikibot.Site')
    def test_adding_reference_with_unverified_domain_should_require_review(
        self, mock_site, mock_check_domain
    ):
        """Adding reference with unverified domain should require manual review."""
        mock_check_domain.return_value = False

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=102,
            title="Test Article 3",
            stable_revid=3000,
        )

        old_text = "Article content."
        new_text = "Article content.<ref>https://unknown-site.com/article</ref>"

        PendingRevision.objects.create(
            page=page,
            revid=3000,
            parentid=None,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="oldhash",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=3001,
            parentid=3000,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="newhash",
            comment="Added reference with unverified URL",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]

        self.assertEqual(result["decision"]["status"], "manual")
        self.assertIn("unverified", result["decision"]["reason"].lower())

    @mock.patch('reviews.models.pywikibot.Site')
    def test_removing_reference_should_require_review(self, mock_site):
        """Removing reference should require manual review."""
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=103,
            title="Test Article 4",
            stable_revid=4000,
        )

        old_text = "Content.<ref>Citation</ref>"
        new_text = "Content."

        PendingRevision.objects.create(
            page=page,
            revid=4000,
            parentid=None,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="oldhash",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=4001,
            parentid=4000,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="newhash",
            comment="Removed reference",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]

        # Should require manual review
        self.assertEqual(result["decision"]["status"], "manual")

    @mock.patch('reviews.models.pywikibot.Site')
    def test_mixed_content_and_reference_changes_should_not_approve(self, mock_site):
        """Mixed content and reference changes should not be approved."""
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=104,
            title="Test Article 5",
            stable_revid=5000,
        )

        old_text = "Original content."
        new_text = "Modified content.<ref>New citation</ref>"

        PendingRevision.objects.create(
            page=page,
            revid=5000,
            parentid=None,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="oldhash",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=5001,
            parentid=5000,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="newhash",
            comment="Changed content and added reference",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]

        # Should require manual review
        self.assertEqual(result["decision"]["status"], "manual")

    @mock.patch('reviews.autoreview._check_domain_exists_on_wiki')
    @mock.patch('reviews.models.pywikibot.Site')
    def test_modifying_reference_with_verified_domain_should_approve(
        self, mock_site, mock_check_domain
    ):
        """Modifying reference content with verified domain should approve."""
        mock_check_domain.return_value = True

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=105,
            title="Test Article 6",
            stable_revid=6000,
        )

        old_text = 'Content.<ref name="source">Old citation</ref>'
        new_text = 'Content.<ref name="source">Updated https://example.com</ref>'

        PendingRevision.objects.create(
            page=page,
            revid=6000,
            parentid=None,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="oldhash",
            comment="Original",
            wikitext=old_text,
        )

        PendingRevision.objects.create(
            page=page,
            revid=6001,
            parentid=6000,
            user_name="Editor",
            user_id=123,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="newhash",
            comment="Updated reference",
            wikitext=new_text,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]

        self.assertEqual(result["decision"]["status"], "approve")
