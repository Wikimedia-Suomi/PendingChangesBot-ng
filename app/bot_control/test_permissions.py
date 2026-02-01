"""
Tests for the permissions system.
"""

import unittest
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory

from .permissions import (
    UserRole,
    get_user_groups_from_mediawiki,
    get_user_role,
    has_permission,
    get_user_info,
    require_permission,
)


class PermissionsTestCase(TestCase):
    """Test cases for permission system."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()

    @patch("bot_control.permissions.requests.get")
    def test_get_user_groups_admin(self, mock_get):
        """Test fetching user groups for an admin."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {
                "users": [
                    {
                        "name": "AdminUser",
                        "groups": ["sysop", "autopatrolled", "*", "user"],
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        groups = get_user_groups_from_mediawiki("AdminUser", "fi", "wikipedia")

        self.assertIn("sysop", groups)
        self.assertIn("autopatrolled", groups)

    @patch("bot_control.permissions.requests.get")
    def test_get_user_groups_nonexistent_user(self, mock_get):
        """Test fetching groups for a non-existent user."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {"users": [{"name": "NonExistent", "missing": ""}]}
        }
        mock_get.return_value = mock_response

        groups = get_user_groups_from_mediawiki("NonExistent", "fi", "wikipedia")

        self.assertEqual(groups, [])

    @patch("bot_control.permissions.get_user_groups_from_mediawiki")
    def test_get_user_role_admin(self, mock_get_groups):
        """Test role determination for admin user."""
        mock_get_groups.return_value = ["sysop", "autopatrolled"]

        role = get_user_role("AdminUser")

        self.assertEqual(role, UserRole.ADMIN)

    @patch("bot_control.permissions.get_user_groups_from_mediawiki")
    def test_get_user_role_reviewer(self, mock_get_groups):
        """Test role determination for reviewer user."""
        mock_get_groups.return_value = ["reviewer", "autopatrolled"]

        role = get_user_role("ReviewerUser")

        self.assertEqual(role, UserRole.REVIEWER)

    @patch("bot_control.permissions.get_user_groups_from_mediawiki")
    def test_get_user_role_public(self, mock_get_groups):
        """Test role determination for public user."""
        mock_get_groups.return_value = ["*", "user"]

        role = get_user_role("PublicUser")

        self.assertEqual(role, UserRole.PUBLIC)

    def test_has_permission_admin_can_do_everything(self):
        """Test that admin has all permissions."""
        self.assertTrue(has_permission(UserRole.ADMIN, UserRole.ADMIN))
        self.assertTrue(has_permission(UserRole.ADMIN, UserRole.REVIEWER))
        self.assertTrue(has_permission(UserRole.ADMIN, UserRole.PUBLIC))

    def test_has_permission_reviewer_limited(self):
        """Test that reviewer has limited permissions."""
        self.assertFalse(has_permission(UserRole.REVIEWER, UserRole.ADMIN))
        self.assertTrue(has_permission(UserRole.REVIEWER, UserRole.REVIEWER))
        self.assertTrue(has_permission(UserRole.REVIEWER, UserRole.PUBLIC))

    def test_has_permission_public_readonly(self):
        """Test that public users have minimal permissions."""
        self.assertFalse(has_permission(UserRole.PUBLIC, UserRole.ADMIN))
        self.assertFalse(has_permission(UserRole.PUBLIC, UserRole.REVIEWER))
        self.assertTrue(has_permission(UserRole.PUBLIC, UserRole.PUBLIC))

    @patch("bot_control.permissions.get_user_groups_from_mediawiki")
    def test_get_user_info_admin(self, mock_get_groups):
        """Test getting comprehensive user info for admin."""
        mock_get_groups.return_value = ["sysop", "autopatrolled"]

        info = get_user_info("AdminUser", "fi", "wikipedia")

        self.assertEqual(info["username"], "AdminUser")
        self.assertEqual(info["role"], "admin")
        self.assertEqual(info["wiki"], "fi.wikipedia")
        self.assertTrue(info["permissions"]["can_start_stop_bot"])
        self.assertTrue(info["permissions"]["can_manual_review"])
        self.assertTrue(info["permissions"]["can_change_settings"])
        self.assertTrue(info["permissions"]["can_view_status"])

    @patch("bot_control.permissions.get_user_groups_from_mediawiki")
    def test_get_user_info_reviewer(self, mock_get_groups):
        """Test getting comprehensive user info for reviewer."""
        mock_get_groups.return_value = ["reviewer"]

        info = get_user_info("ReviewerUser", "fi", "wikipedia")

        self.assertEqual(info["role"], "reviewer")
        self.assertFalse(info["permissions"]["can_start_stop_bot"])
        self.assertTrue(info["permissions"]["can_manual_review"])
        self.assertFalse(info["permissions"]["can_change_settings"])
        self.assertTrue(info["permissions"]["can_view_status"])

    @patch("bot_control.permissions.get_user_role")
    def test_require_permission_decorator_allows_admin(self, mock_get_role):
        """Test that require_permission decorator allows admin users."""
        mock_get_role.return_value = UserRole.ADMIN

        @require_permission(UserRole.ADMIN)
        def protected_view(request):
            return {"success": True}

        request = self.factory.post("/test/")
        request.META["HTTP_X_WIKI_USERNAME"] = "AdminUser"

        response = protected_view(request)

        self.assertEqual(response, {"success": True})

    @patch("bot_control.permissions.get_user_role")
    def test_require_permission_decorator_blocks_public(self, mock_get_role):
        """Test that require_permission decorator blocks public users."""
        mock_get_role.return_value = UserRole.PUBLIC

        @require_permission(UserRole.ADMIN)
        def protected_view(request):
            return {"success": True}

        request = self.factory.post("/test/")
        request.META["HTTP_X_WIKI_USERNAME"] = "PublicUser"

        response = protected_view(request)

        self.assertEqual(response.status_code, 403)

    def test_require_permission_decorator_requires_auth(self):
        """Test that require_permission decorator requires authentication."""

        @require_permission(UserRole.PUBLIC)
        def protected_view(request):
            return {"success": True}

        request = self.factory.post("/test/")
        # No username in headers

        response = protected_view(request)

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
