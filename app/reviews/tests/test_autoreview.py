from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

from reviews import autoreview
from reviews.services import was_user_blocked_after


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

        # Mock parent revision
        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = "Article intro. More text."

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

        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = "Article text. More text."

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

        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = "Section 1. Section 2."

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

        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = "Article text. More text."

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

        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = "Article text. More text."

            # Current stable has the addition plus extra content
            current_stable = (
                "Article text. New intro. User added this sentence. " "New conclusion. More text."
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

        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = "Article text. More text."

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

        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = "Article text. More text."

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

        with patch("reviews.autoreview._get_parent_wikitext") as mock_parent:
            mock_parent.return_value = ""

            current_stable = ""
            threshold = 0.2

            result = autoreview._is_addition_superseded(mock_revision, current_stable, threshold)
            # Should return False (can't compare against empty)
            self.assertFalse(result)
