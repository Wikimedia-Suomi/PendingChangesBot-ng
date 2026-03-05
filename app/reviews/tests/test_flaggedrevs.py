from __future__ import annotations

from django.test import TestCase

from reviews.services.flaggedrevs import FlaggedRevsClient, FlaggedStatus, ReviewResult


class FakeRequest:
    def __init__(self, data):
        self._data = data

    def submit(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FakeSite:
    """Minimal mock that records requests and returns canned responses."""

    def __init__(self):
        self.responses: list[dict | Exception] = []
        self.requests: list[dict] = []
        self._call_idx = 0

    def set_response(self, response: dict | Exception):
        """Set a single response for all subsequent calls."""
        self.responses = [response]
        self._call_idx = 0

    def set_responses(self, responses: list[dict | Exception]):
        """Set multiple responses to be returned in order."""
        self.responses = responses
        self._call_idx = 0

    def simple_request(self, **kwargs):
        self.requests.append(kwargs)
        if self._call_idx < len(self.responses):
            resp = self.responses[self._call_idx]
            self._call_idx += 1
        elif self.responses:
            resp = self.responses[-1]
        else:
            resp = {}
        return FakeRequest(resp)


class FlaggedRevsClientGetStatusTests(TestCase):
    """Tests for FlaggedRevsClient.get_flagged_status()."""

    def setUp(self):
        self.site = FakeSite()
        self.client = FlaggedRevsClient(self.site)

    def test_empty_input_returns_empty(self):
        results = self.client.get_flagged_status()
        self.assertEqual(results, [])
        self.assertEqual(self.site.requests, [])

    def test_query_by_page_ids(self):
        self.site.set_response({
            "query": {
                "pages": [
                    {
                        "pageid": 42,
                        "title": "Helsinki",
                        "flagged": {
                            "stable_revid": 100,
                            "pending_since": "2026-01-10T08:00:00Z",
                            "level": "sighted",
                            "protection_level": "autoconfirmed",
                        },
                    }
                ]
            }
        })

        results = self.client.get_flagged_status(page_ids=[42])

        self.assertEqual(len(results), 1)
        status = results[0]
        self.assertIsInstance(status, FlaggedStatus)
        self.assertEqual(status.pageid, 42)
        self.assertEqual(status.title, "Helsinki")
        self.assertEqual(status.stable_revid, 100)
        self.assertTrue(status.has_pending_changes)
        self.assertEqual(status.level, "sighted")

    def test_query_by_titles(self):
        self.site.set_response({
            "query": {
                "pages": [
                    {"pageid": 7, "title": "Turku", "flagged": {"stable_revid": 50}},
                ]
            }
        })

        results = self.client.get_flagged_status(titles=["Turku"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Turku")
        req = self.site.requests[0]
        self.assertEqual(req["titles"], "Turku")

    def test_page_without_flagged_data(self):
        self.site.set_response({
            "query": {"pages": [{"pageid": 99, "title": "NoFlags"}]}
        })

        results = self.client.get_flagged_status(page_ids=[99])

        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].stable_revid)
        self.assertFalse(results[0].has_pending_changes)

    def test_api_error_returns_empty(self):
        self.site.set_response(RuntimeError("API down"))
        results = self.client.get_flagged_status(page_ids=[1])
        self.assertEqual(results, [])


class FlaggedRevsClientGetPendingPagesTests(TestCase):
    """Tests for FlaggedRevsClient.get_pending_pages()."""

    def setUp(self):
        self.site = FakeSite()
        self.client = FlaggedRevsClient(self.site)

    def test_returns_pending_pages(self):
        self.site.set_response({
            "query": {
                "oldreviewedpages": [
                    {
                        "pageid": 10,
                        "title": "Page_A",
                        "stable_revid": 100,
                        "pending_since": "2026-02-01T00:00:00Z",
                    },
                    {
                        "pageid": 20,
                        "title": "Page_B",
                        "stable_revid": 200,
                        "pending_since": "2026-02-02T00:00:00Z",
                    },
                ]
            }
        })

        results = self.client.get_pending_pages(limit=10)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.has_pending_changes for r in results))
        self.assertEqual(results[0].pageid, 10)
        self.assertEqual(results[1].pageid, 20)

    def test_respects_limit_cap(self):
        self.site.set_response({"query": {"oldreviewedpages": []}})
        self.client.get_pending_pages(limit=1000)

        req = self.site.requests[0]
        self.assertEqual(req["orlimit"], 500)

    def test_api_error_returns_empty(self):
        self.site.set_response(RuntimeError("timeout"))
        results = self.client.get_pending_pages()
        self.assertEqual(results, [])


