from __future__ import annotations

from unittest import mock

from django.test import TestCase

from reviews.models import EditorProfile, PendingPage, PendingRevision, Wiki
from reviews.services import WikiClient, parse_categories


class FakeRequest:
    def __init__(self, data):
        self._data = data

    def submit(self):
        return self._data


class FakeSite:
    def __init__(self):
        self.response: dict[str, dict] = {"query": {"pages": []}}
        self.users_data: dict[str, dict] = {}
        self.requests: list[dict] = []

    def logevents(self, **kwargs):
        """Mock logevents for block checking."""
        return []

    def simple_request(self, **kwargs):
        self.requests.append(kwargs)
        return FakeRequest(self.response)

    def users(self, users):
        for username in users:
            data = self.users_data.get(username)
            if data is not None:
                yield data
            else:
                yield {
                    "name": username,
                    "groups": [],
                }


class WikiClientTests(TestCase):
    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            api_endpoint="https://test.example/api.php",
        )
        self.fake_site = FakeSite()
        self.site_patcher = mock.patch(
            "reviews.services.wiki_client.pywikibot.Site",
            return_value=self.fake_site,
        )
        self.site_patcher.start()
        self.addCleanup(self.site_patcher.stop)
        self.replica_patcher = mock.patch("reviews.services.wiki_client.WikiReplicaConnection")
        self.mock_replica_cls = self.replica_patcher.start()
        self.addCleanup(self.replica_patcher.stop)
        self.mock_replica = self.mock_replica_cls.return_value
        self.mock_replica.execute_query.return_value = []

    def test_parse_categories_extracts_unique_names(self):
        wikitext = (
            "Some text [[Category:Example]] and [[category:Second|label]] and [[Category:Example]]"
        )
        categories = parse_categories(wikitext)
        self.assertEqual(categories, ["Example", "Second"])

    def test_fetch_pending_pages_caches_pages(self):
        self.mock_replica.execute_query.return_value = [
            {
                "fp_page_id": 123,
                "page_title": "Example",
                "fp_stable": 10,
                "fp_pending_since": "2024-01-01T00:00:00Z",
                "rev_id": 11,
                "rev_timestamp": "2024-01-02 03:04:05",
                "rev_parent_id": 9,
                "comment_text": "Superset edit",
                "rev_sha1": "abc123",
                "change_tags": "mobile,pc",
                "user_groups": "autopatrolled,bot",
                "user_former_groups": "sysop",
                "actor_name": "SupersetUser",
                "actor_user": 321,
                "page_categories": "Foo,Bar",
                "rc_bot": 1,
                "rc_patrolled": 0,
            }
        ]
        client = WikiClient(self.wiki)
        pages = client.fetch_pending_pages(limit=10)
        self.assertEqual(len(pages), 1)
        page = PendingPage.objects.get()
        self.assertEqual(page.pageid, 123)
        self.assertEqual(page.stable_revid, 10)
        self.assertIsNotNone(page.pending_since)
        sql_argument = self.mock_replica.execute_query.call_args[0][0]
        self.assertIn("LIMIT 10) AS fp", sql_argument)
        self.assertIn("r.rev_id>=fp_stable", sql_argument)
        revision = PendingRevision.objects.get()
        self.assertEqual(revision.revid, 11)
        self.assertEqual(revision.comment, "Superset edit")
        self.assertEqual(revision.change_tags, ["mobile", "pc"])
        self.assertCountEqual(page.categories, ["Foo", "Bar"])
        self.assertEqual(revision.categories, [])
        self.assertEqual(revision.user_id, 321)
        self.assertTrue(revision.superset_data["rc_bot"])
        self.assertEqual(revision.superset_data["page_categories"], ["Foo", "Bar"])

    def test_fetch_pending_pages_includes_stable_revision_record(self):
        self.mock_replica.execute_query.return_value = [
            {
                "fp_page_id": 555,
                "page_title": "WithStable",
                "fp_stable": 30,
                "fp_pending_since": "2024-01-01T00:00:00Z",
                "rev_id": 30,
                "rev_timestamp": "2024-01-01 00:00:00",
                "rev_parent_id": 29,
                "comment_text": "Stable",
                "rev_sha1": "stable",
                "actor_name": "StableUser",
                "actor_user": 100,
            },
            {
                "fp_page_id": 555,
                "page_title": "WithStable",
                "fp_stable": 30,
                "fp_pending_since": "2024-01-01T00:00:00Z",
                "rev_id": 31,
                "rev_timestamp": "2024-01-02 00:00:00",
                "rev_parent_id": 30,
                "comment_text": "Pending",
                "rev_sha1": "pending",
                "actor_name": "PendingUser",
                "actor_user": 101,
            },
        ]

        client = WikiClient(self.wiki)
        client.fetch_pending_pages(limit=2)

        page = PendingPage.objects.get(pageid=555)
        revisions = list(PendingRevision.objects.filter(page=page).order_by("revid"))
        self.assertEqual([30, 31], [revision.revid for revision in revisions])
        self.assertEqual(page.stable_revid, 30)

    def test_fetch_pending_pages_hydrates_editor_profile(self):
        self.mock_replica.execute_query.return_value = [
            {
                "fp_page_id": 222,
                "page_title": "Profile",
                "fp_stable": 20,
                "fp_pending_since": "2024-01-01T00:00:00Z",
                "rev_id": 25,
                "rev_timestamp": "2024-01-02 03:04:05",
                "rev_parent_id": 19,
                "comment_text": "Profile edit",
                "rev_sha1": "def456",
                "change_tags": "pc",
                "user_groups": "bot,autoreview",
                "actor_name": "ProfileUser",
                "actor_user": 77,
                "page_categories": None,
                "rc_bot": "1",
                "rc_patrolled": None,
            }
        ]
        client = WikiClient(self.wiki)
        client.fetch_pending_pages(limit=5)
        profile = EditorProfile.objects.get(username="ProfileUser")
        self.assertEqual(profile.usergroups, ["autoreview", "bot"])
        self.assertTrue(profile.is_bot)
        self.assertTrue(profile.is_autoreviewed)
        self.assertFalse(profile.is_autopatrolled)


