from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from reviews.autoreview.checks.auto_approved_groups import check_auto_approved_groups
from reviews.autoreview.context import CheckContext


class AutoApprovedGroupsTests(TestCase):
    def test_user_in_auto_approved_group(self):
        mock_revision = MagicMock()
        mock_revision.superset_data = {"user_groups": ["sysop", "user"]}
        mock_revision.user_name = "AdminUser"

        mock_profile = MagicMock()
        mock_profile.usergroups = ["sysop", "user"]

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=mock_profile,
            auto_groups={"sysop": "sysop", "bureaucrat": "bureaucrat"},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_auto_approved_groups(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")
        self.assertTrue(result.should_stop)
        self.assertIn("sysop", result.message)

    def test_user_not_in_auto_approved_group(self):
        mock_revision = MagicMock()
        mock_revision.superset_data = {"user_groups": ["user"]}
        mock_revision.user_name = "RegularUser"

        mock_profile = MagicMock()
        mock_profile.usergroups = ["user"]
        mock_profile.is_autoreviewed = False

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=mock_profile,
            auto_groups={"sysop": "sysop", "bureaucrat": "bureaucrat"},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_auto_approved_groups(context)
        self.assertEqual(result.status, "not_ok")
        self.assertIn("does not belong", result.message)

    def test_user_with_default_autoreview_rights(self):
        mock_revision = MagicMock()
        mock_revision.superset_data = {"user_groups": ["user", "autoreviewer"]}
        mock_revision.user_name = "AutoreviewUser"

        mock_profile = MagicMock()
        mock_profile.usergroups = ["user", "autoreviewer"]
        mock_profile.is_autoreviewed = True
        mock_profile.is_autopatrolled = False

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=mock_profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_auto_approved_groups(context)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.decision.status, "approve")
        self.assertTrue(result.should_stop)
        self.assertIn("Autoreviewed", result.message)

    def test_user_without_autoreview_rights(self):
        mock_revision = MagicMock()
        mock_revision.superset_data = {"user_groups": ["user"]}
        mock_revision.user_name = "NewUser"

        mock_profile = MagicMock()
        mock_profile.usergroups = ["user"]
        mock_profile.is_autoreviewed = False
        mock_profile.is_autopatrolled = False

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=mock_profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_auto_approved_groups(context)
        self.assertEqual(result.status, "not_ok")
        self.assertIn("does not have default auto-approval rights", result.message)

    def test_user_with_autopatrolled_but_not_autoreviewed(self):
        mock_revision = MagicMock()
        mock_revision.superset_data = {"user_groups": ["user", "autopatrolled"]}
        mock_revision.user_name = "AutopatrolledUser"

        mock_profile = MagicMock()
        mock_profile.usergroups = ["user", "autopatrolled"]
        mock_profile.is_autoreviewed = False
        mock_profile.is_autopatrolled = True

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=mock_profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_auto_approved_groups(context)
        self.assertEqual(result.status, "not_ok")
        self.assertIn("does not have autoreview rights", result.message)

    def test_no_profile_no_auto_groups(self):
        mock_revision = MagicMock()
        mock_revision.superset_data = {"user_groups": ["user"]}
        mock_revision.user_name = "UnknownUser"

        context = CheckContext(
            revision=mock_revision,
            client=MagicMock(),
            profile=None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=[],
        )

        result = check_auto_approved_groups(context)
        self.assertEqual(result.status, "not_ok")
