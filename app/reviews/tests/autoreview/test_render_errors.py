"""Tests for render errors check."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase

from reviews.autoreview.checks.render_errors import check_render_errors
from reviews.autoreview.context import CheckContext
from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class RenderErrorsTests(TestCase):
    """Test suite for render errors detection."""

    @patch("reviews.services.wiki_client.pywikibot.Site")
    def test_no_new_render_errors(self, mock_site):
        """Test check passes when no new render errors are introduced."""
        wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=wiki)

        page = PendingPage.objects.create(
            wiki=wiki,
            pageid=1,
            title="Test Page",
            stable_revid=100,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=101,
            parentid=100,
            user_name="Editor",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="test",
            comment="Test edit",
            change_tags=[],
            wikitext="Normal wikitext content",
            categories=[],
        )

        # Mock the pywikibot site
        mock_site_instance = MagicMock()
        mock_site.return_value = mock_site_instance

        # Mock parse API response with no errors
        class FakeRequest:
            def submit(self):
                return {"parse": {"text": "<p>Normal content</p>"}}

        mock_site_instance.simple_request.return_value = FakeRequest()

        from reviews.services import WikiClient

        client = WikiClient(wiki)

        context = CheckContext(
            revision=revision,
            client=client,
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_render_errors(context)
        self.assertEqual(result.status, "ok")
        self.assertIn("does not introduce", result.message)
