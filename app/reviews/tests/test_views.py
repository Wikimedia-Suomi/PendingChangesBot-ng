from __future__ import annotations

import json
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


class ViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki, redirect_aliases=["#REDIRECT"])

    def test_index_creates_default_wiki_if_missing(self):
        Wiki.objects.all().delete()
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending Changes Review")
        codes = list(Wiki.objects.values_list("code", flat=True))
        # All Wikipedias with FlaggedRevisions enabled
        expected_codes = [
            "als",
            "ar",
            "be",
            "bn",
            "bs",
            "ce",
            "ckb",
            "de",
            "en",
            "eo",
            "fa",
            "fi",
            "hi",
            "hu",
            "ia",
            "id",
            "ka",
            "pl",
            "pt",
            "ru",
            "sq",
            "tr",
            "uk",
            "vec",
        ]
        self.assertCountEqual(codes, expected_codes)

    @mock.patch("reviews.views.logger")
    @mock.patch("reviews.views.WikiClient")
    def test_api_refresh_returns_error_on_failure(self, mock_client, mock_logger):
        mock_client.return_value.refresh.side_effect = RuntimeError("failure")
        response = self.client.post(reverse("api_refresh", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())

    @mock.patch("reviews.views.WikiClient")
    def test_api_refresh_success(self, mock_client):
        mock_client.return_value.refresh.return_value = []
        response = self.client.post(reverse("api_refresh", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("pages", response.json())

    def test_api_pending_returns_cached_revisions(self):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1,
            title="Page",
            stable_revid=1,
            categories=["Cat"],
        )
        PendingRevision.objects.create(
            page=page,
            revid=1,
            parentid=None,
            user_name="Stabilizer",
            user_id=9,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=3),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=3),
            sha1="stable",
            comment="Stable revision",
            change_tags=[],
            wikitext="",
            categories=[],
        )
        revision = PendingRevision.objects.create(
            page=page,
            revid=2,
            parentid=1,
            user_name="User",
            user_id=10,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="hash",
            comment="Comment",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={
                "user_groups": ["user", "autopatrolled"],
                "change_tags": ["tag"],
                "page_categories": ["Cat"],
                "rc_bot": False,
            },
        )
        response = self.client.get(reverse("api_pending", args=[self.wiki.pk]))
        payload = response.json()
        self.assertEqual(len(payload["pages"]), 1)
        revisions = payload["pages"][0]["revisions"]
        self.assertEqual(len(revisions), 1)
        rev_payload = revisions[0]
        self.assertEqual(rev_payload["revid"], revision.revid)
        self.assertTrue(rev_payload["editor_profile"]["is_autopatrolled"])
        self.assertEqual(rev_payload["change_tags"], ["tag"])
        self.assertEqual(rev_payload["categories"], ["Cat"])

    def test_api_page_revisions_returns_revision_payload(self):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=42,
            title="Example",
            stable_revid=1,
            categories=["Bar"],
        )
        PendingRevision.objects.create(
            page=page,
            revid=1,
            parentid=None,
            user_name="Stabilizer",
            user_id=9,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=6),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=6),
            sha1="stable",
            comment="Stable revision",
            change_tags=[],
            wikitext="",
            categories=[],
        )
        revision = PendingRevision.objects.create(
            page=page,
            revid=5,
            parentid=3,
            user_name="Another",
            user_id=20,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(minutes=30),
            sha1="sha",
            comment="More",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={
                "user_groups": ["editor", "autoreviewer", "editor", "reviewer", "sysop", "bot"],
                "change_tags": ["foo"],
                "page_categories": ["Bar"],
                "rc_bot": False,
            },
        )

        url = reverse("api_page_revisions", args=[self.wiki.pk, page.pageid])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pageid"], page.pageid)
        self.assertEqual(len(data["revisions"]), 1)
        payload = data["revisions"][0]
        self.assertEqual(payload["revid"], revision.revid)
        self.assertTrue(payload["editor_profile"]["is_autoreviewed"])
        self.assertEqual(payload["change_tags"], ["foo"])
        self.assertEqual(payload["categories"], ["Bar"])

    def test_api_clear_cache_deletes_records(self):
        PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1,
            title="Page",
            stable_revid=1,
        )
        response = self.client.post(reverse("api_clear_cache", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PendingPage.objects.count(), 0)

    def test_api_configuration_updates_settings(self):
        url = reverse("api_configuration", args=[self.wiki.pk])
        payload = {
            "blocking_categories": ["Foo"],
            "auto_approved_groups": ["sysop"],
        }
        response = self.client.put(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        config = self.wiki.configuration
        config.refresh_from_db()
        self.assertEqual(config.blocking_categories, ["Foo"])
        self.assertEqual(config.auto_approved_groups, ["sysop"])

    @mock.patch("reviews.services.pywikibot.Site")
    def test_api_autoreview_marks_bot_revision_auto_approvable(self, mock_site):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=100,
            title="Bot Page",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=200,
            parentid=150,
            user_name="HelpfulBot",
            user_id=999,
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=1),
            sha1="hash",
            comment="Automated edit",
            change_tags=[],
            wikitext="Some plain text",
            categories=[],
            superset_data={"user_groups": ["bot"], "rc_bot": True},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "dry-run")
        self.assertEqual(len(data["results"]), 1)
        result = data["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")
        self.assertEqual(len(result["tests"]), 2)
        self.assertEqual(result["tests"][0]["status"], "ok")
        self.assertEqual(result["tests"][0]["id"], "manual-unapproval")
        self.assertEqual(result["tests"][1]["status"], "ok")
        self.assertEqual(result["tests"][1]["id"], "bot-user")

    @mock.patch("reviews.services.pywikibot.Site")
    def test_api_autoreview_allows_configured_user_groups(self, mock_site):
        config = self.wiki.configuration
        config.auto_approved_groups = ["sysop"]
        config.save(update_fields=["auto_approved_groups"])

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=101,
            title="Group Page",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=201,
            parentid=150,
            user_name="AdminUser",
            user_id=1000,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=5),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=5),
            sha1="hash2",
            comment="Admin edit",
            change_tags=[],
            wikitext="Some plain text",
            categories=[],
            superset_data={"user_groups": ["Sysop"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")
        self.assertEqual(len(result["tests"]), 4)
        self.assertEqual(result["tests"][0]["status"], "ok")
        self.assertEqual(result["tests"][0]["id"], "manual-unapproval")
        self.assertEqual(result["tests"][3]["status"], "ok")
        self.assertEqual(result["tests"][3]["id"], "auto-approved-group")

    @mock.patch("reviews.services.pywikibot.Site")
    def test_api_autoreview_defaults_to_profile_rights(self, mock_site):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=105,
            title="Default Rights",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=401,
            parentid=300,
            user_name="AutoUser",
            user_id=3001,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=4),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=4),
            sha1="hash5",
            comment="Edit",
            change_tags=[],
            wikitext="Some plain text",
            categories=[],
            superset_data={"user_groups": ["autopatrolled"]},
        )
        EditorProfile.objects.create(
            wiki=self.wiki,
            username="AutoUser",
            usergroups=["autopatrolled"],
            is_autopatrolled=True,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")
        self.assertEqual(len(result["tests"]), 5)

    @mock.patch("reviews.models.pywikibot.Site")
    def test_api_autoreview_blocks_on_blocking_categories(self, mock_site):
        config = self.wiki.configuration
        config.blocking_categories = ["Secret"]
        config.save(update_fields=["blocking_categories"])

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=102,
            title="Blocked Page",
            stable_revid=1,
        )
        revision = PendingRevision.objects.create(
            page=page,
            revid=202,
            parentid=160,
            user_name="RegularUser",
            user_id=1001,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=3),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=3),
            sha1="hash3",
            comment="Edit",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={},
        )

        wikitext_response = {
            "query": {
                "pages": [
                    {
                        "revisions": [
                            {
                                "slots": {
                                    "main": {
                                        "content": "Hidden [[Category:Secret]]",
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def __init__(self):
                self.requests: list[dict] = []

            def logevents(self, **kwargs):
                """Mock logevents for block checking."""
                return []  # No block events

            def simple_request(self, **kwargs):
                self.requests.append(kwargs)

                # Check if this is a request for review log (manual un-approval check)
                if kwargs.get("list") == "logevents" and kwargs.get("letype") == "review":
                    return FakeRequest(
                        {
                            "query": {
                                "logevents": []  # No un-approvals
                            }
                        }
                    )

                # Check if this is a request for magic words
                if kwargs.get("meta") == "siteinfo" and kwargs.get("siprop") == "magicwords":
                    return FakeRequest(
                        {"query": {"magicwords": [{"name": "redirect", "aliases": ["#REDIRECT"]}]}}
                    )

                return FakeRequest(wikitext_response)

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "blocked")
        self.assertEqual(len(result["tests"]), 6)
        self.assertEqual(result["tests"][5]["status"], "fail")
        self.assertEqual(result["tests"][5]["id"], "blocking-categories")

        revision.refresh_from_db()
        self.assertEqual(revision.wikitext, "Hidden [[Category:Secret]]")
        self.assertEqual(revision.categories, ["Secret"])
        # 2 requests: 1 for redirect aliases, 1 for wikitext
        # (manual un-approval check uses reviews.services.pywikibot.Site which isn't mocked here)
        self.assertEqual(len(fake_site.requests), 2)

        second_response = self.client.post(url)
        self.assertEqual(second_response.status_code, 200)
        # redirect aliases are now cached, wikitext was already cached
        # But there's 1 more request (possibly from another check)
        self.assertEqual(len(fake_site.requests), 3)

    @mock.patch("reviews.models.pywikibot.Site")
    @mock.patch("reviews.services.pywikibot.Site")
    def test_api_autoreview_requires_manual_review_when_no_rules_apply(
        self, mock_service_site, mock_model_site
    ):
        mock_service_site.return_value.simple_request.return_value.submit.return_value = {
            "parse": {"text": "<p>No errors</p>"}
        }
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=103,
            title="Manual Page",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=203,
            parentid=170,
            user_name="Editor",
            user_id=1002,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="hash4",
            comment="Edit",
            change_tags=[],
            wikitext="Content [[Category:General]]",
            categories=[],
            superset_data={"user_groups": ["user"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "manual")
        self.assertEqual(len(result["tests"]), 8)
        self.assertEqual(result["tests"][-1]["status"], "ok")

    @mock.patch("reviews.services.pywikibot.Site")
    def test_api_autoreview_orders_revisions_from_oldest_to_newest(self, mock_site):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=104,
            title="Multiple Revisions",
            stable_revid=1,
        )
        older_timestamp = datetime.now(timezone.utc) - timedelta(days=2)
        newer_timestamp = datetime.now(timezone.utc) - timedelta(days=1)
        PendingRevision.objects.create(
            page=page,
            revid=301,
            parentid=200,
            user_name="Editor1",
            user_id=2001,
            timestamp=older_timestamp,
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=2),
            sha1="sha-old",
            comment="Old",
            change_tags=[],
            wikitext="Older revision text",
            categories=[],
            superset_data={"user_groups": ["user"]},
        )
        PendingRevision.objects.create(
            page=page,
            revid=302,
            parentid=301,
            user_name="Editor2",
            user_id=2002,
            timestamp=newer_timestamp,
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=1),
            sha1="sha-new",
            comment="New",
            change_tags=[],
            wikitext="Newer revision text",
            categories=[],
            superset_data={"user_groups": ["user"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual([result["revid"] for result in results], [301, 302])

    @mock.patch("requests.get")
    def test_fetch_diff_success(self, mock_get):
        """
        Tests that the API successfully fetches content and returns correct HTML and content type.
        """
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = '<html><div class="diff-content">Mock data for testing</div></html>'

        external_wiki_url = "https://fi.wikipedia.org/w/index.php?diff=12345"

        response = self.client.get(reverse("fetch_diff"), {"url": external_wiki_url})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html")
        self.assertIn(b"Mock data for testing", response.content)

    def test_fetch_diff_missing_url(self):
        """
        Tests the API returns 400 Bad Request when 'url' parameter is not passed.
        """
        response = self.client.get(reverse("fetch_diff"))

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Missing 'url' parameter", response.content)
