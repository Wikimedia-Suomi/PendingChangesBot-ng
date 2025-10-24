from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from django.test import TestCase

from reviews.autoreview.checks.article_to_redirect import check_article_to_redirect
from reviews.autoreview.context import CheckContext
from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class ArticleToRedirectTests(TestCase):
    def test_not_a_redirect(self):
        mock_revision = MagicMock()
        mock_revision.get_wikitext.return_value = "This is normal article content."

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )

        result = check_article_to_redirect(context)
        self.assertEqual(result.status, "ok")
        self.assertIn("not an article-to-redirect", result.message)

    def test_redirect_without_parent(self):
        mock_revision = MagicMock()
        mock_revision.get_wikitext.return_value = "#REDIRECT [[Target Page]]"
        mock_revision.parentid = None

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )

        result = check_article_to_redirect(context)
        self.assertEqual(result.status, "ok")
        self.assertIn("not an article-to-redirect", result.message)

    def test_article_to_redirect_conversion(self):
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

        PendingRevision.objects.create(
            page=page,
            revid=100,
            parentid=99,
            user_name="Author",
            user_id=1,
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=1),
            sha1="parent",
            comment="Parent",
            change_tags=[],
            wikitext="This is article content with substance.",
            categories=[],
        )

        redirect_revision = PendingRevision.objects.create(
            page=page,
            revid=101,
            parentid=100,
            user_name="Editor",
            user_id=2,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="redirect",
            comment="Convert to redirect",
            change_tags=[],
            wikitext="#REDIRECT [[Target Page]]",
            categories=[],
        )

        context = CheckContext(
            revision=redirect_revision,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )

        result = check_article_to_redirect(context)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.decision.status, "blocked")
        self.assertTrue(result.should_stop)
        self.assertIn("autoreview rights", result.message)

    def test_redirect_to_redirect_allowed(self):
        wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=wiki)

        page = PendingPage.objects.create(
            wiki=wiki,
            pageid=2,
            title="Redirect Page",
            stable_revid=200,
        )

        PendingRevision.objects.create(
            page=page,
            revid=200,
            parentid=199,
            user_name="Author",
            user_id=1,
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=1),
            sha1="parent",
            comment="Redirect",
            change_tags=[],
            wikitext="#REDIRECT [[Old Target]]",
            categories=[],
        )

        updated_redirect = PendingRevision.objects.create(
            page=page,
            revid=201,
            parentid=200,
            user_name="Editor",
            user_id=2,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="updated",
            comment="Update redirect target",
            change_tags=[],
            wikitext="#REDIRECT [[New Target]]",
            categories=[],
        )

        context = CheckContext(
            revision=updated_redirect,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )

        result = check_article_to_redirect(context)
        self.assertEqual(result.status, "ok")
        self.assertIn("not an article-to-redirect", result.message)
