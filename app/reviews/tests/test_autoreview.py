from unittest import TestCase
from unittest.mock import MagicMock
from reviews import autoreview

class AutoreviewBlockedUserTests(TestCase):
    def test_blocked_user_not_auto_approved(self):
        blocked_profile = MagicMock()
        blocked_profile.is_blocked = True
        blocked_profile.is_bot = False
        blocked_profile.is_autopatrolled = False
        blocked_profile.is_autoreviewed = False
        blocked_profile.usergroups = []

        revision = MagicMock()
        revision.user_name = "BlockedUser"
        revision.superset_data = {}
        revision.page.categories = []

        result = autoreview._evaluate_revision(
            revision,
            blocked_profile,
            auto_groups={},
            blocking_categories={},
        )

        self.assertEqual(result["decision"].status, "blocked")
        self.assertTrue(any(t["id"] == "blocked-user" for t in result["tests"]))