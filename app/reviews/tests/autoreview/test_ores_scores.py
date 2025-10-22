"""Tests for ORES score checks."""
from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase

from reviews.autoreview.checks.ores_scores import check_ores_scores
from reviews.autoreview.context import CheckContext


class OresScoreTests(TestCase):
    """Test ORES damaging and goodfaith score checks."""

    def _create_context(self, revision, damaging_threshold=0.7, goodfaith_threshold=0.5):
        wiki = revision.page.wiki

        if hasattr(wiki, "_state") and not wiki._state.adding:
            from reviews.models import WikiConfiguration

            config, _ = WikiConfiguration.objects.get_or_create(wiki=wiki)
            config.ores_damaging_threshold = damaging_threshold
            config.ores_goodfaith_threshold = goodfaith_threshold
            config.ores_damaging_threshold_living = 0.1
            config.ores_goodfaith_threshold_living = 0.9
            config.save()

            wiki_configuration = config
        else:
            wiki_configuration = MagicMock()
            wiki_configuration.ores_damaging_threshold = damaging_threshold
            wiki_configuration.ores_goodfaith_threshold = goodfaith_threshold
            wiki_configuration.ores_damaging_threshold_living = 0.1
            wiki_configuration.ores_goodfaith_threshold_living = 0.9

        revision.page.wiki.configuration = wiki_configuration

        return CheckContext(
            revision=revision,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[]
        )

    @patch("reviews.autoreview.utils.living_person.is_living_person", return_value=False)
    @patch("reviews.models.ModelScores.objects.create")
    @patch("reviews.models.ModelScores.objects.get")
    @patch("reviews.autoreview.utils.ores.http.fetch")
    def test_ores_damaging_score_exceeds_threshold(
        self, mock_fetch, mock_model_scores_get, mock_model_scores_create, mock_is_living_person
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

        context = self._create_context(
                      mock_revision, damaging_threshold=0.7, goodfaith_threshold=0.0)
        result = check_ores_scores(context)

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.decision.status, "blocked")
        self.assertIn("0.850", result.message)

    @patch("reviews.autoreview.utils.living_person.is_living_person", return_value=False)
    @patch("reviews.models.ModelScores.objects.create")
    @patch("reviews.models.ModelScores.objects.get")
    @patch("reviews.autoreview.utils.ores.http.fetch")
    def test_ores_goodfaith_score_below_threshold(
        self, mock_fetch, mock_model_scores_get, mock_model_scores_create, mock_is_living_person
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
                                    "probability": {"true": 0.25, "false": 0.75},
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

        context = self._create_context(
                      mock_revision, damaging_threshold=0.0, goodfaith_threshold=0.5)
        result = check_ores_scores(context)

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.decision.status, "blocked")
        self.assertIn("0.250", result.message)

    @patch("reviews.autoreview.utils.living_person.is_living_person", return_value=False)
    @patch("reviews.models.ModelScores.objects.create")
    @patch("reviews.models.ModelScores.objects.get")
    @patch("reviews.autoreview.utils.ores.http.fetch")
    def test_ores_scores_within_thresholds(
        self, mock_fetch, mock_model_scores_get, mock_model_scores_create, mock_is_living_person
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
                                    "probability": {"true": 0.15, "false": 0.85},
                                }
                            },
                            "goodfaith": {
                                "score": {
                                    "prediction": True,
                                    "probability": {"true": 0.85, "false": 0.15},
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

        context = self._create_context(
                      mock_revision, damaging_threshold=0.7, goodfaith_threshold=0.5)
        result = check_ores_scores(context)

        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.decision)

    @patch("reviews.autoreview.utils.living_person.is_living_person", return_value=False)
    def test_ores_checks_disabled_when_thresholds_zero(self, mock_is_living_person):
        """Test that ORES checks are skipped when thresholds are 0.0."""

        mock_revision = MagicMock()
        mock_revision.page.wiki.code = "fi"
        mock_revision.revid = 12345
        mock_revision.page.wiki.code = "fi"
        mock_revision.page.wiki.family = "wikipedia"

        context = self._create_context(
                      mock_revision, damaging_threshold=0.0, goodfaith_threshold=0.0)
        result = check_ores_scores(context)

        self.assertEqual(result.status, "skip")
        self.assertIn("disabled", result.message)

    @patch("reviews.autoreview.utils.living_person.is_living_person", return_value=False)
    @patch("reviews.models.ModelScores.objects.create")
    @patch("reviews.models.ModelScores.objects.get")
    @patch("reviews.autoreview.utils.ores.http.fetch")
    def test_ores_scores_are_cached(
        self, mock_fetch, mock_model_scores_get, mock_model_scores_create, mock_is_living_person
    ):
        """Test that ORES scores are cached in the database after fetching."""
        from reviews.models import ModelScores, PendingPage, PendingRevision, Wiki

        # Create real models for this test
        wiki = Wiki.objects.create(
            code="fi",
            family="wikipedia",
            name="Finnish Wikipedia",
            api_endpoint="https://fi.wikipedia.org/w/api.php",
        )

        page = PendingPage.objects.create(
            wiki=wiki,
            pageid=123,
            title="Test Page",
            stable_revid=12340,

        )

        revision = PendingRevision.objects.create(
            revid=12345,
            page=page,
            comment="Test edit",
            timestamp="2025-10-10 01:01:01Z",
            age_at_fetch = timedelta(hours=4),
        )

        # First call - no cache
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
                                    "probability": {"true": 0.15, "false": 0.85},
                                }
                            },
                            "goodfaith": {
                                "score": {
                                    "prediction": True,
                                    "probability": {"true": 0.85, "false": 0.15},
                                }
                            },
                        }
                    }
                }
            }
        )
        mock_fetch.return_value = mock_response

        context = self._create_context(revision, damaging_threshold=0.7, goodfaith_threshold=0.5)
        result1 = check_ores_scores(context)

        # Verify cache was created
        self.assertTrue(mock_model_scores_create.called)
        self.assertEqual(result1.status, "ok")
