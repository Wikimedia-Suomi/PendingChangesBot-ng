"""Tests for ORES score checks."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase, override_settings

from reviews import autoreview
from reviews.autoreview.checks.ores_scores import check_ores_scores


class OresScoreTests(TestCase):
    """Test ORES damaging and goodfaith score checks."""

    @patch("reviews.models.ModelScores.objects.create")
    @patch("reviews.models.ModelScores.objects.get")
    @patch("reviews.autoreview.utils.ores.http.fetch")
    def test_ores_damaging_score_exceeds_threshold(
        self, mock_fetch, mock_model_scores_get, mock_model_scores_create
    ):
        """Test that high damaging score blocks auto-approval."""
        from reviews.models import ModelScores

        mock_model_scores_get.side_effect = ModelScores.DoesNotExist()
        mock_model_scores_create.return_value = MagicMock()

        mock_response = Mock()
        mock_response.headers = {}
        mock_response.text = json.dumps(
            {
                "fiwiki": {
                    "scores": {
                        "12345": {
                            "damaging": {
                                "score": {
                                    "prediction": True,
                                    "probability": {"true": 0.85, "false": 0.15},
                                }
                            }
                        }
                    }
                }
            }
        )
        mock_fetch.return_value = mock_response

        mock_revision = MagicMock()
        mock_revision.revid = 12345
        mock_revision.page.wiki.code = "fi"
        mock_revision.page.wiki.family = "wikipedia"

        result = check_ores_scores(mock_revision, damaging_threshold=0.7, goodfaith_threshold=0.0)

        self.assertTrue(result["should_block"])
        self.assertEqual(result["test"]["status"], "fail")
        self.assertIn("0.850", result["test"]["message"])

    @patch("reviews.models.ModelScores.objects.create")
    @patch("reviews.models.ModelScores.objects.get")
    @patch("reviews.autoreview.utils.ores.http.fetch")
    def test_ores_goodfaith_score_below_threshold(
        self, mock_fetch, mock_model_scores_get, mock_model_scores_create
    ):
        """Test that low goodfaith score blocks auto-approval."""
        from reviews.models import ModelScores

        mock_model_scores_get.side_effect = ModelScores.DoesNotExist()
        mock_model_scores_create.return_value = MagicMock()

        mock_response = Mock()
        mock_response.headers = {}
        mock_response.text = json.dumps(
            {
                "fiwiki": {
                    "scores": {
                        "12345": {
                            "goodfaith": {
                                "score": {
                                    "prediction": False,
                                    "probability": {"true": 0.3, "false": 0.7},
                                }
                            }
                        }
                    }
                }
            }
        )
        mock_fetch.return_value = mock_response

        mock_revision = MagicMock()
        mock_revision.revid = 12345
        mock_revision.page.wiki.code = "fi"
        mock_revision.page.wiki.family = "wikipedia"

        result = check_ores_scores(mock_revision, damaging_threshold=0.0, goodfaith_threshold=0.5)

        self.assertTrue(result["should_block"])
        self.assertEqual(result["test"]["status"], "fail")
        self.assertIn("0.300", result["test"]["message"])

    @patch("reviews.models.ModelScores.objects.create")
    @patch("reviews.models.ModelScores.objects.get")
    @patch("reviews.autoreview.utils.ores.http.fetch")
    def test_ores_scores_within_thresholds(
        self, mock_fetch, mock_model_scores_get, mock_model_scores_create
    ):
        """Test that good scores pass the check."""
        from reviews.models import ModelScores

        mock_model_scores_get.side_effect = ModelScores.DoesNotExist()
        mock_model_scores_create.return_value = MagicMock()

        mock_response = Mock()
        mock_response.headers = {}
        mock_response.text = json.dumps(
            {
                "fiwiki": {
                    "scores": {
                        "12345": {
                            "damaging": {
                                "score": {
                                    "prediction": False,
                                    "probability": {"true": 0.02, "false": 0.98},
                                }
                            },
                            "goodfaith": {
                                "score": {
                                    "prediction": True,
                                    "probability": {"true": 0.999, "false": 0.001},
                                }
                            },
                        }
                    }
                }
            }
        )
        mock_fetch.return_value = mock_response

        mock_revision = MagicMock()
        mock_revision.revid = 12345
        mock_revision.page.wiki.code = "fi"
        mock_revision.page.wiki.family = "wikipedia"

        result = check_ores_scores(mock_revision, damaging_threshold=0.7, goodfaith_threshold=0.5)

        self.assertFalse(result["should_block"])
        self.assertEqual(result["test"]["status"], "ok")
        self.assertIn("damaging: 0.020", result["test"]["message"])
        self.assertIn("goodfaith: 0.999", result["test"]["message"])

    def test_ores_checks_disabled_when_thresholds_zero(self):
        """Test that ORES checks are skipped when thresholds are 0.0."""
        mock_revision = MagicMock()
        mock_revision.revid = 12345
        mock_revision.page.wiki.code = "fi"
        mock_revision.page.wiki.family = "wikipedia"

        result = check_ores_scores(mock_revision, damaging_threshold=0.0, goodfaith_threshold=0.0)

        self.assertFalse(result["should_block"])
        self.assertEqual(result["test"]["status"], "skip")
        self.assertIn("disabled", result["test"]["message"])

    def test_ores_scores_are_cached(self):
        """Test that ORES scores are cached in the database after fetching."""
        from reviews.models import ModelScores, PendingPage, PendingRevision, Wiki

        wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

        page = PendingPage.objects.create(
            wiki=wiki, pageid=123, title="Test Page", stable_revid=999
        )

        revision = PendingRevision.objects.create(
            page=page,
            revid=12345,
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            age_at_fetch=timedelta(hours=1),
            sha1="abc123",
            wikitext="Test content",
        )

        with patch("reviews.autoreview.utils.ores.http.fetch") as mock_fetch:
            mock_response = Mock()
            mock_response.text = json.dumps(
                {
                    "testwiki": {
                        "scores": {
                            "12345": {
                                "damaging": {
                                    "score": {"probability": {"true": 0.15, "false": 0.85}}
                                },
                                "goodfaith": {
                                    "score": {"probability": {"true": 0.92, "false": 0.08}}
                                },
                            }
                        }
                    }
                }
            )
            mock_fetch.return_value = mock_response

            result1 = check_ores_scores(revision, damaging_threshold=0.7, goodfaith_threshold=0.5)

            mock_fetch.assert_called_once()
            self.assertFalse(result1["should_block"])
            self.assertEqual(result1["test"]["status"], "ok")

            # Verify scores are cached
            model_scores = ModelScores.objects.get(revision=revision)
            self.assertEqual(model_scores.ores_damaging_score, 0.15)
            self.assertEqual(model_scores.ores_goodfaith_score, 0.92)

            # Second call should use cache
            result2 = check_ores_scores(revision, damaging_threshold=0.7, goodfaith_threshold=0.5)
            mock_fetch.assert_called_once()  # Still only called once

