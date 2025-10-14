from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from django.test import TestCase

from reviews import autoreview
from reviews.autoreview import (
    _find_invalid_isbns,
    _validate_isbn_10,
    _validate_isbn_13,
)
from reviews.services import was_user_blocked_after


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


class SupersededAdditionsTests(TestCase):
    """Test suite for superseded additions detection."""

    def test_normalize_wikitext(self):
        """Test that wikitext normalization removes markup correctly."""
        text = "Some text with [[link|display]] and {{template}} and <ref>citation</ref>"
        normalized = autoreview._normalize_wikitext(text)
        self.assertEqual(normalized, "Some text with display and and")

    def test_normalize_wikitext_with_categories(self):
        """Test that category links are removed."""
        text = "Article text [[Category:Test]] more text"
        normalized = autoreview._normalize_wikitext(text)
        self.assertEqual(normalized, "Article text more text")

    def test_extract_additions_simple(self):
        """Test extracting additions from simple text change."""
        parent = "Original text."
        pending = "Original text. New addition."
        additions = autoreview._extract_additions(parent, pending)
        self.assertEqual(len(additions), 1)
        self.assertIn("New addition.", additions[0])

    def test_extract_additions_no_parent(self):
        """Test extraction when there is no parent revision."""
        parent = ""
        pending = "New article text."
        additions = autoreview._extract_additions(parent, pending)
        self.assertEqual(additions, ["New article text."])

    def test_extract_additions_multiple(self):
        """Test extracting multiple separate additions."""
        parent = "First paragraph. Third paragraph."
        pending = "First paragraph. Second paragraph. Third paragraph. Fourth paragraph."
        additions = autoreview._extract_additions(parent, pending)
        self.assertGreaterEqual(len(additions), 2)

    def test_is_addition_superseded_fully_removed(self):
        """Test case 1: Addition was fully removed in current stable."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article intro. User added this content about topic X. More text."
        )
        mock_revision.page = MagicMock()

        # Mock the latest revision (which is different from the one being checked)
        mock_latest = MagicMock()
        mock_latest.revid = 125  # Different from 123
        mock_latest.get_wikitext.return_value = "Article intro. More text."

        # Mock parent revision
        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article intro. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            # Current stable has the addition removed
            current_stable = "Article intro. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            self.assertTrue(result)

    def test_is_addition_superseded_partially_removed(self):
        """Test case 2: Addition was partially removed (majority removed)."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article text. User added a very long detailed sentence about "
            "topic X with lots of information and details here. More text."
        )
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = "Article text. User added info. More text."

        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article text. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            # Current stable only kept a small part (~15% of the addition)
            current_stable = "Article text. User added info. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should be considered superseded as significant content was removed
            self.assertTrue(result)

    def test_is_addition_superseded_moved_text(self):
        """Test case 3: Addition was moved to different location."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Section 1. User added this important content. Section 2."
        )
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = (
            "Section 1. Section 2. User added this important content."
        )

        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Section 1. Section 2."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            # Current stable has the content moved to Section 2
            current_stable = "Section 1. Section 2. User added this important content."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should NOT be superseded as content is still present
            self.assertFalse(result)

    def test_is_addition_superseded_rephrased(self):
        """Test case 4: Addition was rephrased/reworded."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article text. The quick brown fox jumps over the lazy dog. More text."
        )
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = (
            "Article text. A fast brown fox leaps over a sleepy canine. More text."
        )

        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article text. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            # Current stable has similar but rephrased content
            current_stable = "Article text. A fast brown fox leaps over a sleepy canine. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should NOT be superseded due to similarity (even if rephrased)
            self.assertFalse(result)

    def test_is_addition_superseded_with_new_text(self):
        """Test case 5: Addition is present but surrounded by new content."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article text. User added this sentence. More text."
        )
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = (
            "Article text. New intro. User added this sentence. New conclusion. More text."
        )

        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article text. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            # Current stable has the addition plus extra content
            current_stable = (
                "Article text. New intro. User added this sentence. New conclusion. More text."
            )
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should NOT be superseded as the addition is still present
            self.assertFalse(result)

    def test_is_addition_superseded_unchanged(self):
        """Test case 6: Addition remains unchanged."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article text. User added this content. More text."
        )
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = "Article text. User added this content. More text."

        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article text. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            # Current stable has the exact same addition
            current_stable = "Article text. User added this content. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should NOT be superseded
            self.assertFalse(result)

    def test_is_addition_superseded_short_addition(self):
        """Test that very short additions are ignored."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = "Article text. Yes. More text."
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = "Article text. More text."

        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = "Article text. More text."
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            # Current stable doesn't have the short addition
            current_stable = "Article text. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should NOT be considered superseded (too short to matter)
            self.assertFalse(result)

    def test_is_addition_superseded_no_parent(self):
        """Test behavior when there's no parent revision."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = None
        mock_revision.get_wikitext.return_value = "New article content."
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = "Different content."

        with patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter:
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            current_stable = "Different content."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should NOT be superseded (first revision)
            self.assertFalse(result)

    def test_is_addition_superseded_empty_stable(self):
        """Test behavior when current stable is empty."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = "New content added."
        mock_revision.page = MagicMock()

        # Mock the latest revision
        mock_latest = MagicMock()
        mock_latest.revid = 125
        mock_latest.get_wikitext.return_value = ""

        with (
            patch("reviews.autoreview._get_parent_wikitext") as mock_parent,
            patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter,
        ):
            mock_parent.return_value = ""
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            current_stable = ""
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should return False (can't compare against empty)
            self.assertFalse(result)

    def test_is_addition_superseded_is_latest_revision(self):
        """Test that if revision is the latest, it cannot be superseded."""
        mock_revision = MagicMock()
        mock_revision.revid = 123
        mock_revision.parentid = 100
        mock_revision.get_wikitext.return_value = (
            "Article text. User added this content. More text."
        )
        mock_revision.page = MagicMock()

        # Mock the latest revision to be the same as the revision being checked
        mock_latest = MagicMock()
        mock_latest.revid = 123  # Same as mock_revision.revid
        mock_latest.get_wikitext.return_value = "Article text. User added this content. More text."

        with patch("reviews.autoreview.PendingRevision.objects.filter") as mock_filter:
            mock_filter.return_value.order_by.return_value.first.return_value = mock_latest

            current_stable = "Article text. More text."
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should return False because this IS the latest revision
            self.assertFalse(result)
