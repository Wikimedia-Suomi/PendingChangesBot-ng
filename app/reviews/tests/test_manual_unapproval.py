from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from reviews.models import (
    EditorProfile,
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)


class ManualUnapprovalTests(TestCase):
    """Tests for manual un-approval check in autoreview functionality."""

    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        self.config = WikiConfiguration.objects.create(wiki=self.wiki)

    @mock.patch.object(PendingRevision, "get_rendered_html", return_value="<p>Clean HTML</p>")
    @mock.patch("reviews.services.WikiClient.has_manual_unapproval")
    def test_manually_unapproved_revision_should_be_blocked(self, mock_has_unapproval, mock_html):
        """Bot should not auto-approve revisions that have been manually un-approved."""
        mock_has_unapproval.return_value = True

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=12345,
            title="Test Page",
            stable_revid=100,
        )

        EditorProfile.objects.create(
            wiki=self.wiki,
            username="TestBot",
            usergroups=["bot"],
            is_bot=True,
            is_autopatrolled=True,
            is_autoreviewed=True,
        )

        PendingRevision.objects.create(
            page=page,
            revid=101,
            parentid=100,
            user_name="TestBot",
            user_id=999,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="abc123",
            comment="Bot edit",
            change_tags=[],
            wikitext="Test content",
            categories=[],
            superset_data={"rc_bot": True},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        self.assertEqual(
            result["decision"]["status"],
            "blocked",
            "Manually un-approved revisions should be blocked from auto-approval",
        )
        self.assertIn("manually un-approved", result["decision"]["reason"].lower())

        manual_unapproval_test = next(
            (test for test in result["tests"] if test["id"] == "manual-unapproval"), None
        )
        self.assertIsNotNone(manual_unapproval_test)
        assert manual_unapproval_test is not None  # for mypy
        self.assertEqual(manual_unapproval_test["status"], "fail")

    @mock.patch.object(PendingRevision, "get_rendered_html", return_value="<p>Clean HTML</p>")
    @mock.patch("reviews.services.WikiClient.has_manual_unapproval")
    def test_not_manually_unapproved_revision_passes_check(self, mock_has_unapproval, mock_html):
        """Revisions without manual un-approval should pass the check."""
        mock_has_unapproval.return_value = False

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=54321,
            title="Another Test Page",
            stable_revid=200,
        )

        EditorProfile.objects.create(
            wiki=self.wiki,
            username="AnotherBot",
            usergroups=["bot"],
            is_bot=True,
        )

        PendingRevision.objects.create(
            page=page,
            revid=201,
            parentid=200,
            user_name="AnotherBot",
            user_id=888,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="def456",
            comment="Bot edit",
            change_tags=[],
            wikitext="Test content",
            categories=[],
            superset_data={"rc_bot": True},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        manual_unapproval_test = next(
            (test for test in result["tests"] if test["id"] == "manual-unapproval"), None
        )
        self.assertIsNotNone(manual_unapproval_test)
        assert manual_unapproval_test is not None  # for mypy
        self.assertEqual(manual_unapproval_test["status"], "ok")

        self.assertEqual(result["decision"]["status"], "approve")

    @mock.patch.object(PendingRevision, "get_rendered_html", return_value="<p>Clean HTML</p>")
    @mock.patch("reviews.services.WikiClient.has_manual_unapproval")
    def test_manual_unapproval_overrides_autoreview_rights(self, mock_has_unapproval, mock_html):
        """Manual un-approval should block even users with autoreview rights."""
        mock_has_unapproval.return_value = True

        self.config.auto_approved_groups = ["autoreviewer"]
        self.config.save(update_fields=["auto_approved_groups"])

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=99999,
            title="Autoreview Test Page",
            stable_revid=300,
        )

        EditorProfile.objects.create(
            wiki=self.wiki,
            username="TrustedEditor",
            usergroups=["user", "autoreviewer"],
            is_autoreviewed=True,
        )

        PendingRevision.objects.create(
            page=page,
            revid=301,
            parentid=300,
            user_name="TrustedEditor",
            user_id=777,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="ghi789",
            comment="Important edit",
            change_tags=[],
            wikitext="Updated content",
            categories=[],
            superset_data={"user_groups": ["user", "autoreviewer"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        self.assertEqual(
            result["decision"]["status"],
            "blocked",
            "Manual un-approval should override autoreview rights",
        )

    @mock.patch("reviews.models.pending_revision.pywikibot.Site")
    def test_has_manual_unapproval_detects_unapproval(self, mock_site):
        """Test WikiClient.has_manual_unapproval correctly detects un-approvals."""
        from reviews.services import WikiClient

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def logevents(self, **kwargs):
                """Mock logevents for block checking."""
                return []

            def simple_request(self, **kwargs):
                return FakeRequest(
                    {
                        "query": {
                            "logevents": [
                                {
                                    "logid": 12345,
                                    "action": "unapprove",
                                    "timestamp": "2025-10-11T10:00:00Z",
                                    "params": {"0": 101},
                                },
                                {
                                    "logid": 12344,
                                    "action": "approve",
                                    "timestamp": "2025-10-11T09:00:00Z",
                                    "params": {"0": 101},
                                },
                            ]
                        }
                    }
                )

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        client = WikiClient(self.wiki)
        result = client.has_manual_unapproval("Test Page", 101)

        self.assertTrue(result, "Should detect manual un-approval")

    @mock.patch("reviews.models.pending_revision.pywikibot.Site")
    def test_has_manual_unapproval_returns_false_when_no_unapproval(self, mock_site):
        """Test WikiClient.has_manual_unapproval returns False when no un-approval exists."""
        from reviews.services import WikiClient

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def logevents(self, **kwargs):
                """Mock logevents for block checking."""
                return []

            def simple_request(self, **kwargs):
                return FakeRequest(
                    {
                        "query": {
                            "logevents": [
                                {
                                    "logid": 12346,
                                    "action": "approve",
                                    "timestamp": "2025-10-11T11:00:00Z",
                                    "params": {"0": 102},
                                },
                                {
                                    "logid": 12345,
                                    "action": "approve",
                                    "timestamp": "2025-10-11T10:00:00Z",
                                    "params": {"0": 101},
                                },
                            ]
                        }
                    }
                )

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        client = WikiClient(self.wiki)
        result = client.has_manual_unapproval("Test Page", 101)

        self.assertFalse(result, "Should return False when no un-approval exists")

    @mock.patch("reviews.models.pending_revision.pywikibot.Site")
    def test_has_manual_unapproval_checks_correct_revision(self, mock_site):
        """Test that has_manual_unapproval only returns True for the specific revision."""
        from reviews.services import WikiClient

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def logevents(self, **kwargs):
                """Mock logevents for block checking."""
                return []

            def simple_request(self, **kwargs):
                return FakeRequest(
                    {
                        "query": {
                            "logevents": [
                                {
                                    "logid": 12347,
                                    "action": "unapprove",
                                    "timestamp": "2025-10-11T12:00:00Z",
                                    "params": {"0": 999},
                                }
                            ]
                        }
                    }
                )

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        client = WikiClient(self.wiki)
        result = client.has_manual_unapproval("Test Page", 101)

        self.assertFalse(result, "Should return False when un-approval is for a different revision")

    @mock.patch("reviews.models.pending_revision.pywikibot.Site")
    def test_later_approval_overrides_earlier_unapproval(self, mock_site):
        """If revision was un-approved then re-approved, should return False."""
        from reviews.services import WikiClient

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def logevents(self, **kwargs):
                """Mock logevents for block checking."""
                return []

            def simple_request(self, **kwargs):
                return FakeRequest(
                    {
                        "query": {
                            "logevents": [
                                {
                                    "logid": 12350,
                                    "action": "approve",
                                    "timestamp": "2025-10-12T10:00:00Z",
                                    "params": {"0": 101},
                                },
                                {
                                    "logid": 12349,
                                    "action": "unapprove",
                                    "timestamp": "2025-10-11T10:00:00Z",
                                    "params": {"0": 101},
                                },
                                {
                                    "logid": 12348,
                                    "action": "approve",
                                    "timestamp": "2025-10-10T10:00:00Z",
                                    "params": {"0": 101},
                                },
                            ]
                        }
                    }
                )

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        client = WikiClient(self.wiki)
        result = client.has_manual_unapproval("Test Page", 101)

        self.assertFalse(
            result, "Should return False when most recent action is approval (not unapproval)"
        )

    @mock.patch("reviews.models.pending_revision.pywikibot.Site")
    def test_detects_quality_unapproval(self, mock_site):
        """Test that unapprove2 (quality un-approval) is also detected."""
        from reviews.services import WikiClient

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def logevents(self, **kwargs):
                """Mock logevents for block checking."""
                return []

            def simple_request(self, **kwargs):
                return FakeRequest(
                    {
                        "query": {
                            "logevents": [
                                {
                                    "logid": 12351,
                                    "action": "unapprove2",
                                    "timestamp": "2025-10-13T10:00:00Z",
                                    "params": {"0": 102},
                                }
                            ]
                        }
                    }
                )

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        client = WikiClient(self.wiki)
        result = client.has_manual_unapproval("Test Page", 102)

        self.assertTrue(result, "Should detect unapprove2 (quality/higher-level un-approval)")
