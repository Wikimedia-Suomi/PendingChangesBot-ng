import unittest
import logging
from unittest.mock import patch, MagicMock
from reviews.autoreview import _evaluate_revision, _get_revertrisk_score

logging.disable(logging.CRITICAL)

class DummyRevision:
    def __init__(self, revid=12345, user_name="TestUser", superset_data=None):
        self.revid = revid
        self.user_name = user_name
        self.page = MagicMock()
        self.page.categories = []
        self.page.wiki = MagicMock()
        self.page.wiki.language_code = "en"
        self.superset_data = superset_data or {}

    def get_categories(self):
        return []

class TestRevertrisk(unittest.TestCase):

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    @patch("reviews.autoreview._get_revertrisk_score")
    def test_high_risk_blocks(self, mock_score, mock_bot_edit):
        mock_score.return_value = 0.9
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "blocked")

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    @patch("reviews.autoreview._get_revertrisk_score")
    def test_low_risk_continues(self, mock_score, mock_bot_edit):
        mock_score.return_value = 0.5
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "manual")

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    @patch("reviews.autoreview._get_revertrisk_score")
    def test_api_error_handled(self, mock_score, mock_bot_edit):
        mock_score.return_value = None
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "manual")

    @patch("reviews.autoreview._get_revertrisk_score")
    def test_bot_bypasses_check(self, mock_score):
        revision = DummyRevision(superset_data={"rc_bot": True})
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=0.8
        )
        self.assertEqual(result["decision"].status, "approve")
        mock_score.assert_not_called()

    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    def test_no_threshold_skips_check(self, mock_bot_edit):
        revision = DummyRevision()
        result = _evaluate_revision(
            revision, None, auto_groups={}, 
            blocking_categories={}, revertrisk_threshold=None
        )
        self.assertFalse(any(t["id"] == "revertrisk" for t in result["tests"]))

    @patch("reviews.autoreview.http.fetch")
    @patch("reviews.autoreview.is_bot_edit", return_value=False)
    def test_api_exception_returns_none(self, mock_bot_edit, mock_fetch):
        mock_fetch.side_effect = Exception("Network error")
        score = _get_revertrisk_score(DummyRevision())
        self.assertIsNone(score)


if __name__ == "__main__":
    unittest.main()