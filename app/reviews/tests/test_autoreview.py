"""Tests for timing functionality in autoreview.py"""

import time
from unittest.mock import MagicMock, Mock, patch
from datetime import datetime

from django.test import TestCase

from ..services import was_user_blocked_after
from ..autoreview import (
    run_autoreview_for_page,
    _evaluate_revision,
    AutoreviewDecision,
)
from .. import autoreview


class TimingInTestsTestCase(TestCase):
    """Test that timing information is captured for each test."""

    def setUp(self):
        """Set up common test fixtures."""
        self.mock_wiki = Mock()
        self.mock_wiki.code = "en"
        self.mock_wiki.family = "wikipedia"
        self.mock_wiki.configuration = Mock()
        self.mock_wiki.configuration.auto_approved_groups = []
        self.mock_wiki.configuration.blocking_categories = []
        self.mock_wiki.configuration.redirect_aliases = ["#REDIRECT"]

        self.mock_page = Mock()
        self.mock_page.wiki = self.mock_wiki
        self.mock_page.stable_revid = 100
        self.mock_page.categories = []

        self.mock_revision = Mock()
        self.mock_revision.revid = 200
        self.mock_revision.user_name = "TestUser"
        self.mock_revision.timestamp = datetime(2025, 1, 1, 12, 0, 0)
        self.mock_revision.parentid = 100
        self.mock_revision.page = self.mock_page
        self.mock_revision.superset_data = {}
        self.mock_revision.render_error_count = None
        self.mock_revision.get_wikitext = Mock(return_value="Test content")
        self.mock_revision.get_categories = Mock(return_value=[])

        self.mock_client = Mock()
        self.mock_client.is_user_blocked_after_edit = Mock(return_value=False)
        self.mock_client.get_rendered_html = Mock(return_value="<html></html>")

    @patch('reviews.autoreview.is_bot_edit')
    def test_bot_user_test_includes_timing(self, mock_is_bot):
        """Test that bot user check includes duration_ms."""
        mock_is_bot.return_value = True
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        self.assertEqual(len(result["tests"]), 1)
        test = result["tests"][0]
        self.assertIn("duration_ms", test)
        self.assertIsInstance(test["duration_ms"], (int, float))
        self.assertGreaterEqual(test["duration_ms"], 0)
        self.assertEqual(test["id"], "bot-user")

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview._is_article_to_redirect_conversion')
    @patch('reviews.autoreview.is_bot_edit')
    def test_blocked_user_test_includes_timing(self, mock_is_bot, mock_redirect, mock_render):
        """Test that blocked user check includes duration_ms."""
        mock_is_bot.return_value = False
        mock_redirect.return_value = False
        mock_render.return_value = False
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        # Should have bot-user test and blocked-user test
        self.assertGreaterEqual(len(result["tests"]), 2)
        blocked_test = next(t for t in result["tests"] if t["id"] == "blocked-user")
        self.assertIn("duration_ms", blocked_test)
        self.assertIsInstance(blocked_test["duration_ms"], (int, float))
        self.assertGreaterEqual(blocked_test["duration_ms"], 0)

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview.is_bot_edit')
    def test_blocked_user_exception_includes_timing(self, mock_is_bot, mock_render):
        """Test that timing is captured even when block check fails."""
        mock_is_bot.return_value = False
        mock_render.return_value = False
        self.mock_client.is_user_blocked_after_edit = Mock(side_effect=Exception("API Error"))
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        blocked_test = next(t for t in result["tests"] if t["id"] == "blocked-user")
        self.assertIn("duration_ms", blocked_test)
        self.assertEqual(blocked_test["status"], "fail")
        self.assertGreaterEqual(blocked_test["duration_ms"], 0)

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview._is_article_to_redirect_conversion')
    @patch('reviews.autoreview.is_bot_edit')
    def test_auto_approved_groups_test_includes_timing(self, mock_is_bot, mock_redirect, mock_render):
        """Test that auto-approved groups check includes duration_ms."""
        mock_is_bot.return_value = False
        mock_redirect.return_value = False
        mock_render.return_value = False
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={"sysop": "sysop"},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        group_test = next(t for t in result["tests"] if t["id"] == "auto-approved-group")
        self.assertIn("duration_ms", group_test)
        self.assertIsInstance(group_test["duration_ms"], (int, float))
        self.assertGreaterEqual(group_test["duration_ms"], 0)

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview._get_parent_wikitext')
    @patch('reviews.autoreview.is_bot_edit')
    def test_redirect_conversion_test_includes_timing(self, mock_is_bot, mock_parent_wikitext, mock_render):
        """Test that redirect conversion check includes duration_ms."""
        mock_is_bot.return_value = False
        mock_parent_wikitext.return_value = "Parent content"
        mock_render.return_value = False
        self.mock_revision.get_wikitext = Mock(return_value="Regular article content")
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        redirect_test = next(
            t for t in result["tests"] if t["id"] == "article-to-redirect-conversion"
        )
        self.assertIn("duration_ms", redirect_test)
        self.assertIsInstance(redirect_test["duration_ms"], (int, float))
        self.assertGreaterEqual(redirect_test["duration_ms"], 0)

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview._is_article_to_redirect_conversion')
    @patch('reviews.autoreview.is_bot_edit')
    def test_blocking_categories_test_includes_timing(self, mock_is_bot, mock_redirect, mock_render):
        """Test that blocking categories check includes duration_ms."""
        mock_is_bot.return_value = False
        mock_redirect.return_value = False
        mock_render.return_value = False
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={"category:spam": "Category:Spam"},
            redirect_aliases=["#REDIRECT"],
        )
        
        category_test = next(t for t in result["tests"] if t["id"] == "blocking-categories")
        self.assertIn("duration_ms", category_test)
        self.assertIsInstance(category_test["duration_ms"], (int, float))
        self.assertGreaterEqual(category_test["duration_ms"], 0)

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview._is_article_to_redirect_conversion')
    @patch('reviews.autoreview.is_bot_edit')
    def test_render_errors_test_includes_timing(self, mock_is_bot, mock_redirect, mock_render):
        """Test that render errors check includes duration_ms."""
        mock_is_bot.return_value = False
        mock_redirect.return_value = False
        mock_render.return_value = False
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        render_test = next(t for t in result["tests"] if t["id"] == "new-render-errors")
        self.assertIn("duration_ms", render_test)
        self.assertIsInstance(render_test["duration_ms"], (int, float))
        self.assertGreaterEqual(render_test["duration_ms"], 0)