class FlaggedRevsClientReviewTests(TestCase):
    """Tests for FlaggedRevsClient.review_revision()."""

    def setUp(self):
        self.site = FakeSite()
        self.client = FlaggedRevsClient(self.site)

    def test_successful_approval(self):
        self.site.set_responses([
            # First call: CSRF token
            {"query": {"tokens": {"csrftoken": "abc123+\\"}}},
            # Second call: review action
            {"review": {"revid": 500}},
        ])

        result = self.client.review_revision(500, comment="Auto-approved")

        self.assertIsInstance(result, ReviewResult)
        self.assertTrue(result.success)
        self.assertEqual(result.revid, 500)
        self.assertIn("approved", result.message)

        # Check review request params
        review_req = self.site.requests[1]
        self.assertEqual(review_req["action"], "review")
        self.assertEqual(review_req["revid"], 500)
        self.assertEqual(review_req["comment"], "Auto-approved")
        self.assertEqual(review_req["token"], "abc123+\\")

    def test_successful_unapproval(self):
        self.site.set_responses([
            {"query": {"tokens": {"csrftoken": "tok+\\"}}},
            {"review": {"revid": 600}},
        ])

        result = self.client.review_revision(600, unapprove=True)

        self.assertTrue(result.success)
        self.assertIn("un-approved", result.message)

        review_req = self.site.requests[1]
        self.assertEqual(review_req["unapprove"], 1)

    def test_review_api_error(self):
        self.site.set_responses([
            {"query": {"tokens": {"csrftoken": "tok+\\"}}},
            {"error": {"code": "permissiondenied", "info": "You don't have permission"}},
        ])

        result = self.client.review_revision(700)

        self.assertFalse(result.success)
        self.assertIn("permission", result.message)

    def test_csrf_token_failure(self):
        self.site.set_response(RuntimeError("Network error"))

        result = self.client.review_revision(800)

        self.assertFalse(result.success)
        self.assertIn("CSRF token", result.message)

    def test_review_request_exception(self):
        self.site.set_responses([
            {"query": {"tokens": {"csrftoken": "tok+\\"}}},
            RuntimeError("Connection reset"),
        ])

        result = self.client.review_revision(900)

        self.assertFalse(result.success)
        self.assertIn("failed", result.message.lower())


class FlaggedRevsClientReviewLogTests(TestCase):
    """Tests for FlaggedRevsClient.get_review_log()."""

    def setUp(self):
        self.site = FakeSite()
        self.client = FlaggedRevsClient(self.site)

    def test_returns_log_events(self):
        self.site.set_response({
            "query": {
                "logevents": [
                    {
                        "logid": 1,
                        "action": "approve",
                        "user": "Reviewer1",
                        "timestamp": "2026-02-10T12:00:00Z",
                        "params": {"0": 500},
                    },
                    {
                        "logid": 2,
                        "action": "unapprove",
                        "user": "Admin1",
                        "timestamp": "2026-02-11T08:00:00Z",
                        "params": {"0": 500},
                    },
                ]
            }
        })

        events = self.client.get_review_log("Helsinki")

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["action"], "approve")
        self.assertEqual(events[1]["action"], "unapprove")

        req = self.site.requests[0]
        self.assertEqual(req["letitle"], "Helsinki")

    def test_respects_limit_cap(self):
        self.site.set_response({"query": {"logevents": []}})
        self.client.get_review_log("Test", limit=1000)

        req = self.site.requests[0]
        self.assertEqual(req["lelimit"], 500)

    def test_api_error_returns_empty(self):
        self.site.set_response(RuntimeError("fail"))
        events = self.client.get_review_log("Test")
        self.assertEqual(events, [])
