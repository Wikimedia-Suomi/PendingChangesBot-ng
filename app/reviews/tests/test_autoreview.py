from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch
from reviews import autoreview

class AutoreviewBlockedUserTests(TestCase):

    @patch('reviews.services.was_user_blocked_after')
    def test_blocked_user_not_auto_approved(self, mock_block_check):
        """Test that user blocked after edit is not auto-approved."""
        mock_block_check.return_value = True

        profile = MagicMock()
        profile.usergroups = []

        revision = MagicMock()
        revision.user_name = "BlockedUser"
        # Correct datetime assignment
        revision.timestamp = datetime.fromisoformat("2024-01-15T10:00:00")
        revision.page.categories = []

        revision.page.wiki = MagicMock()
        revision.page.wiki.code = "fi"
        revision.page.wiki.family = "wikipedia"

        result = autoreview._evaluate_revision(
            revision,
            profile,
            auto_groups={},
            blocking_categories={},
        )

        self.assertEqual(result["decision"].status, "blocked")
        self.assertTrue(any(t["id"] == "blocked-user" for t in result["tests"]))