class TimingPrecisionTestCase(TestCase):
    """Test that timing has appropriate precision."""

    def setUp(self):
        """Set up common test fixtures."""
        self.mock_wiki = Mock()
        self.mock_wiki.code = "en"
        self.mock_wiki.family = "wikipedia"

        self.mock_page = Mock()
        self.mock_page.wiki = self.mock_wiki
        self.mock_page.categories = []

        self.mock_revision = Mock()
        self.mock_revision.revid = 200
        self.mock_revision.user_name = "TestUser"
        self.mock_revision.timestamp = datetime(2025, 1, 1, 12, 0, 0)
        self.mock_revision.parentid = 100
        self.mock_revision.page = self.mock_page
        self.mock_revision.superset_data = {}
        self.mock_revision.render_error_count = None
        self.mock_revision.get_wikitext = Mock(return_value="Test content")
        self.mock_revision.get_categories = Mock(return_value=[])

        self.mock_client = Mock()
        self.mock_client.is_user_blocked_after_edit = Mock(return_value=False)

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview.is_bot_edit')
    def test_timing_has_millisecond_precision(self, mock_is_bot, mock_render):
        """Test that timing is reported in milliseconds with 2 decimal places."""
        mock_is_bot.return_value = False
        mock_render.return_value = False
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        for test in result["tests"]:
            duration = test["duration_ms"]
            # Check that it's rounded to 2 decimal places
            self.assertEqual(duration, round(duration, 2))

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview.is_bot_edit')
    def test_timing_is_positive(self, mock_is_bot, mock_render):
        """Test that all timing values are non-negative."""
        mock_is_bot.return_value = False
        mock_render.return_value = False
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        for test in result["tests"]:
            self.assertGreaterEqual(test["duration_ms"], 0)


