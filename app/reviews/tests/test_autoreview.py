from __future__ import annotations

from datetime import timedelta
from unittest import mock

from bot_control.models import BotActivity
from django.test import TestCase
from django.utils import timezone

from reviews.autoreview.base import CheckResult
from reviews.autoreview.decision import AutoreviewDecision
from reviews.autoreview.runner import (
    review_single_revision,
    run_autoreview_for_page,
    run_checks_pipeline,
)
from reviews.models import (
    EditorProfile,
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_check(
    check_id: str,
    status: str = "ok",
    message: str = "OK",
    decision: AutoreviewDecision | None = None,
    should_stop: bool = False,
):
    """Return a check-info dict whose function returns a fixed CheckResult."""

    def _fn(context):
        return CheckResult(
            check_id=check_id,
            check_title=check_id.replace("-", " ").title(),
            status=status,
            message=message,
            decision=decision,
            should_stop=should_stop,
        )

    return {"id": check_id, "name": check_id, "function": _fn, "priority": 0}


class FakeRequest:
    """Minimal mock for pywikibot site.simple_request()."""

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
        self.responses = [response]
        self._call_idx = 0

    def set_responses(self, responses: list[dict | Exception]):
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


class _BaseTestCase(TestCase):
    """Shared setUp for tests that need a Wiki, Page, Revision, and config."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            api_endpoint="https://test.example/api.php",
        )
        WikiConfiguration.objects.create(
            wiki=self.wiki,
            auto_approved_groups=[],
            blocking_categories=[],
            redirect_aliases=["#REDIRECT"],
        )
        self.page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=100,
            title="Test_Page",
            stable_revid=999,
            pending_since=timezone.now() - timedelta(hours=1),
        )
        self.revision = PendingRevision.objects.create(
            page=self.page,
            revid=1001,
            parentid=999,
            user_name="TestUser",
            user_id=42,
            timestamp=timezone.now() - timedelta(minutes=30),
            age_at_fetch=timedelta(minutes=30),
            sha1="abc123",
            comment="Test edit",
            wikitext="Hello world",
        )
        self.profile = EditorProfile.objects.create(
            wiki=self.wiki,
            username="TestUser",
        )

        # Patch pywikibot.Site so no real network calls happen
        self.fake_site = FakeSite()
        self.site_patcher = mock.patch(
            "reviews.services.wiki_client.pywikibot.Site",
            return_value=self.fake_site,
        )
        self.site_patcher.start()
        self.addCleanup(self.site_patcher.stop)


# ===================================================================
# run_checks_pipeline tests
# ===================================================================


class RunChecksPipelineTests(_BaseTestCase):
    """Tests for :func:`run_checks_pipeline`."""

    def _run(self, checks):
        from reviews.services import WikiClient

        client = WikiClient(self.wiki)
        with mock.patch("reviews.autoreview.runner.get_enabled_checks", return_value=checks):
            return run_checks_pipeline(
                self.revision,
                client,
                self.profile,
                auto_groups={},
                blocking_categories={},
                redirect_aliases=[],
            )

    def test_all_checks_pass_returns_manual(self):
        """When no check stops the pipeline, the decision is 'manual'."""
        checks = [_make_check("check-a"), _make_check("check-b")]
        result = self._run(checks)

        self.assertEqual(result["decision"].status, "manual")
        self.assertEqual(len(result["tests"]), 2)
        self.assertIn("total_duration_ms", result)

    def test_blocking_check_stops_pipeline(self):
        """A check that sets should_stop=True halts further checks."""
        block_decision = AutoreviewDecision(status="blocked", label="Blocked", reason="Bad edit")
        checks = [
            _make_check(
                "blocker",
                status="fail",
                message="Blocked",
                decision=block_decision,
                should_stop=True,
            ),
            _make_check("should-not-run"),
        ]
        result = self._run(checks)

        self.assertEqual(result["decision"].status, "blocked")
        # Only the first check should have run
        self.assertEqual(len(result["tests"]), 1)
        self.assertEqual(result["tests"][0]["id"], "blocker")

    def test_approve_check_stops_pipeline(self):
        """An approving check stops the pipeline with 'approve'."""
        approve_decision = AutoreviewDecision(
            status="approve", label="Auto-approved", reason="Trusted group"
        )
        checks = [
            _make_check(
                "auto-group",
                status="ok",
                decision=approve_decision,
                should_stop=True,
            ),
            _make_check("unreachable"),
        ]
        result = self._run(checks)

        self.assertEqual(result["decision"].status, "approve")
        self.assertEqual(len(result["tests"]), 1)

    def test_empty_checks_returns_manual(self):
        """With no checks configured, the decision defaults to 'manual'."""
        result = self._run([])

        self.assertEqual(result["decision"].status, "manual")
        self.assertEqual(result["tests"], [])

    def test_check_duration_recorded(self):
        """Each check result includes a duration_ms field."""
        checks = [_make_check("timing-check")]
        result = self._run(checks)

        self.assertIn("duration_ms", result["tests"][0])
        self.assertGreaterEqual(result["tests"][0]["duration_ms"], 0)


# ===================================================================
# review_single_revision tests
# ===================================================================


class ReviewSingleRevisionTests(_BaseTestCase):
    """Tests for :func:`review_single_revision`."""

    def _patch_pipeline(self, decision_status, decision_label="", decision_reason=""):
        """Return a context manager that patches run_checks_pipeline."""
        decision = AutoreviewDecision(
            status=decision_status,
            label=decision_label or decision_status.title(),
            reason=decision_reason or f"Reason for {decision_status}",
        )
        fake_result = {
            "tests": [
                {
                    "id": "fake-check",
                    "title": "Fake Check",
                    "status": "ok",
                    "message": "OK",
                    "duration_ms": 1.5,
                }
            ],
            "decision": decision,
            "total_duration_ms": 2.0,
        }
        return mock.patch(
            "reviews.autoreview.runner.run_checks_pipeline",
            return_value=fake_result,
        )

    def test_approve_dry_run_does_not_submit(self):
        """In dry-run mode, approve decisions do NOT call the FlaggedRevs API."""
        with self._patch_pipeline("approve"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=True)

        self.assertEqual(result["decision"]["status"], "approve")
        self.assertEqual(result["mode"], "dry-run")
        self.assertFalse(result["review_submitted"])

    def test_approve_live_submits_review(self):
        """In live mode, approve decisions call FlaggedRevsClient.review_revision."""
        self.fake_site.set_responses(
            [
                {"query": {"tokens": {"csrftoken": "tok+\\"}}},
                {"review": {"revid": 1001}},
            ]
        )
        with self._patch_pipeline("approve"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=False)

        self.assertEqual(result["decision"]["status"], "approve")
        self.assertEqual(result["mode"], "live")
        self.assertTrue(result["review_submitted"])
        self.assertIn("approved", result["review_message"])

    def test_approve_live_api_failure(self):
        """When the FlaggedRevs API rejects the review, review_submitted is False."""
        self.fake_site.set_responses(
            [
                # CSRF token
                {"query": {"tokens": {"csrftoken": "tok+\\"}}},
                # Review API returns error
                {"error": {"code": "permissiondenied", "info": "No permission"}},
            ]
        )
        with self._patch_pipeline("approve"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=False)

        self.assertFalse(result["review_submitted"])
        self.assertIn("permission", result["review_message"].lower())

    def test_blocked_decision_no_review(self):
        """Blocked decisions never attempt to submit a review."""
        with self._patch_pipeline("blocked"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=False)

        self.assertEqual(result["decision"]["status"], "blocked")
        self.assertFalse(result["review_submitted"])
        # No FlaggedRevs API calls should have been made
        self.assertEqual(len(self.fake_site.requests), 0)

    def test_manual_decision_no_review(self):
        """Manual review decisions never submit a review."""
        with self._patch_pipeline("manual"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=False)

        self.assertEqual(result["decision"]["status"], "manual")
        self.assertFalse(result["review_submitted"])

    def test_logs_bot_activity(self):
        """review_single_revision creates a BotActivity record."""
        with self._patch_pipeline("approve"):
            review_single_revision(revid=1001, wiki_code="test", log_activity=True, dry_run=True)

        activity = BotActivity.objects.filter(revision_id=1001).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.decision, "approve")
        self.assertEqual(activity.wiki_code, "test")
        self.assertEqual(activity.page_id, 100)
        self.assertTrue(activity.is_dry_run)

    def test_no_log_when_disabled(self):
        """When log_activity=False, no BotActivity is created."""
        with self._patch_pipeline("approve"):
            review_single_revision(revid=1001, wiki_code="test", log_activity=False, dry_run=True)

        self.assertEqual(BotActivity.objects.filter(revision_id=1001).count(), 0)

    def test_unknown_wiki_raises(self):
        """ValueError is raised when the wiki code doesn't exist."""
        with self.assertRaises(ValueError) as ctx:
            review_single_revision(revid=1001, wiki_code="nonexistent")
        self.assertIn("not found", str(ctx.exception))

    def test_unknown_revision_raises(self):
        """ValueError is raised when the revision doesn't exist in the DB."""
        with self.assertRaises(ValueError) as ctx:
            review_single_revision(revid=99999, wiki_code="test")
        self.assertIn("not found", str(ctx.exception))

    def test_result_structure(self):
        """The returned dict has all expected keys."""
        with self._patch_pipeline("manual"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=True)

        expected_keys = {
            "revid",
            "tests",
            "decision",
            "total_duration_ms",
            "mode",
            "review_submitted",
            "review_message",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        self.assertEqual(result["revid"], 1001)

    def test_approve_live_exception_handling(self):
        """Network exceptions during review submission are handled gracefully."""
        # The CSRF token request will fail with this exception
        self.fake_site.set_responses(
            [
                RuntimeError("Connection refused"),
            ]
        )
        with self._patch_pipeline("approve"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=False)

        self.assertFalse(result["review_submitted"])
        self.assertIn("CSRF", result["review_message"])

    def test_revision_without_editor_profile(self):
        """Revision whose user has no EditorProfile still processes."""
        self.revision.user_name = "UnknownEditor"
        self.revision.save()

        with self._patch_pipeline("manual"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=True)

        self.assertEqual(result["decision"]["status"], "manual")
        self.assertEqual(result["revid"], 1001)

    def test_revision_with_no_username(self):
        """Revision with empty user_name (anonymous) processes correctly."""
        self.revision.user_name = ""
        self.revision.save()

        with self._patch_pipeline("manual"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=True)

        self.assertEqual(result["decision"]["status"], "manual")

    def test_decision_dict_has_label_and_reason(self):
        """The decision dict includes label and reason from AutoreviewDecision."""
        with self._patch_pipeline("blocked", "Category block", "Page in blocked cat"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=True)

        self.assertEqual(result["decision"]["label"], "Category block")
        self.assertEqual(result["decision"]["reason"], "Page in blocked cat")

    def test_bot_activity_records_check_details(self):
        """BotActivity log captures execution time and check count."""
        with self._patch_pipeline("manual"):
            review_single_revision(revid=1001, wiki_code="test", log_activity=True, dry_run=True)

        activity = BotActivity.objects.get(revision_id=1001)
        self.assertEqual(activity.total_checks_run, 1)
        self.assertGreater(activity.execution_time_ms, 0)
        self.assertEqual(activity.page_title, "Test_Page")
        self.assertEqual(activity.user_name, "TestUser")

    def test_bot_activity_records_determining_check(self):
        """BotActivity determining_check is set when a check has a decision."""
        decision = AutoreviewDecision(status="approve", label="Auto", reason="Trusted")
        fake_result = {
            "tests": [
                {
                    "id": "auto-group-check",
                    "title": "Auto Group Check",
                    "status": "ok",
                    "message": "OK",
                    "duration_ms": 1.0,
                    "decision": decision,
                }
            ],
            "decision": decision,
            "total_duration_ms": 1.0,
        }
        with mock.patch(
            "reviews.autoreview.runner.run_checks_pipeline",
            return_value=fake_result,
        ):
            review_single_revision(revid=1001, wiki_code="test", log_activity=True, dry_run=True)

        activity = BotActivity.objects.get(revision_id=1001)
        self.assertEqual(activity.determining_check, "auto-group-check")

    def test_total_duration_ms_in_result(self):
        """total_duration_ms is forwarded from the pipeline result."""
        with self._patch_pipeline("manual"):
            result = review_single_revision(revid=1001, wiki_code="test", dry_run=True)

        self.assertEqual(result["total_duration_ms"], 2.0)

    def test_redirect_aliases_from_config(self):
        """Cached redirect_aliases prevent extra API calls during review."""
        with self._patch_pipeline("manual"):
            review_single_revision(revid=1001, wiki_code="test", dry_run=True)

        # No requests should have been made to fetch redirect aliases
        # because WikiConfiguration.redirect_aliases is pre-populated
        self.assertEqual(len(self.fake_site.requests), 0)


# ===================================================================
# run_autoreview_for_page tests
# ===================================================================


class RunAutoreviewForPageTests(_BaseTestCase):
    """Tests for :func:`run_autoreview_for_page`."""

    def _patch_pipeline(self, decision_status):
        decision = AutoreviewDecision(
            status=decision_status,
            label=decision_status.title(),
            reason=f"Test {decision_status}",
        )
        fake_result = {
            "tests": [
                {
                    "id": "test-check",
                    "title": "Test Check",
                    "status": "ok",
                    "message": "OK",
                    "duration_ms": 1.0,
                }
            ],
            "decision": decision,
            "total_duration_ms": 1.5,
        }
        return mock.patch(
            "reviews.autoreview.runner.run_checks_pipeline",
            return_value=fake_result,
        )

    def test_no_pending_revisions_returns_empty(self):
        """When all revisions match the stable revid, returns empty list."""
        self.revision.revid = self.page.stable_revid
        self.revision.save()

        results = run_autoreview_for_page(self.page, log_activity=False)
        self.assertEqual(results, [])

    def test_reviews_pending_revision_dry_run(self):
        """Dry-run mode processes the revision but doesn't submit."""
        with self._patch_pipeline("approve"):
            results = run_autoreview_for_page(self.page, log_activity=False, dry_run=True)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["revid"], 1001)
        self.assertEqual(results[0]["decision"]["status"], "approve")
        self.assertEqual(results[0]["mode"], "dry-run")
        self.assertFalse(results[0]["review_submitted"])

    def test_reviews_pending_revision_live(self):
        """Live mode submits the review via FlaggedRevs."""
        self.fake_site.set_responses(
            [
                {"query": {"tokens": {"csrftoken": "tok+\\"}}},
                {"review": {"revid": 1001}},
            ]
        )
        with self._patch_pipeline("approve"):
            results = run_autoreview_for_page(self.page, log_activity=False, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["review_submitted"])
        self.assertEqual(results[0]["mode"], "live")

    def test_blocked_revision_not_submitted(self):
        """Blocked decisions don't submit reviews even in live mode."""
        with self._patch_pipeline("blocked"):
            results = run_autoreview_for_page(self.page, log_activity=False, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["review_submitted"])

    def test_logs_bot_activity(self):
        """BotActivity is created when log_activity=True."""
        with self._patch_pipeline("manual"):
            run_autoreview_for_page(self.page, log_activity=True, dry_run=True)

        activity = BotActivity.objects.filter(revision_id=1001, wiki_code="test").first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.decision, "manual")

    def test_multiple_revisions(self):
        """All pending revisions for a page are processed."""
        PendingRevision.objects.create(
            page=self.page,
            revid=1002,
            parentid=1001,
            user_name="AnotherUser",
            user_id=99,
            timestamp=timezone.now() - timedelta(minutes=10),
            age_at_fetch=timedelta(minutes=10),
            sha1="def456",
            comment="Second edit",
            wikitext="Updated",
        )

        with self._patch_pipeline("manual"):
            results = run_autoreview_for_page(self.page, log_activity=False, dry_run=True)

        self.assertEqual(len(results), 2)
        revids = {r["revid"] for r in results}
        self.assertEqual(revids, {1001, 1002})

    def test_review_api_failure_logged(self):
        """When FlaggedRevs review fails, result captures the failure."""
        self.fake_site.set_responses(
            [
                {"query": {"tokens": {"csrftoken": "tok+\\"}}},
                {"error": {"code": "badtoken", "info": "Invalid token"}},
            ]
        )
        with self._patch_pipeline("approve"):
            results = run_autoreview_for_page(self.page, log_activity=False, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["review_submitted"])
        self.assertIn("token", results[0]["review_message"].lower())


