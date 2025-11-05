"""Tests for autoreview timing functionality."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from reviews.autoreview.runner import run_checks_pipeline


class AutoreviewTimingTests(TestCase):
    """Test that timing information is captured correctly."""

    def test_checks_include_duration_ms(self):
        """Test that each check result includes duration_ms field."""
        # Setup mocks
        mock_wiki = MagicMock()
        mock_wiki.code = "en"
        mock_wiki.family = "wikipedia"
        mock_wiki.configuration = MagicMock()
        mock_wiki.configuration.enabled_checks = ["broken-wikicode"]  # Run only one check

        mock_page = MagicMock()
        mock_page.wiki = mock_wiki
        mock_page.categories = []

        revision = MagicMock()
        revision.page = mock_page
        revision.user_name = "TestUser"
        revision.wikitext = "Some test content"
        revision.superset_data = {}
        revision.parentid = None  # No parent revision
        revision.change_tags = []
        revision.get_rendered_html.return_value = "<p>Test content</p>"

        mock_client = MagicMock()
        mock_profile = MagicMock()

        # Run the pipeline
        result = run_checks_pipeline(
            revision=revision,
            client=mock_client,
            profile=mock_profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        # Assert that tests have duration_ms
        self.assertIn("tests", result)
        self.assertGreater(len(result["tests"]), 0)

        for test in result["tests"]:
            self.assertIn("duration_ms", test)
            self.assertIsInstance(test["duration_ms"], float)
            self.assertGreaterEqual(test["duration_ms"], 0)

    def test_pipeline_includes_total_duration_ms(self):
        """Test that pipeline result includes total_duration_ms field."""
        # Setup mocks
        mock_wiki = MagicMock()
        mock_wiki.code = "en"
        mock_wiki.family = "wikipedia"
        mock_wiki.configuration = MagicMock()
        mock_wiki.configuration.enabled_checks = ["broken-wikicode", "manual-unapproval"]

        mock_page = MagicMock()
        mock_page.wiki = mock_wiki
        mock_page.categories = []

        revision = MagicMock()
        revision.page = mock_page
        revision.user_name = "TestUser"
        revision.wikitext = "Some test content"
        revision.superset_data = {}
        revision.parentid = None
        revision.change_tags = []
        revision.get_rendered_html.return_value = "<p>Test content</p>"

        mock_client = MagicMock()
        mock_client.has_manual_unapproval.return_value = False

        mock_profile = MagicMock()

        # Run the pipeline
        result = run_checks_pipeline(
            revision=revision,
            client=mock_client,
            profile=mock_profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        # Assert that result has total_duration_ms
        self.assertIn("total_duration_ms", result)
        self.assertIsInstance(result["total_duration_ms"], float)
        self.assertGreaterEqual(result["total_duration_ms"], 0)

    def test_duration_is_reasonable(self):
        """Test that timing measurements are reasonable (not zero, not huge)."""
        # Setup mocks
        mock_wiki = MagicMock()
        mock_wiki.code = "en"
        mock_wiki.family = "wikipedia"
        mock_wiki.configuration = MagicMock()
        mock_wiki.configuration.enabled_checks = ["broken-wikicode"]

        mock_page = MagicMock()
        mock_page.wiki = mock_wiki
        mock_page.categories = []

        revision = MagicMock()
        revision.page = mock_page
        revision.user_name = "TestUser"
        revision.wikitext = "Some test content"
        revision.superset_data = {}
        revision.parentid = None
        revision.change_tags = []
        revision.get_rendered_html.return_value = "<p>Test content</p>"

        mock_client = MagicMock()
        mock_profile = MagicMock()

        # Run the pipeline
        result = run_checks_pipeline(
            revision=revision,
            client=mock_client,
            profile=mock_profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        # Assert that durations are reasonable (between 0 and 10000ms)
        for test in result["tests"]:
            self.assertGreater(test["duration_ms"], 0)
            self.assertLess(test["duration_ms"], 10000)  # 10 seconds max

        # Total duration should be at least the sum of individual durations
        total = result["total_duration_ms"]
        sum_of_tests = sum(test["duration_ms"] for test in result["tests"])
        self.assertGreaterEqual(total, sum_of_tests * 0.9)  # Allow 10% tolerance

    def test_early_exit_includes_timing(self):
        """Test that early exit from blocking check still includes timing data."""
        # Setup mocks to trigger early exit
        mock_wiki = MagicMock()
        mock_wiki.code = "en"
        mock_wiki.family = "wikipedia"
        mock_wiki.configuration = MagicMock()
        mock_wiki.configuration.enabled_checks = None  # All checks

        mock_page = MagicMock()
        mock_page.wiki = mock_wiki
        mock_page.categories = []

        revision = MagicMock()
        revision.page = mock_page
        revision.user_name = "BlockedUser"
        revision.wikitext = "Some content"
        revision.superset_data = {}
        revision.parentid = None
        revision.change_tags = []
        revision.get_rendered_html.return_value = "<p>Test content</p>"

        mock_client = MagicMock()
        mock_client.has_manual_unapproval.return_value = False
        mock_client.is_user_blocked_after_edit.return_value = True  # Trigger block

        mock_profile = MagicMock()
        mock_profile.is_bot = False

        # Run the pipeline
        result = run_checks_pipeline(
            revision=revision,
            client=mock_client,
            profile=mock_profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        # Assert timing data is present even with early exit
        self.assertIn("total_duration_ms", result)
        self.assertIn("tests", result)
        self.assertGreater(len(result["tests"]), 0)

        # Each test should have duration
        for test in result["tests"]:
            self.assertIn("duration_ms", test)