class TotalTimingInRunAutoreviewTestCase(TestCase):
    """Test that total timing is captured for revision processing."""

    def setUp(self):
        """Set up common test fixtures."""
        self.mock_wiki = Mock()
        self.mock_wiki.code = "en"
        self.mock_wiki.configuration = Mock()
        self.mock_wiki.configuration.auto_approved_groups = []
        self.mock_wiki.configuration.blocking_categories = []

        self.mock_page = Mock()
        self.mock_page.wiki = self.mock_wiki
        self.mock_page.stable_revid = 100

    @patch('reviews.autoreview._evaluate_revision')
    @patch('reviews.autoreview.WikiClient')
    @patch('reviews.autoreview._get_redirect_aliases')
    @patch('reviews.autoreview.EditorProfile')
    def test_run_autoreview_includes_total_time(
        self,
        mock_profile_cls,
        mock_aliases,
        mock_client_cls,
        mock_evaluate,
    ):
        """Test that run_autoreview_for_page includes total_time_ms."""
        # Setup mocks
        mock_revision = Mock()
        mock_revision.revid = 200
        mock_revision.user_name = "TestUser"
        
        self.mock_page.revisions.exclude().order_by = Mock(return_value=[mock_revision])
        mock_profile_cls.objects.filter = Mock(return_value=[])
        mock_aliases.return_value = ["#REDIRECT"]
        
        mock_evaluate.return_value = {
            "tests": [{"id": "test", "duration_ms": 1.5}],
            "decision": AutoreviewDecision(
                status="manual",
                label="Test",
                reason="Test reason"
            ),
        }
        
        # Run the function
        results = run_autoreview_for_page(self.mock_page)
        
        # Check results
        self.assertEqual(len(results), 1)
        self.assertIn("total_time_ms", results[0])
        self.assertIsInstance(results[0]["total_time_ms"], (int, float))
        self.assertGreaterEqual(results[0]["total_time_ms"], 0)

    @patch('reviews.autoreview._evaluate_revision')
    @patch('reviews.autoreview.WikiClient')
    @patch('reviews.autoreview._get_redirect_aliases')
    @patch('reviews.autoreview.EditorProfile')
    def test_total_time_precision(
        self,
        mock_profile_cls,
        mock_aliases,
        mock_client_cls,
        mock_evaluate,
    ):
        """Test that total time has appropriate precision."""
        mock_revision = Mock()
        mock_revision.revid = 200
        mock_revision.user_name = "TestUser"
        
        self.mock_page.revisions.exclude().order_by = Mock(return_value=[mock_revision])
        mock_profile_cls.objects.filter = Mock(return_value=[])
        mock_aliases.return_value = ["#REDIRECT"]
        
        mock_evaluate.return_value = {
            "tests": [],
            "decision": AutoreviewDecision(
                status="manual",
                label="Test",
                reason="Test reason"
            ),
        }
        
        results = run_autoreview_for_page(self.mock_page)
        
        total_time = results[0]["total_time_ms"]
        # Check that it's rounded to 2 decimal places
        self.assertEqual(total_time, round(total_time, 2))

    @patch('reviews.autoreview._evaluate_revision')
    @patch('reviews.autoreview.WikiClient')
    @patch('reviews.autoreview._get_redirect_aliases')
    @patch('reviews.autoreview.EditorProfile')
    def test_multiple_revisions_each_have_timing(
        self,
        mock_profile_cls,
        mock_aliases,
        mock_client_cls,
        mock_evaluate,
    ):
        """Test that each revision gets its own timing."""
        # Create multiple revisions
        revisions = [Mock(revid=i, user_name=f"User{i}") for i in range(200, 203)]
        
        self.mock_page.revisions.exclude().order_by = Mock(return_value=revisions)
        mock_profile_cls.objects.filter = Mock(return_value=[])
        mock_aliases.return_value = ["#REDIRECT"]
        
        mock_evaluate.return_value = {
            "tests": [],
            "decision": AutoreviewDecision(
                status="manual",
                label="Test",
                reason="Test reason"
            ),
        }
        
        results = run_autoreview_for_page(self.mock_page)
        
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertIn("total_time_ms", result)
            self.assertGreaterEqual(result["total_time_ms"], 0)


