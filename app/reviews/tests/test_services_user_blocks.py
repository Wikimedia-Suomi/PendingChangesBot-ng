from __future__ import annotations

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
