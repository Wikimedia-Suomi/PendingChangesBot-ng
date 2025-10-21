"""Tests for user block checks."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from django.test import TestCase

from reviews.autoreview.checks.user_block import check_user_block
from reviews.autoreview.context import CheckContext
from reviews.services import was_user_blocked_after


class AutoreviewBlockedUserTests(TestCase):
    def setUp(self):
        """Clear the LRU cache before each test."""
        was_user_blocked_after.cache_clear()

    @patch("reviews.services.wiki_client.pywikibot.Site")
    def test_blocked_user_not_auto_approved(self, mock_site):
        """Test that a user blocked after making an edit is NOT auto-approved."""
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
        profile.is_autoreviewed = False
        profile.is_autopatrolled = False

        mock_wiki = MagicMock()
        mock_wiki.code = "fi"
        mock_wiki.family = "wikipedia"
        mock_wiki.configuration = MagicMock()
        mock_wiki.configuration.enabled_checks = None  # Run all checks

        revision = MagicMock()
        revision.user_name = "BlockedUser"
        revision.timestamp = datetime.fromisoformat("2024-01-15T10:00:00")
        revision.page.categories = []
        revision.page.wiki = mock_wiki
        revision.superset_data = {}

        # Create a mock WikiClient
        from reviews.services import WikiClient
        mock_client = WikiClient(mock_wiki)

        # Create context
        context = CheckContext(
            revision=revision,
            client=mock_client,
            profile=profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[]
        )

        # Call the check
        result = check_user_block(context)

        # Assert
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.decision.status, "blocked")
        self.assertIn("blocked", result.message.lower())

        # Verify pywikibot.Site was called
        self.assertGreaterEqual(mock_site.call_count, 1)

        # Verify logevents was called with correct parameters
        mock_site_instance.logevents.assert_called_once()