# ===================================================================
# Management command tests
# ===================================================================


class ReviewRevisionCommandTests(_BaseTestCase):
    """Tests for the ``review_revision`` management command."""

    def test_command_dry_run(self):
        """Management command runs in dry-run mode by default."""
        from io import StringIO

        from django.core.management import call_command

        approve_decision = AutoreviewDecision(
            status="approve", label="Approved", reason="All checks passed"
        )
        fake_result = {
            "tests": [
                {
                    "id": "check-1",
                    "title": "Check 1",
                    "status": "ok",
                    "message": "OK",
                    "duration_ms": 1.0,
                }
            ],
            "decision": approve_decision,
            "total_duration_ms": 1.5,
        }
        out = StringIO()
        with mock.patch(
            "reviews.autoreview.runner.run_checks_pipeline",
            return_value=fake_result,
        ):
            call_command("review_revision", "1001", "--wiki=test", stdout=out)

        output = out.getvalue()
        self.assertIn("check-1", output)
        self.assertIn("APPROVE", output)

    def test_command_unknown_wiki(self):
        """Command raises CommandError for non-existent wiki."""
        from io import StringIO

        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command(
                "review_revision",
                "1001",
                "--wiki=nonexistent",
                stdout=StringIO(),
            )

    def test_command_unknown_revision(self):
        """Command raises CommandError for non-existent revision."""
        from io import StringIO

        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command(
                "review_revision",
                "99999",
                "--wiki=test",
                stdout=StringIO(),
            )

    def test_command_live_flag(self):
        """Management command passes --live flag through to review_single_revision."""
        from io import StringIO

        from django.core.management import call_command

        self.fake_site.set_responses(
            [
                {"query": {"tokens": {"csrftoken": "tok+\\"}}},
                {"review": {"revid": 1001}},
            ]
        )
        approve_decision = AutoreviewDecision(status="approve", label="Approved", reason="OK")
        fake_result = {
            "tests": [
                {"id": "c1", "title": "C1", "status": "ok", "message": "OK", "duration_ms": 1.0}
            ],
            "decision": approve_decision,
            "total_duration_ms": 1.0,
        }
        out = StringIO()
        with mock.patch(
            "reviews.autoreview.runner.run_checks_pipeline",
            return_value=fake_result,
        ):
            call_command(
                "review_revision",
                "1001",
                "--wiki=test",
                "--live",
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("LIVE", output)
        self.assertIn("Review submitted", output)

    def test_command_no_log_flag(self):
        """Management command with --no-log skips BotActivity creation."""
        from io import StringIO

        from django.core.management import call_command

        approve_decision = AutoreviewDecision(
            status="manual", label="Manual", reason="Needs review"
        )
        fake_result = {
            "tests": [
                {"id": "c1", "title": "C1", "status": "ok", "message": "OK", "duration_ms": 1.0}
            ],
            "decision": approve_decision,
            "total_duration_ms": 1.0,
        }
        out = StringIO()
        with mock.patch(
            "reviews.autoreview.runner.run_checks_pipeline",
            return_value=fake_result,
        ):
            call_command(
                "review_revision",
                "1001",
                "--wiki=test",
                "--no-log",
                stdout=out,
            )

        self.assertEqual(BotActivity.objects.filter(revision_id=1001).count(), 0)

    def test_command_displays_blocked_decision(self):
        """Management command displays blocked decisions with error styling."""
        from io import StringIO

        from django.core.management import call_command

        blocked_decision = AutoreviewDecision(
            status="blocked", label="Blocked", reason="Bad category"
        )
        fake_result = {
            "tests": [
                {
                    "id": "cat-check",
                    "title": "Category Check",
                    "status": "fail",
                    "message": "In blocked category",
                    "duration_ms": 0.5,
                }
            ],
            "decision": blocked_decision,
            "total_duration_ms": 0.8,
        }
        out = StringIO()
        with mock.patch(
            "reviews.autoreview.runner.run_checks_pipeline",
            return_value=fake_result,
        ):
            call_command(
                "review_revision",
                "1001",
                "--wiki=test",
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("BLOCKED", output)
        self.assertIn("Bad category", output)
        self.assertIn("cat-check", output)