class RefreshWorkflowTests(TestCase):
    @mock.patch("reviews.services.wiki_client.WikiReplicaConnection")
    @mock.patch("reviews.services.wiki_client.pywikibot.Site")
    def test_refresh_handles_errors(self, mock_site, mock_replica):
        wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            api_endpoint="https://test.example/api.php",
        )
        fake_site = FakeSite()
        fake_site.response = {"query": {"pages": []}}
        mock_site.return_value = fake_site
        mock_replica.return_value.execute_query.side_effect = RuntimeError("boom")
        client = WikiClient(wiki)
        with self.assertRaises(RuntimeError):
            client.refresh()

    @mock.patch("reviews.services.wiki_client.WikiReplicaConnection")
    @mock.patch("reviews.services.wiki_client.pywikibot.Site")
    def test_refresh_does_not_call_pywikibot_requests(self, mock_site, mock_replica):
        wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            api_endpoint="https://test.example/api.php",
        )
        fake_site = FakeSite()
        mock_site.return_value = fake_site
        mock_replica.return_value.execute_query.return_value = [
            {
                "fp_page_id": 1,
                "page_title": "Page",
                "fp_stable": 1,
                "fp_pending_since": "2024-01-01T00:00:00Z",
                "rev_id": 2,
                "rev_timestamp": "2024-01-01 01:00:00",
                "rev_parent_id": 1,
                "comment_text": "Edit",
                "rev_sha1": "hash",
                "change_tags": "tag",
                "user_groups": "user",
                "actor_name": "User",
                "actor_user": 5,
            }
        ]

        client = WikiClient(wiki)
        client.refresh()
        self.assertEqual(fake_site.requests, [])
        self.assertEqual(PendingRevision.objects.count(), 1)


class FormerBotTests(TestCase):
    """Test cases for former bot detection and handling."""

    def test_ensure_editor_profile_with_former_bot_group(self):
        """Test that former bot group is properly detected."""
        wiki = Wiki.objects.create(code="fi", family="wikipedia")
        client = WikiClient(wiki)

        superset_data = {
            "user_groups": ["autoconfirmed"],
            "user_former_groups": ["bot"],
            "rc_bot": False,
        }

        profile = client.ensure_editor_profile("FormerBotUser", superset_data)

        self.assertFalse(profile.is_bot)
        self.assertTrue(profile.is_former_bot)
        self.assertEqual(profile.username, "FormerBotUser")

    def test_ensure_editor_profile_with_current_and_former_bot(self):
        """Test user who is both current and former bot (edge case)."""
        wiki = Wiki.objects.create(code="fi", family="wikipedia")
        client = WikiClient(wiki)

        superset_data = {
            "user_groups": ["bot", "autoconfirmed"],
            "user_former_groups": ["bot"],  # Can happen if removed and re-added
            "rc_bot": True,
        }

        profile = client.ensure_editor_profile("ReinstatedBot", superset_data)

        self.assertTrue(profile.is_bot)
        self.assertTrue(profile.is_former_bot)

    def test_ensure_editor_profile_without_former_groups(self):
        """Test that missing former groups doesn't cause issues."""
        wiki = Wiki.objects.create(code="fi", family="wikipedia")
        client = WikiClient(wiki)

        superset_data = {
            "user_groups": ["autoconfirmed"],
            "user_former_groups": [],
            "rc_bot": False,
        }

        profile = client.ensure_editor_profile("RegularUser", superset_data)

        self.assertFalse(profile.is_bot)
        self.assertFalse(profile.is_former_bot)

    def test_ensure_editor_profile_former_bot_no_superset_data(self):
        """Test that profile defaults work when no superset data provided."""
        wiki = Wiki.objects.create(code="fi", family="wikipedia")
        client = WikiClient(wiki)

        profile = client.ensure_editor_profile("SomeUser", None)

        self.assertFalse(profile.is_bot)
        self.assertFalse(profile.is_former_bot)