class ExistingFunctionalityPreservedTestCase(TestCase):
    """Test that existing functionality is not broken by timing changes."""

    def setUp(self):
        """Set up common test fixtures."""
        self.mock_wiki = Mock()
        self.mock_page = Mock()
        self.mock_page.wiki = self.mock_wiki
        self.mock_page.categories = []

        self.mock_revision = Mock()
        self.mock_revision.revid = 200
        self.mock_revision.user_name = "TestUser"
        self.mock_revision.timestamp = datetime(2025, 1, 1, 12, 0, 0)
        self.mock_revision.parentid = 100
        self.mock_revision.page = self.mock_page
        self.mock_revision.superset_data = {}
        self.mock_revision.get_categories = Mock(return_value=[])

        self.mock_client = Mock()
        self.mock_client.is_user_blocked_after_edit = Mock(return_value=False)

    @patch('reviews.autoreview.is_bot_edit')
    def test_decision_structure_unchanged(self, mock_is_bot):
        """Test that decision structure remains the same."""
        mock_is_bot.return_value = True
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        self.assertIn("decision", result)
        decision = result["decision"]
        self.assertEqual(decision.status, "approve")
        self.assertEqual(decision.label, "Would be auto-approved")
        self.assertEqual(decision.reason, "The user is recognized as a bot.")

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview._is_article_to_redirect_conversion')
    @patch('reviews.autoreview.is_bot_edit')
    def test_test_results_structure_preserved(self, mock_is_bot, mock_redirect, mock_render):
        """Test that test result structure is preserved (with addition of duration_ms)."""
        mock_is_bot.return_value = False
        mock_redirect.return_value = False
        mock_render.return_value = False
        
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        
        for test in result["tests"]:
            # Original fields must be present
            self.assertIn("id", test)
            self.assertIn("title", test)
            self.assertIn("status", test)
            self.assertIn("message", test)
            # New field added
            self.assertIn("duration_ms", test)

    @patch('reviews.autoreview._evaluate_revision')
    @patch('reviews.autoreview.WikiClient')
    @patch('reviews.autoreview._get_redirect_aliases')
    @patch('reviews.autoreview.EditorProfile')
    def test_run_autoreview_structure_preserved(
        self,
        mock_profile_cls,
        mock_aliases,
        mock_client_cls,
        mock_evaluate,
    ):
        """Test that run_autoreview_for_page structure is preserved."""
        mock_wiki = Mock()
        mock_wiki.configuration = Mock()
        mock_wiki.configuration.auto_approved_groups = []
        mock_wiki.configuration.blocking_categories = []

        mock_page = Mock()
        mock_page.wiki = mock_wiki
        mock_page.stable_revid = 100

        mock_revision = Mock()
        mock_revision.revid = 200
        mock_revision.user_name = "TestUser"
        
        mock_page.revisions.exclude().order_by = Mock(return_value=[mock_revision])
        mock_profile_cls.objects.filter = Mock(return_value=[])
        mock_aliases.return_value = ["#REDIRECT"]
        
        mock_evaluate.return_value = {
            "tests": [{"id": "test", "title": "Test", "status": "ok", 
                      "message": "Test message", "duration_ms": 1.0}],
            "decision": AutoreviewDecision(
                status="manual",
                label="Test",
                reason="Test reason"
            ),
        }
        
        results = run_autoreview_for_page(mock_page)
        
        # Original structure must be present
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertIn("revid", result)
        self.assertIn("tests", result)
        self.assertIn("decision", result)
        self.assertIn("status", result["decision"])
        self.assertIn("label", result["decision"])
        self.assertIn("reason", result["decision"])
        # New field added
        self.assertIn("total_time_ms", result)


