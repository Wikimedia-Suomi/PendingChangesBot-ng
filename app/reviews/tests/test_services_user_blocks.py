from __future__ import annotations

import time
from unittest import mock

from django.test import TestCase

from reviews.services.user_blocks import was_user_blocked_after


class UserBlocksTests(TestCase):
    @mock.patch("reviews.services.user_blocks.pywikibot.Site")
    def test_was_user_blocked_after_false(self, mock_site):
        mock_site.return_value.logevents.return_value = []
        result = was_user_blocked_after("en", "wikipedia", "TestUser", 2024)
        self.assertFalse(result)

    @mock.patch("reviews.services.user_blocks.logger")
    @mock.patch("reviews.services.user_blocks.pywikibot.Site")
    def test_was_user_blocked_after_exception(self, mock_site, mock_logger):
        mock_site.side_effect = Exception("API error")
        result = was_user_blocked_after("en", "wikipedia", "TestUser", 2024)
        self.assertFalse(result)

    @mock.patch("reviews.services.user_blocks.pywikibot.Site")
    def test_was_user_blocked_after_non_block_action(self, mock_site):
        class FakeEvent:
            def action(self):
                return "unblock"

        mock_site.return_value.logevents.return_value = [FakeEvent()]
        result = was_user_blocked_after("en", "wikipedia", "TestUser", 2024)
        self.assertFalse(result)

    @mock.patch("reviews.services.user_blocks.pywikibot.Site")
    def test_cache_hit_reduces_api_calls(self, mock_site):
        """Test that cache prevents redundant API calls."""
        # Clear cache before test
        was_user_blocked_after.cache_clear()

        class FakeEvent:
            def action(self):
                return "block"

        mock_site.return_value.logevents.return_value = [FakeEvent()]

        # First call - should hit API
        result1 = was_user_blocked_after("en", "wikipedia", "CachedUser", 2024)
        self.assertTrue(result1)
        self.assertEqual(mock_site.call_count, 1)

        # Second call with same params - should use cache
        result2 = was_user_blocked_after("en", "wikipedia", "CachedUser", 2024)
        self.assertTrue(result2)
        self.assertEqual(mock_site.call_count, 1)  # Still 1, not 2

    @mock.patch("reviews.services.user_blocks.time.time")
    @mock.patch("reviews.services.user_blocks.pywikibot.Site")
    def test_cache_expires_after_ttl(self, mock_site, mock_time):
        """Test that cache expires after TTL period."""
        # Clear cache before test
        was_user_blocked_after.cache_clear()

        class FakeEvent:
            def action(self):
                return "block"

        mock_site.return_value.logevents.return_value = [FakeEvent()]

        # Set initial time
        mock_time.return_value = 1000.0

        # First call at t=1000
        result1 = was_user_blocked_after("en", "wikipedia", "ExpireTest", 2024)
        self.assertTrue(result1)
        self.assertEqual(mock_site.call_count, 1)

        # Second call at t=2000 (within TTL of 3600)
        mock_time.return_value = 2000.0
        result2 = was_user_blocked_after("en", "wikipedia", "ExpireTest", 2024)
        self.assertTrue(result2)
        self.assertEqual(mock_site.call_count, 1)  # Still cached

        # Third call at t=5000 (after TTL of 3600)
        mock_time.return_value = 5000.0
        result3 = was_user_blocked_after("en", "wikipedia", "ExpireTest", 2024)
        self.assertTrue(result3)
        self.assertEqual(mock_site.call_count, 2)  # Cache expired, new API call

    def test_cache_clear_method_exists(self):
        """Test that cache_clear method is available."""
        self.assertTrue(hasattr(was_user_blocked_after, "cache_clear"))
        self.assertTrue(callable(was_user_blocked_after.cache_clear))

    def test_cache_info_method_exists(self):
        """Test that cache_info method is available for monitoring."""
        self.assertTrue(hasattr(was_user_blocked_after, "cache_info"))
        self.assertTrue(callable(was_user_blocked_after.cache_info))
