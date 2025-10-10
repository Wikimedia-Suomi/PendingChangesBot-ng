from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch
from reviews import autoreview


class AutoreviewBlockedUserTests(TestCase):

    @patch('reviews.services.was_user_blocked_after')
    @patch('reviews.autoreview._is_bot_user')  # ← ADD THIS MOCK
    def test_blocked_user_not_auto_approved(self, mock_is_bot, mock_block_check):
        """Test that user blocked after edit is not auto-approved."""
        mock_is_bot.return_value = False  # ← User is NOT a bot
        mock_block_check.return_value = True  # ← User WAS blocked

        profile = MagicMock()
        profile.usergroups = []
        profile.is_bot = False  # ← Explicitly set

        mock_wiki = MagicMock()
        mock_wiki.code = "fi"
        mock_wiki.family = "wikipedia"

        revision = MagicMock()
        revision.user_name = "BlockedUser"
        revision.timestamp = datetime.fromisoformat("2024-01-15T10:00:00")
        revision.page.categories = []
        revision.page.wiki = mock_wiki

        result = autoreview._evaluate_revision(
            revision,
            profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases={},
        )

        # Assert
        self.assertEqual(result["decision"].status, "blocked")
        self.assertTrue(any(t["id"] == "blocked-user" for t in result["tests"]))
        
        # Verify the mock was called with correct parameters
        mock_block_check.assert_called_once_with("fi", "wikipedia", "BlockedUser", 2024)