class TimingOverheadTestCase(TestCase):
    """Test that timing overhead is minimal."""

    def setUp(self):
        """Set up common test fixtures."""
        self.mock_wiki = Mock()
        self.mock_page = Mock()
        self.mock_page.wiki = self.mock_wiki
        self.mock_page.categories = []

        self.mock_revision = Mock()
        self.mock_revision.revid = 200
        self.mock_revision.user_name = "TestUser"
        self.mock_revision.timestamp = datetime(2025, 1, 1, 12, 0, 0)
        self.mock_revision.parentid = 100
        self.mock_revision.page = self.mock_page
        self.mock_revision.superset_data = {}
        self.mock_revision.render_error_count = None
        self.mock_revision.get_wikitext = Mock(return_value="Test content")
        self.mock_revision.get_categories = Mock(return_value=[])

        self.mock_client = Mock()
        self.mock_client.is_user_blocked_after_edit = Mock(return_value=False)

    @patch('reviews.autoreview._check_for_new_render_errors')
    @patch('reviews.autoreview.is_bot_edit')
    def test_timing_does_not_slow_execution_significantly(self, mock_is_bot, mock_render):
        """Test that timing instrumentation has minimal overhead."""
        mock_is_bot.return_value = False
        mock_render.return_value = False
        
        start = time.perf_counter()
        result = _evaluate_revision(
            self.mock_revision,
            self.mock_client,
            None,
            auto_groups={},
            blocking_categories={},
            redirect_aliases=["#REDIRECT"],
        )
        end = time.perf_counter()
        actual_time = (end - start) * 1000
        
        # The sum of reported test times should be less than actual time
        # (because actual includes Python overhead)
        reported_time = sum(test["duration_ms"] for test in result["tests"])
        
        # Reported time should be reasonable relative to actual time
        # (within 50% overhead for timing instrumentation)
        self.assertLessEqual(reported_time, actual_time * 1.5)


class ISBNValidationTests(TestCase):
    """Test ISBN-10 and ISBN-13 checksum validation."""

    def test_valid_isbn_10_with_numeric_check_digit(self):
        """Valid ISBN-10 with numeric check digit should pass."""
        self.assertTrue(_validate_isbn_10("0306406152"))

    def test_valid_isbn_10_with_x_check_digit(self):
        """Valid ISBN-10 with 'X' check digit should pass."""
        self.assertTrue(_validate_isbn_10("043942089X"))
        self.assertTrue(_validate_isbn_10("043942089x"))  # lowercase x

    def test_invalid_isbn_10_wrong_checksum(self):
        """ISBN-10 with wrong checksum should fail."""
        self.assertFalse(_validate_isbn_10("0306406153"))  # Last digit wrong

    def test_invalid_isbn_10_too_short(self):
        """ISBN-10 with fewer than 10 digits should fail."""
        self.assertFalse(_validate_isbn_10("030640615"))

    def test_invalid_isbn_10_too_long(self):
        """ISBN-10 with more than 10 digits should fail."""
        self.assertFalse(_validate_isbn_10("03064061521"))

    def test_invalid_isbn_10_with_letters(self):
        """ISBN-10 with invalid characters should fail."""
        self.assertFalse(_validate_isbn_10("030640A152"))

    def test_valid_isbn_13_starting_with_978(self):
        """Valid ISBN-13 starting with 978 should pass."""
        self.assertTrue(_validate_isbn_13("9780306406157"))

    def test_valid_isbn_13_starting_with_979(self):
        """Valid ISBN-13 starting with 979 should pass."""
        self.assertTrue(_validate_isbn_13("9791234567896"))

    def test_invalid_isbn_13_wrong_checksum(self):
        """ISBN-13 with wrong checksum should fail."""
        self.assertFalse(_validate_isbn_13("9780306406158"))  # Last digit wrong

    def test_invalid_isbn_13_wrong_prefix(self):
        """ISBN-13 not starting with 978 or 979 should fail."""
        self.assertFalse(_validate_isbn_13("9771234567890"))

    def test_invalid_isbn_13_too_short(self):
        """ISBN-13 with fewer than 13 digits should fail."""
        self.assertFalse(_validate_isbn_13("978030640615"))

    def test_invalid_isbn_13_too_long(self):
        """ISBN-13 with more than 13 digits should fail."""
        self.assertFalse(_validate_isbn_13("97803064061571"))

    def test_invalid_isbn_13_with_letters(self):
        """ISBN-13 with non-digit characters should fail."""
        self.assertFalse(_validate_isbn_13("978030640615X"))


