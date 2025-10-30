"""
Integration tests for approval utility function with views.
This module tests the integration of the approval utility function with the API endpoints.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class ApprovalIntegrationTests(TestCase):
    """Integration tests for approval utility function."""

    def setUp(self):
        """Set up test data."""
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        self.config = WikiConfiguration.objects.create(wiki=self.wiki)

        self.page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=12345,
            title="Test Page",
            stable_revid=100,
        )

        # Create some test revisions
        now = datetime.now()
        self.revision1 = PendingRevision.objects.create(
            page=self.page,
            revid=200,
            parentid=150,
            user_name="TestUser1",
            user_id=1000,
            timestamp=now - timedelta(hours=2),
            age_at_fetch=timedelta(hours=2),
            sha1="abc123",
            comment="Test comment 1",
        )

        self.revision2 = PendingRevision.objects.create(
            page=self.page,
            revid=201,
            parentid=200,
            user_name="TestUser2",
            user_id=1001,
            timestamp=now - timedelta(hours=1),
            age_at_fetch=timedelta(hours=1),
            sha1="def456",
            comment="Test comment 2",
        )

        self.client = Client()

    @patch("reviews.views.run_autoreview_for_page")
    def test_api_autoreview_with_approval_summary(self, mock_autoreview):
        """Test that the autoreview API includes approval summary."""
        # Mock the autoreview results
        mock_autoreview.return_value = [
            {
                "revid": 200,
                "tests": [],
                "decision": {
                    "status": "approve",
                    "label": "Would be auto-approved",
                    "reason": "user was bot",
                },
            },
            {
                "revid": 201,
                "tests": [],
                "decision": {
                    "status": "approve",
                    "label": "Would be auto-approved",
                    "reason": "user was autoreviewed",
                },
            },
        ]

        # Make API request
        url = reverse("api_autoreview", kwargs={"pk": self.wiki.id, "pageid": self.page.pageid})
        response = self.client.post(url)

        # Check response
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that approval summary is included
        self.assertIn("approval_summary", data)
        approval_summary = data["approval_summary"]

        # Check that the highest approvable revision ID is correct
        self.assertEqual(approval_summary["max_approvable_revid"], 201)

        # Check that the approval comment includes both reasons
        comment = approval_summary["approval_comment"]
        self.assertIn("rev_id 200 approved because user was bot", comment)
        self.assertIn("rev_id 201 approved because user was autoreviewed", comment)

    @patch("reviews.views.run_autoreview_for_page")
    def test_api_autoreview_no_approvable_revisions(self, mock_autoreview):
        """Test API response when no revisions can be approved."""
        # Mock the autoreview results with no approvable revisions
        mock_autoreview.return_value = [
            {
                "revid": 200,
                "tests": [],
                "decision": {
                    "status": "blocked",
                    "label": "Cannot be auto-approved",
                    "reason": "user was blocked",
                },
            },
            {
                "revid": 201,
                "tests": [],
                "decision": {
                    "status": "manual",
                    "label": "Requires human review",
                    "reason": "requires human review",
                },
            },
        ]

        # Make API request
        url = reverse("api_autoreview", kwargs={"pk": self.wiki.id, "pageid": self.page.pageid})
        response = self.client.post(url)

        # Check response
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that approval summary indicates no approvable revisions
        approval_summary = data["approval_summary"]
        self.assertIsNone(approval_summary["max_approvable_revid"])
        self.assertEqual(approval_summary["approval_comment"], "No revisions can be approved")

    @patch("reviews.views.run_autoreview_for_page")
    def test_api_autoreview_mixed_results(self, mock_autoreview):
        """Test API response with mixed approvable and non-approvable revisions."""
        # Mock the autoreview results with mixed results
        mock_autoreview.return_value = [
            {
                "revid": 200,
                "tests": [],
                "decision": {
                    "status": "approve",
                    "label": "Would be auto-approved",
                    "reason": "user was bot",
                },
            },
            {
                "revid": 201,
                "tests": [],
                "decision": {
                    "status": "blocked",
                    "label": "Cannot be auto-approved",
                    "reason": "user was blocked",
                },
            },
            {
                "revid": 202,
                "tests": [],
                "decision": {
                    "status": "approve",
                    "label": "Would be auto-approved",
                    "reason": "user was autoreviewed",
                },
            },
        ]

        # Make API request
        url = reverse("api_autoreview", kwargs={"pk": self.wiki.id, "pageid": self.page.pageid})
        response = self.client.post(url)

        # Check response
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that approval summary includes only approvable revisions
        approval_summary = data["approval_summary"]
        self.assertEqual(
            approval_summary["max_approvable_revid"], 202
        )  # Highest approvable revision

        comment = approval_summary["approval_comment"]
        self.assertIn("rev_id 200 approved because user was bot", comment)
        self.assertIn("rev_id 202 approved because user was autoreviewed", comment)
        self.assertNotIn("user was blocked", comment)  # Should not include blocked revisions
