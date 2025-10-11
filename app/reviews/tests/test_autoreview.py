import unittest
import logging
from unittest.mock import patch, MagicMock
from reviews.autoreview import _evaluate_revision, _get_revertrisk_score

logging.disable(logging.CRITICAL)

class DummyRevision:
    def __init__(self, revid=12345, user_name="TestUser", superset_data=None):
        self.revid = revid
        self.user_name = user_name
        self.page = MagicMock()
        self.page.categories = []
        self.page.wiki = MagicMock()
        self.page.wiki.language_code = "en"
        self.superset_data = superset_data or {}

    def get_categories(self):
        return []

class TestRevertrisk(unittest.TestCase):

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    @patch("reviews.autoreview._get_revertrisk_score")
    def test_high_risk_blocks(self, mock_score, mock_bot_edit):
        mock_score.return_value = 0.9
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "blocked")

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    @patch("reviews.autoreview._get_revertrisk_score")
    def test_low_risk_continues(self, mock_score, mock_bot_edit):
        mock_score.return_value = 0.5
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "manual")

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    @patch("reviews.autoreview._get_revertrisk_score")
    def test_api_error_handled(self, mock_score, mock_bot_edit):
        mock_score.return_value = None
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "manual")

    @patch("reviews.autoreview._get_revertrisk_score")
    def test_bot_bypasses_check(self, mock_score):
        revision = DummyRevision(superset_data={"rc_bot": True})
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "approve")
        mock_score.assert_not_called()

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    def test_no_threshold_skips_check(self, mock_bot_edit):
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=None
        )
        self.assertFalse(any(t["id"] == "revertrisk" for t in result["tests"]))

    @patch("reviews.autoreview.http.fetch")
    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    def test_api_exception_returns_none(self, mock_bot_edit, mock_fetch):
        mock_fetch.side_effect = Exception("Network error")
        score = _get_revertrisk_score(DummyRevision())
        self.assertIsNone(score)


if __name__ == "__main__":
    unittest.main()
from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

from reviews import autoreview
from reviews.services import was_user_blocked_after


class AutoreviewBlockedUserTests(TestCase):
    def setUp(self):
        """Clear the LRU cache before each test."""
        was_user_blocked_after.cache_clear()

    @patch("reviews.services.pywikibot.Site")
    @patch("reviews.autoreview._is_bot_user")
    def test_blocked_user_not_auto_approved(self, mock_is_bot, mock_site):
        """Test that a user blocked after making an edit is NOT auto-approved."""
        mock_is_bot.return_value = False  # User is NOT a bot

        # Mock the pywikibot.Site and logevents to return a block event
        mock_site_instance = MagicMock()
        mock_site.return_value = mock_site_instance

        # Create a mock block event
        mock_block_event = MagicMock()
        mock_block_event.action.return_value = "block"
        mock_site_instance.logevents.return_value = [mock_block_event]

        profile = MagicMock()
        profile.usergroups = []
        profile.is_bot = False

        mock_wiki = MagicMock()
        mock_wiki.code = "fi"
        mock_wiki.family = "wikipedia"

        revision = MagicMock()
        revision.user_name = "BlockedUser"
        revision.timestamp = datetime.fromisoformat("2024-01-15T10:00:00")
        revision.page.categories = []
        revision.page.wiki = mock_wiki

        # Create a mock WikiClient - but we need the real is_user_blocked_after_edit method
        from reviews.services import WikiClient

        mock_client = WikiClient(mock_wiki)

        # Call with correct signature: revision, client, profile, **kwargs
        result = autoreview._evaluate_revision(
            revision,
            mock_client,
            profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases={},
        )

        # Assert
        self.assertEqual(result["decision"].status, "blocked")
        self.assertTrue(any(t["id"] == "blocked-user" for t in result["tests"]))

        # Verify pywikibot.Site was called (will be called twice:
        # once in WikiClient.__init__, once in was_user_blocked_after)
        self.assertGreaterEqual(mock_site.call_count, 1)

        # Verify logevents was called with correct parameters
        mock_site_instance.logevents.assert_called_once()