class ISBNDetectionTests(TestCase):
    """Test ISBN detection in wikitext."""

    def test_no_isbns_in_text(self):
        """Text without ISBNs should return empty list."""
        text = "This is just normal text without any ISBNs."
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_valid_isbn_10_with_hyphens(self):
        """Valid ISBN-10 with hyphens should not be flagged."""
        text = "isbn: 0-306-40615-2"
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_valid_isbn_10_with_spaces(self):
        """Valid ISBN-10 with spaces should not be flagged."""
        text = "isbn 0 306 40615 2"
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_valid_isbn_10_no_separators(self):
        """Valid ISBN-10 without separators should not be flagged."""
        text = "ISBN:0306406152"
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_valid_isbn_13_various_formats(self):
        """Valid ISBN-13 in various formats should not be flagged."""
        text1 = "ISBN: 978-0-306-40615-7"
        text2 = "isbn = 978 0 306 40615 7"
        text3 = "Isbn:9780306406157"
        self.assertEqual(_find_invalid_isbns(text1), [])
        self.assertEqual(_find_invalid_isbns(text2), [])
        self.assertEqual(_find_invalid_isbns(text3), [])

    def test_invalid_isbn_10_detected(self):
        """Invalid ISBN-10 should be detected."""
        text = "isbn: 0-306-40615-3"  # Wrong check digit
        invalid = _find_invalid_isbns(text)
        self.assertEqual(len(invalid), 1)
        self.assertIn("0-306-40615-3", invalid[0])

    def test_invalid_isbn_13_detected(self):
        """Invalid ISBN-13 should be detected."""
        text = "ISBN: 978-0-306-40615-8"  # Wrong check digit
        invalid = _find_invalid_isbns(text)
        self.assertEqual(len(invalid), 1)

    def test_isbn_too_short_detected(self):
        """ISBN with fewer than 10 digits should be detected as invalid."""
        text = "isbn: 123-456"
        invalid = _find_invalid_isbns(text)
        self.assertEqual(len(invalid), 1)

    def test_isbn_too_long_detected(self):
        """ISBN with more than 13 digits should be detected as invalid."""
        text = "isbn: 12345678901234"
        invalid = _find_invalid_isbns(text)
        self.assertEqual(len(invalid), 1)

    def test_multiple_valid_isbns(self):
        """Multiple valid ISBNs should not be flagged."""
        text = """
        First book: ISBN: 0-306-40615-2
        Second book: ISBN: 978-0-306-40615-7
        """
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_multiple_isbns_with_one_invalid(self):
        """Text with one invalid ISBN among valid ones should flag the invalid one."""
        text = """
        Valid: ISBN: 0-306-40615-2
        Invalid: ISBN: 978-0-306-40615-8
        """
        invalid = _find_invalid_isbns(text)
        self.assertEqual(len(invalid), 1)

    def test_multiple_invalid_isbns(self):
        """Text with multiple invalid ISBNs should flag all of them."""
        text = """
        Invalid 1: ISBN: 0-306-40615-3
        Invalid 2: ISBN: 978-0-306-40615-8
        """
        invalid = _find_invalid_isbns(text)
        self.assertEqual(len(invalid), 2)

    def test_case_insensitive_isbn_detection(self):
        """ISBN detection should be case-insensitive."""
        text1 = "ISBN: 0-306-40615-2"
        text2 = "isbn: 0-306-40615-2"
        text3 = "Isbn: 0-306-40615-2"
        self.assertEqual(_find_invalid_isbns(text1), [])
        self.assertEqual(_find_invalid_isbns(text2), [])
        self.assertEqual(_find_invalid_isbns(text3), [])

    def test_isbn_with_equals_sign(self):
        """ISBN with = separator should be detected."""
        text = "isbn = 0-306-40615-2"
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_isbn_with_colon(self):
        """ISBN with : separator should be detected."""
        text = "isbn: 0-306-40615-2"
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_isbn_no_separator(self):
        """ISBN without separator should be detected."""
        text = "isbn 0-306-40615-2"
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_real_world_wikipedia_citation(self):
        """Test with realistic Wikipedia citation format."""
        text = """
        {{cite book |last=Smith |first=John |title=Example Book
        |publisher=Example Press |year=2020 |isbn=978-0-306-40615-7}}
        """
        self.assertEqual(_find_invalid_isbns(text), [])

    def test_invalid_isbn_in_wikipedia_citation(self):
        """Test invalid ISBN in Wikipedia citation format."""
        text = """
        {{cite book |last=Smith |first=John |title=Fake Book
        |publisher=Fake Press |year=2020 |isbn=978-0-306-40615-8}}
        """
        invalid = _find_invalid_isbns(text)
        self.assertEqual(len(invalid), 1)

    def test_isbn_with_trailing_year(self):
        """Test that trailing years are not captured as part of ISBN."""
        text = "isbn: 978 0 306 40615 7 2020"
        invalid = _find_invalid_isbns(text)
        # Should recognize valid ISBN and not capture the year
        self.assertEqual(len(invalid), 0)

    def test_isbn_with_spaces_around_hyphens(self):
        """Test that ISBNs with spaces around hyphens are fully captured."""
        text = "isbn: 978 - 0 - 306 - 40615 - 7"
        invalid = _find_invalid_isbns(text)
        # Should recognize valid ISBN with spaces around hyphens
        self.assertEqual(len(invalid), 0)

    def test_isbn_followed_by_punctuation(self):
        """Test that ISBNs followed by punctuation are correctly detected."""
        # ISBN followed by comma
        text1 = "isbn: 9780306406157, 2020"
        self.assertEqual(_find_invalid_isbns(text1), [])

        # ISBN followed by period
        text2 = "isbn: 0-306-40615-2."
        self.assertEqual(_find_invalid_isbns(text2), [])

        # ISBN followed by semicolon
        text3 = "isbn: 978-0-306-40615-7; another book"
        self.assertEqual(_find_invalid_isbns(text3), [])

        # Invalid ISBN followed by comma
        text4 = "isbn: 9780306406158, 2020"
        invalid = _find_invalid_isbns(text4)
        self.assertEqual(len(invalid), 1)


