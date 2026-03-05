"""
Tests for the audit logging system: middleware, model, and API views.
"""

from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from .middleware import AuditLogMiddleware
from .models import AuditLog


class AuditLogModelTestCase(TestCase):
    """Test cases for the AuditLog model."""

    def test_create_audit_log(self):
        """Test creating an audit log entry."""
        log = AuditLog.objects.create(
            method="GET",
            path="/bot-control/",
            status_code=200,
            username="TestUser",
            role="admin",
            ip_address="127.0.0.1",
            response_time_ms=12.5,
        )
        self.assertEqual(log.method, "GET")
        self.assertEqual(log.path, "/bot-control/")
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.username, "TestUser")

    def test_ordering_is_newest_first(self):
        """Test that logs are ordered by timestamp descending."""
        AuditLog.objects.create(method="GET", path="/first", status_code=200)
        AuditLog.objects.create(method="GET", path="/second", status_code=200)
        logs = list(AuditLog.objects.all())
        self.assertEqual(logs[0].path, "/second")
        self.assertEqual(logs[1].path, "/first")

    def test_str_representation(self):
        """Test string representation."""
        log = AuditLog.objects.create(method="POST", path="/api/start/", status_code=200)
        self.assertIn("POST", str(log))
        self.assertIn("/api/start/", str(log))
        self.assertIn("200", str(log))


class AuditLogMiddlewareTestCase(TestCase):
    """Test cases for the AuditLogMiddleware."""

    def setUp(self):
        self.factory = RequestFactory()

    def _get_middleware(self, response=None):
        """Create middleware with a dummy get_response."""
        if response is None:
            response = HttpResponse("OK", status=200)

        def get_response(request):
            return response

        return AuditLogMiddleware(get_response)

    @patch("bot_control.permissions.get_user_groups_from_mediawiki", return_value=[])
    def test_middleware_logs_request(self, mock_groups):
        """Test that middleware creates an audit log entry."""
        middleware = self._get_middleware()
        request = self.factory.get("/bot-control/api/status/")
        request.session = {}
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        middleware(request)

        self.assertEqual(AuditLog.objects.count(), 1)
        log = AuditLog.objects.first()
        self.assertEqual(log.method, "GET")
        self.assertEqual(log.path, "/bot-control/api/status/")
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.ip_address, "192.168.1.1")

    @patch("bot_control.permissions.get_user_groups_from_mediawiki", return_value=[])
    def test_middleware_skips_static_files(self, mock_groups):
        """Test that middleware skips static file requests."""
        middleware = self._get_middleware()
        request = self.factory.get("/static/reviews/app.js")
        request.session = {}

        middleware(request)

        self.assertEqual(AuditLog.objects.count(), 0)

    @patch("bot_control.permissions.get_user_groups_from_mediawiki", return_value=["reviewer"])
    def test_middleware_captures_session_username(self, mock_groups):
        """Test that middleware reads username from session."""
        middleware = self._get_middleware()
        request = self.factory.get("/bot-control/")
        request.session = {"wiki_username": "Harshita", "wiki_code": "fi"}

        middleware(request)

        log = AuditLog.objects.first()
        self.assertEqual(log.username, "Harshita")
        self.assertEqual(log.role, "reviewer")

    @patch("bot_control.permissions.get_user_groups_from_mediawiki", return_value=[])
    def test_middleware_handles_x_forwarded_for(self, mock_groups):
        """Test that middleware extracts IP from X-Forwarded-For header."""
        middleware = self._get_middleware()
        request = self.factory.get("/bot-control/", HTTP_X_FORWARDED_FOR="10.0.0.1, 10.0.0.2")
        request.session = {}

        middleware(request)

        log = AuditLog.objects.first()
        self.assertEqual(log.ip_address, "10.0.0.1")

    @patch("bot_control.permissions.get_user_groups_from_mediawiki", return_value=[])
    def test_middleware_records_response_time(self, mock_groups):
        """Test that middleware records response time."""
        middleware = self._get_middleware()
        request = self.factory.get("/bot-control/")
        request.session = {}

        middleware(request)

        log = AuditLog.objects.first()
        self.assertIsNotNone(log.response_time_ms)
        self.assertGreaterEqual(log.response_time_ms, 0)


class AuditLogAPITestCase(TestCase):
    """Test cases for the audit log API endpoint."""

    def setUp(self):
        """Create sample audit log entries."""
        AuditLog.objects.create(
            method="GET", path="/bot-control/", status_code=200, username="admin1", role="admin"
        )
        AuditLog.objects.create(
            method="POST",
            path="/bot-control/api/start/",
            status_code=200,
            username="admin1",
            role="admin",
        )
        AuditLog.objects.create(
            method="GET",
            path="/bot-control/api/status/",
            status_code=200,
            username="anonymous",
            role="public",
        )
        AuditLog.objects.create(
            method="GET", path="/statistics/", status_code=404, username="anonymous", role="public"
        )
        AuditLog.objects.create(
            method="GET",
            path="/bot-control/api/status/",
            status_code=500,
            username="anonymous",
            role="public",
        )
        self.initial_count = 5

    def _get_api_count(self, params=""):
        """Helper: get total from audit log API, accounting for middleware-added logs."""
        response = self.client.get(f"/bot-control/api/audit-logs/?{params}")
        return response.json()

    def test_get_audit_logs_returns_all(self):
        """Test fetching all audit logs."""
        response = self.client.get("/bot-control/api/audit-logs/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # At least our 5 seed entries (middleware may add more)
        self.assertGreaterEqual(data["pagination"]["total"], self.initial_count)

    def test_filter_by_method(self):
        """Test filtering by HTTP method."""
        response = self.client.get("/bot-control/api/audit-logs/?method=POST")
        data = response.json()
        for log in data["logs"]:
            self.assertEqual(log["method"], "POST")
        # At least our one seeded POST
        self.assertGreaterEqual(data["pagination"]["total"], 1)

    def test_filter_by_status_range(self):
        """Test filtering by status code range."""
        response = self.client.get("/bot-control/api/audit-logs/?status=4xx")
        data = response.json()
        self.assertGreaterEqual(data["pagination"]["total"], 1)
        for log in data["logs"]:
            self.assertGreaterEqual(log["status_code"], 400)
            self.assertLess(log["status_code"], 500)

    def test_filter_by_user(self):
        """Test filtering by username."""
        response = self.client.get("/bot-control/api/audit-logs/?user=admin1")
        data = response.json()
        self.assertGreaterEqual(data["pagination"]["total"], 2)
        for log in data["logs"]:
            self.assertIn("admin1", log["username"])

    def test_search_by_path(self):
        """Test searching by path substring."""
        response = self.client.get("/bot-control/api/audit-logs/?q=/api/status/")
        data = response.json()
        self.assertGreaterEqual(data["pagination"]["total"], 2)
        for log in data["logs"]:
            self.assertIn("/api/status/", log["path"])

    def test_pagination_structure(self):
        """Test pagination response structure."""
        response = self.client.get("/bot-control/api/audit-logs/?per_page=2&page=1")
        data = response.json()
        self.assertEqual(len(data["logs"]), 2)
        self.assertIn("pagination", data)
        self.assertEqual(data["pagination"]["page"], 1)
        self.assertEqual(data["pagination"]["per_page"], 2)
        self.assertGreaterEqual(data["pagination"]["total"], self.initial_count)
        self.assertGreaterEqual(data["pagination"]["total_pages"], 3)

    def test_audit_logs_page_renders(self):
        """Test that the audit logs page template renders."""
        response = self.client.get("/bot-control/audit-logs/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audit Logs")