class PendingChangesStatusTests(TestCase):
    """Tests for WikiClient.get_pending_changes_status()."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Finnish Wikipedia",
            code="fi",
            api_endpoint="https://fi.wikipedia.org/w/api.php",
        )
        self.fake_site = FakeSite()
        self.site_patcher = mock.patch(
            "reviews.services.wiki_client.pywikibot.Site",
            return_value=self.fake_site,
        )
        self.site_patcher.start()
        self.addCleanup(self.site_patcher.stop)

    def test_returns_empty_list_when_no_ids_or_titles(self):
        client = WikiClient(self.wiki)
        result = client.get_pending_changes_status()
        self.assertEqual(result, [])
        self.assertEqual(self.fake_site.requests, [])

    def test_queries_by_page_ids(self):
        self.fake_site.response = {
            "query": {
                "pages": [
                    {
                        "pageid": 123,
                        "title": "Helsinki",
                        "flagged": {
                            "stable_revid": 100,
                            "pending_since": "2026-01-15T10:00:00Z",
                            "level": "sighted",
                            "protection_level": "autoconfirmed",
                        },
                    }
                ]
            }
        }
        client = WikiClient(self.wiki)
        results = client.get_pending_changes_status(page_ids=[123])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pageid"], 123)
        self.assertEqual(results[0]["title"], "Helsinki")
        self.assertEqual(results[0]["stable_revid"], 100)
        self.assertEqual(results[0]["pending_since"], "2026-01-15T10:00:00Z")
        self.assertEqual(results[0]["level"], "sighted")

        req = self.fake_site.requests[0]
        self.assertEqual(req["action"], "query")
        self.assertEqual(req["prop"], "info|flagged")
        self.assertEqual(req["pageids"], "123")

    def test_queries_by_titles(self):
        self.fake_site.response = {
            "query": {
                "pages": [
                    {
                        "pageid": 456,
                        "title": "Tampere",
                        "flagged": {
                            "stable_revid": 200,
                        },
                    }
                ]
            }
        }
        client = WikiClient(self.wiki)
        results = client.get_pending_changes_status(titles=["Tampere"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Tampere")

        req = self.fake_site.requests[0]
        self.assertEqual(req["titles"], "Tampere")

    def test_page_ids_takes_precedence_over_titles(self):
        self.fake_site.response = {"query": {"pages": [{"pageid": 1, "title": "A", "flagged": {}}]}}
        client = WikiClient(self.wiki)
        client.get_pending_changes_status(page_ids=[1], titles=["B"])

        req = self.fake_site.requests[0]
        self.assertIn("pageids", req)
        self.assertNotIn("titles", req)

    def test_multiple_pages(self):
        self.fake_site.response = {
            "query": {
                "pages": [
                    {"pageid": 10, "title": "Page1", "flagged": {"stable_revid": 50}},
                    {"pageid": 20, "title": "Page2", "flagged": {"stable_revid": 60}},
                ]
            }
        }
        client = WikiClient(self.wiki)
        results = client.get_pending_changes_status(page_ids=[10, 20])

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["stable_revid"], 50)
        self.assertEqual(results[1]["stable_revid"], 60)

        req = self.fake_site.requests[0]
        self.assertEqual(req["pageids"], "10|20")

    def test_page_without_flagged_data(self):
        self.fake_site.response = {
            "query": {
                "pages": [
                    {"pageid": 999, "title": "Unflagged"},
                ]
            }
        }
        client = WikiClient(self.wiki)
        results = client.get_pending_changes_status(page_ids=[999])

        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0]["stable_revid"])
        self.assertIsNone(results[0]["pending_since"])
        self.assertEqual(results[0]["flagged"], {})

    def test_api_error_returns_empty_list(self):
        class ErrorRequest:
            def submit(self):
                raise RuntimeError("API unavailable")

        original = self.fake_site.simple_request

        def error_request(**kwargs):
            self.fake_site.requests.append(kwargs)
            return ErrorRequest()

        self.fake_site.simple_request = error_request

        client = WikiClient(self.wiki)
        results = client.get_pending_changes_status(page_ids=[123])

        self.assertEqual(results, [])
        self.fake_site.simple_request = original