class AutoreviewBlockedUserTests(TestCase):
    """Test blocked user functionality."""
    
    def setUp(self):
        """Clear the LRU cache before each test."""
        was_user_blocked_after.cache_clear()

    @patch("reviews.services.pywikibot.Site")
    @patch("reviews.autoreview._is_bot_user")
    def test_blocked_user_not_auto_approved(self, mock_is_bot, mock_site):
        """Test that a user blocked after making an edit is NOT auto-approved."""
        mock_is_bot.return_value = False  # User is NOT a bot

        # Mock the pywikibot.Site and logevents to return a block event
        mock_site_instance = MagicMock()
        mock_site.return_value = mock_site_instance

        # Create a mock block event
        mock_block_event = MagicMock()
        mock_block_event.action.return_value = "block"
        mock_site_instance.logevents.return_value = [mock_block_event]

        profile = MagicMock()
        profile.usergroups = []
        profile.is_bot = False

        mock_wiki = MagicMock()
        mock_wiki.code = "fi"
        mock_wiki.family = "wikipedia"

        revision = MagicMock()
        revision.user_name = "BlockedUser"
        revision.timestamp = datetime.fromisoformat("2024-01-15T10:00:00")
        revision.page.categories = []
        revision.page.wiki = mock_wiki

        # Create a mock WikiClient - but we need the real is_user_blocked_after_edit method
        from reviews.services import WikiClient

        mock_client = WikiClient(mock_wiki)

        # Call with correct signature: revision, client, profile, **kwargs
        result = autoreview._evaluate_revision(
            revision,
            mock_client,
            profile,
            auto_groups={},
            blocking_categories={},
            redirect_aliases={},
        )

        # Assert
        self.assertEqual(result["decision"].status, "blocked")
        self.assertTrue(any(t["id"] == "blocked-user" for t in result["tests"]))

        # Verify pywikibot.Site was called (will be called twice:
        # once in WikiClient.__init__, once in was_user_blocked_after)
        self.assertGreaterEqual(mock_site.call_count, 1)

        # Verify logevents was called with correct parameters
        mock_site_instance.logevents.assert_called_once()
