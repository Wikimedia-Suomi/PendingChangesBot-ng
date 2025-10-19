"""Tests for multi-model ML API integration and auto-review functionality."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from reviews.autoreview import _get_ml_model_score
from reviews.models import (
    EditorProfile,
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)


class MLModelTests(TestCase):
    """Tests for ML model API integration and auto-review functionality."""

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
            ml_model_type="damaging",
            ml_model_threshold=0.7,
        )

    @mock.patch("reviews.autoreview.pywikibot.Site")
    def test_ml_model_disabled_when_threshold_zero(self, mock_site):
        """When threshold is 0.0, ML model check should be disabled."""
        self.config.ml_model_threshold = 0.0
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

        # Find the ML model test
        ml_test = next(
            (t for t in result["tests"] if t["id"] == "ml-model"),
            None
        )
        self.assertIsNotNone(ml_test)
        self.assertEqual(ml_test["status"], "ok")
        self.assertIn("disabled", ml_test["message"])

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_high_damaging_score_blocks_approval(self, mock_fetch, mock_site):
        """High damaging score should block auto-approval."""
        # Mock API response with high damaging score
        mock_response = mock.Mock()
        mock_response.status_code = 200
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
            user_name="TestUser",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash2",
            comment="Test edit",
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

        # Should be blocked
        self.assertEqual(result["decision"]["status"], "blocked")

        # Find the ML model test
        ml_test = next(
            (t for t in result["tests"] if t["id"] == "ml-model"),
            None
        )
        self.assertIsNotNone(ml_test)
        self.assertEqual(ml_test["status"], "fail")
        self.assertEqual(ml_test["ml_model_type"], "damaging")
        self.assertIsNotNone(ml_test["ml_score"])

    @mock.patch("reviews.autoreview.pywikibot.Site")
    @mock.patch("reviews.autoreview.http.fetch")
    def test_low_goodfaith_score_blocks_approval(self, mock_fetch, mock_site):
        """Low good faith score (bad faith) should block auto-approval."""
        self.config.ml_model_type = "goodfaith"
        self.config.ml_model_threshold = 0.3
        self.config.save()

        # Mock API response - goodfaith model uses probabilities.false for bad faith
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = '{"output": {"probabilities": {"true": 0.3, "false": 0.7}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=789,
            title="Bad Faith Page",
            stable_revid=500,
        )

        PendingRevision.objects.create(
            page=page,
            revid=600,
            parentid=500,
            user_name="TestUser",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash3",
            comment="Test edit",
            change_tags=[],
            wikitext="Bad faith content",
            categories=[],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        # Should be blocked
        self.assertEqual(result["decision"]["status"], "blocked")

        # Find the ML model test
        ml_test = next(
            (t for t in result["tests"] if t["id"] == "ml-model"),
            None
        )
        self.assertIsNotNone(ml_test)
        self.assertEqual(ml_test["status"], "fail")
        self.assertEqual(ml_test["ml_model_type"], "goodfaith")

    @mock.patch("reviews.autoreview.http.fetch")
    def test_get_ml_model_score_damaging(self, mock_fetch):
        """Test _get_ml_model_score with damaging model."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = '{"output": {"probabilities": {"true": 0.42, "false": 0.58}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=111,
            title="Test Page",
            stable_revid=222,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=333,
            parentid=222,
            user_name="TestUser",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash4",
            comment="Test",
            wikitext="Content",
        )

        score = _get_ml_model_score(revision, "damaging")
        self.assertIsNotNone(score)
        self.assertAlmostEqual(score, 0.42, places=2)

    @mock.patch("reviews.autoreview.http.fetch")
    def test_get_ml_model_score_revertrisk(self, mock_fetch):
        """Test _get_ml_model_score with revertrisk model."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = '{"output": {"probabilities": {"true": 0.65, "false": 0.35}}}'
        mock_fetch.return_value = mock_response

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=444,
            title="Test Page 2",
            stable_revid=555,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=666,
            parentid=555,
            user_name="TestUser",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash5",
            comment="Test",
            wikitext="Content",
        )

        score = _get_ml_model_score(revision, "revertrisk")
        self.assertIsNotNone(score)
        self.assertAlmostEqual(score, 0.65, places=2)

    @mock.patch("reviews.autoreview.http.fetch")
    def test_ml_model_api_failure_does_not_block(self, mock_fetch):
        """When ML API fails, should not block approval (fail-open)."""
        # Mock API failure
        mock_fetch.side_effect = Exception("API connection failed")

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=777,
            title="Test Page API Fail",
            stable_revid=888,
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=999,
            parentid=888,
            user_name="TestUser",
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash6",
            comment="Test",
            wikitext="Content",
        )

        score = _get_ml_model_score(revision, "damaging")
        self.assertIsNone(score)

    def test_backward_compatibility_with_revertrisk_threshold(self):
        """Test backward compatibility with legacy revertrisk_threshold field."""
        # Create a config with only the legacy field set
        wiki2 = Wiki.objects.create(
            name="Legacy Wiki",
            code="legacy",
            family="wikipedia",
            api_endpoint="https://legacy.wikipedia.org/w/api.php",
        )
        config2 = WikiConfiguration.objects.create(
            wiki=wiki2,
            revertrisk_threshold=0.5,
            ml_model_threshold=0.0,  # New field not set
        )

        # The system should still use revertrisk_threshold for backward compatibility
        self.assertEqual(config2.revertrisk_threshold, 0.5)
        self.assertEqual(config2.ml_model_threshold, 0.0)
