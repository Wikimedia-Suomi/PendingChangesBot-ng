from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from reviews.autoreview import _get_revertrisk_score
from reviews.models import (
    EditorProfile,
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)


class RevertriskTests(TestCase):
    """Tests for revertrisk API integration and auto-review functionality."""

    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        self.config = WikiConfiguration.objects.create(
            wiki=self.wiki,
            revertrisk_threshold=0.7,
        )

    @mock.patch("reviews.autoreview.pywikibot.Site")
    def test_revertrisk_disabled_when_threshold_zero(self, mock_site):
        """When threshold is 0.0, revertrisk check should be disabled."""
        self.config.revertrisk_threshold = 0.0
        self.config.save()

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=123,
            title="Test Page",
            stable_revid=100,
        )

        PendingRevision.objects.create(
            page=page,
            revid=200,
            parentid=100,
            user_name="TestUser",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash",
            comment="Test edit",
            change_tags=[],
            wikitext="Test content",
            categories=[],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        # Find the revertrisk test
        revertrisk_test = next(
            (t for t in result["tests"] if t["id"] == "revertrisk"),
            None
        )
        self.assertIsNotNone(revertrisk_test)
        self.assertEqual(revertrisk_test["status"], "ok")
        self.assertIn("disabled", revertrisk_test["message"])

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_high_revertrisk_blocks_approval(self, mock_fetch, mock_site):
        """High revertrisk score should block auto-approval."""
        # Mock API response with high risk score
        mock_response = mock.Mock()
        mock_response.text = '{"output": {"probabilities": {"true": 0.85, "false": 0.15}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=456,
            title="Risky Page",
            stable_revid=300,
        )

        PendingRevision.objects.create(
            page=page,
            revid=400,
            parentid=300,
            user_name="RegularUser",
            user_id=2,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash2",
            comment="Potentially risky edit",
            change_tags=[],
            wikitext="Risky content",
            categories=[],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        # Decision should be blocked
        self.assertEqual(result["decision"]["status"], "blocked")
        self.assertIn("revert risk", result["decision"]["reason"].lower())

        # Find the revertrisk test
        revertrisk_test = next(
            (t for t in result["tests"] if t["id"] == "revertrisk"),
            None
        )
        self.assertIsNotNone(revertrisk_test)
        self.assertEqual(revertrisk_test["status"], "fail")
        self.assertEqual(revertrisk_test["revertrisk_score"], 0.85)

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_low_revertrisk_allows_continuation(self, mock_fetch, mock_site):
        """Low revertrisk score should allow other checks to continue."""
        # Mock API response with low risk score
        mock_response = mock.Mock()
        mock_response.text = '{"output": {"probabilities": {"true": 0.05, "false": 0.95}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=789,
            title="Safe Page",
            stable_revid=500,
        )

        PendingRevision.objects.create(
            page=page,
            revid=600,
            parentid=500,
            user_name="SafeUser",
            user_id=3,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash3",
            comment="Safe edit",
            change_tags=[],
            wikitext="Safe content",
            categories=[],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        # Find the revertrisk test
        revertrisk_test = next(
            (t for t in result["tests"] if t["id"] == "revertrisk"),
            None
        )
        self.assertIsNotNone(revertrisk_test)
        self.assertEqual(revertrisk_test["status"], "ok")
        self.assertEqual(revertrisk_test["revertrisk_score"], 0.05)
        self.assertIn("Low revert risk", revertrisk_test["message"])

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_revertrisk_api_failure_does_not_block(self, mock_fetch, mock_site):
        """API failure should not block approval (fail-open behavior)."""
        # Mock API failure
        mock_fetch.side_effect = Exception("API unavailable")

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=999,
            title="API Test Page",
            stable_revid=700,
        )

        PendingRevision.objects.create(
            page=page,
            revid=800,
            parentid=700,
            user_name="TestUser",
            user_id=4,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash4",
            comment="Test edit",
            change_tags=[],
            wikitext="Test content",
            categories=[],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        # Should not be blocked due to API failure
        self.assertNotEqual(result["decision"]["status"], "blocked")

        # Find the revertrisk test
        revertrisk_test = next(
            (t for t in result["tests"] if t["id"] == "revertrisk"),
            None
        )
        self.assertIsNotNone(revertrisk_test)
        self.assertEqual(revertrisk_test["status"], "not_ok")
        self.assertIsNone(revertrisk_test["revertrisk_score"])
        self.assertIn("Failed to fetch", revertrisk_test["message"])

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_revertrisk_with_bot_user(self, mock_fetch, mock_site):
        """Bot users should be auto-approved regardless of revertrisk score."""
        # Mock API response with high risk score
        mock_response = mock.Mock()
        mock_response.text = '{"output": {"probabilities": {"true": 0.95, "false": 0.05}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1234,
            title="Bot Page",
            stable_revid=900,
        )

        PendingRevision.objects.create(
            page=page,
            revid=1000,
            parentid=900,
            user_name="BotUser",
            user_id=5,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash5",
            comment="Bot edit",
            change_tags=[],
            wikitext="Bot content",
            categories=[],
            superset_data={"rc_bot": True},
        )

        EditorProfile.objects.create(
            wiki=self.wiki,
            username="BotUser",
            usergroups=["bot"],
            is_bot=True,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        # Bot should be approved without checking revertrisk
        self.assertEqual(result["decision"]["status"], "approve")

        # Revertrisk test should not be present since bot check passes first
        revertrisk_test = next(
            (t for t in result["tests"] if t["id"] == "revertrisk"),
            None
        )
        self.assertIsNone(revertrisk_test)

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_revertrisk_score_included_in_message(self, mock_fetch, mock_site):
        """Revertrisk score should be included in test message."""
        # Mock API response
        mock_response = mock.Mock()
        mock_response.text = '{"output": {"probabilities": {"true": 0.42, "false": 0.58}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=5555,
            title="Score Test Page",
            stable_revid=1100,
        )

        PendingRevision.objects.create(
            page=page,
            revid=1200,
            parentid=1100,
            user_name="TestUser",
            user_id=6,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash6",
            comment="Test",
            change_tags=[],
            wikitext="Content",
            categories=[],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        data = response.json()
        result = data["results"][0]

        revertrisk_test = next(
            (t for t in result["tests"] if t["id"] == "revertrisk"),
            None
        )
        self.assertIsNotNone(revertrisk_test)
        self.assertIn("0.420", revertrisk_test["message"])
        self.assertIn("0.700", revertrisk_test["message"])

    @mock.patch("reviews.autoreview.http.fetch")
    def test_get_revertrisk_score_function(self, mock_fetch):
        """Test the _get_revertrisk_score helper function."""
        # Mock successful response
        mock_response = mock.Mock()
        mock_response.text = '{"output": {"probabilities": {"true": 0.75, "false": 0.25}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=6666,
            title="Function Test Page",
            stable_revid=1300,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=1400,
            parentid=1300,
            user_name="TestUser",
            user_id=7,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash7",
            comment="Test",
            change_tags=[],
            wikitext="Content",
            categories=[],
            superset_data={},
        )

        score = _get_revertrisk_score(revision)
        self.assertEqual(score, 0.75)

        # Verify the API was called with correct parameters
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args
        self.assertEqual(call_args[1]["method"], "POST")
        self.assertIn("revertrisk", call_args[0][0])

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_threshold_boundary_condition(self, mock_fetch, mock_site):
        """Test that score exactly at threshold is not blocked."""
        # Mock API response with score equal to threshold
        mock_response = mock.Mock()
        mock_response.text = '{"output": {"probabilities": {"true": 0.7, "false": 0.3}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=7777,
            title="Boundary Test Page",
            stable_revid=1500,
        )

        PendingRevision.objects.create(
            page=page,
            revid=1600,
            parentid=1500,
            user_name="TestUser",
            user_id=8,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash8",
            comment="Test",
            change_tags=[],
            wikitext="Content",
            categories=[],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        data = response.json()
        result = data["results"][0]

        # Score equal to threshold should not block
        self.assertNotEqual(result["decision"]["status"], "blocked")

        revertrisk_test = next(
            (t for t in result["tests"] if t["id"] == "revertrisk"),
            None
        )
        self.assertIsNotNone(revertrisk_test)
        self.assertEqual(revertrisk_test["status"], "ok")
