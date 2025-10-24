from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from django.test import TestCase

from reviews.autoreview.checks.invalid_isbn import check_invalid_isbn
from reviews.autoreview.context import CheckContext
from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class InvalidISBNCheckTests(TestCase):
    def test_check_with_invalid_isbn(self):
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
            comment="Added book with invalid ISBN",
            change_tags=[],
            wikitext="Book citation: ISBN 978-0-306-40615-8",
            categories=[],
        )

        context = CheckContext(
            revision=revision,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_invalid_isbn(context)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.decision.status, "blocked")
        self.assertTrue(result.should_stop)
        self.assertIn("invalid ISBN", result.message)

    def test_check_with_valid_isbn(self):
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
            title="Test Page 2",
            stable_revid=200,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=201,
            parentid=200,
            user_name="Editor",
            user_id=2,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="test",
            comment="Added book with valid ISBN",
            change_tags=[],
            wikitext="Book citation: ISBN 978-0-306-40615-7",
            categories=[],
        )

        context = CheckContext(
            revision=revision,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_invalid_isbn(context)
        self.assertEqual(result.status, "ok")
        self.assertIn("No invalid ISBNs", result.message)
