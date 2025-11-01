from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import StringIO
from unittest import mock
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from reviews.models import Wiki, WikiConfiguration

from review_statistics.models import (
    FlaggedRevsStatistics,
    ReviewActivity,
    ReviewStatisticsCache,
    ReviewStatisticsMetadata,
)


class StatisticsModelTests(TestCase):
    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    def test_review_statistics_cache_creation(self):
        """Test creating a review statistics cache entry."""
        stat = ReviewStatisticsCache.objects.create(
            wiki=self.wiki,
            reviewer_name="Reviewer1",
            reviewed_user_name="User1",
            page_title="Test_Page",
            page_id=123,
            reviewed_revision_id=456,
            pending_revision_id=455,
            reviewed_timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            pending_timestamp=datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            review_delay_days=5,
        )
        self.assertEqual(stat.reviewer_name, "Reviewer1")
        self.assertEqual(stat.review_delay_days, 5)

    def test_review_statistics_metadata_creation(self):
        """Test creating statistics metadata."""
        metadata = ReviewStatisticsMetadata.objects.create(
            wiki=self.wiki,
            total_records=100,
            oldest_review_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            newest_review_timestamp=datetime(2025, 1, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(metadata.total_records, 100)
        self.assertEqual(metadata.wiki, self.wiki)


class StatisticsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    def test_api_statistics_empty(self):
        """Test statistics API with no data."""
        response = self.client.get(reverse("api_statistics", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("metadata", data)
        self.assertIn("top_reviewers", data)
        self.assertIn("top_reviewed_users", data)
        self.assertIn("records", data)
        self.assertEqual(data["metadata"]["total_records"], 0)

    def test_api_statistics_with_data(self):
        """Test statistics API with cached data."""
        # Create metadata
        ReviewStatisticsMetadata.objects.create(
            wiki=self.wiki,
            total_records=2,
        )
        # Create statistics entries
        ReviewStatisticsCache.objects.create(
            wiki=self.wiki,
            reviewer_name="Reviewer1",
            reviewed_user_name="User1",
            page_title="Page1",
            page_id=1,
            reviewed_revision_id=10,
            pending_revision_id=9,
            reviewed_timestamp=datetime(2025, 1, 15, tzinfo=timezone.utc),
            pending_timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc),
            review_delay_days=5,
        )
        ReviewStatisticsCache.objects.create(
            wiki=self.wiki,
            reviewer_name="Reviewer1",
            reviewed_user_name="User2",
            page_title="Page2",
            page_id=2,
            reviewed_revision_id=20,
            pending_revision_id=19,
            reviewed_timestamp=datetime(2025, 1, 14, tzinfo=timezone.utc),
            pending_timestamp=datetime(2025, 1, 12, tzinfo=timezone.utc),
            review_delay_days=2,
        )

        response = self.client.get(reverse("api_statistics", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["metadata"]["total_records"], 2)
        self.assertEqual(len(data["top_reviewers"]), 1)
        self.assertEqual(data["top_reviewers"][0]["reviewer_name"], "Reviewer1")
        self.assertEqual(data["top_reviewers"][0]["review_count"], 2)
        self.assertEqual(len(data["records"]), 2)

    def test_api_statistics_with_filters(self):
        """Test statistics API with reviewer filter."""
        ReviewStatisticsCache.objects.create(
            wiki=self.wiki,
            reviewer_name="Reviewer1",
            reviewed_user_name="User1",
            page_title="Page1",
            page_id=1,
            reviewed_revision_id=10,
            pending_revision_id=9,
            reviewed_timestamp=datetime(2025, 1, 15, tzinfo=timezone.utc),
            pending_timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc),
            review_delay_days=5,
        )
        ReviewStatisticsCache.objects.create(
            wiki=self.wiki,
            reviewer_name="Reviewer2",
            reviewed_user_name="User2",
            page_title="Page2",
            page_id=2,
            reviewed_revision_id=20,
            pending_revision_id=19,
            reviewed_timestamp=datetime(2025, 1, 14, tzinfo=timezone.utc),
            pending_timestamp=datetime(2025, 1, 12, tzinfo=timezone.utc),
            review_delay_days=2,
        )

        response = self.client.get(
            reverse("api_statistics", args=[self.wiki.pk]) + "?reviewer=Reviewer1"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["reviewer_name"], "Reviewer1")

    @mock.patch("reviews.views.WikiClient")
    def test_api_statistics_refresh_success(self, mock_client):
        """Test refreshing statistics successfully."""
        mock_client.return_value.refresh_review_statistics.return_value = {
            "total_records": 10,
            "oldest_timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "newest_timestamp": datetime(2025, 1, 15, tzinfo=timezone.utc),
            "is_incremental": True,
        }
        response = self.client.post(reverse("api_statistics_refresh", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_records"], 10)
        self.assertEqual(data["is_incremental"], True)

    @mock.patch("reviews.views.logger")
    @mock.patch("reviews.views.WikiClient")
    def test_api_statistics_refresh_failure(self, mock_client, mock_logger):
        """Test statistics refresh error handling."""
        mock_client.return_value.refresh_review_statistics.side_effect = RuntimeError(
            "Network error"
        )
        response = self.client.post(reverse("api_statistics_refresh", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())


class StatisticsServiceTests(TestCase):
    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    @mock.patch("review_statistics.services.SupersetQuery")
    def test_fetch_review_statistics(self, mock_superset):
        """Test fetching review statistics from Superset."""
        from reviews.services import WikiClient

        mock_superset.return_value.query.return_value = [
            {
                "log_id": 12345,
                "reviewer_name": "Reviewer1",
                "reviewed_user_name": "User1",
                "page_title": "Test_Page",
                "page_id": 123,
                "reviewed_revision_id": 456,
                "pending_revision_id": 455,
                "reviewed_timestamp": "20250115120000",
                "pending_timestamp": "20250110120000",
                "review_delay_days": 5,
            }
        ]

        client = WikiClient(self.wiki)
        result = client.fetch_review_statistics(days=1)

        self.assertEqual(result["total_records"], 1)
        self.assertIsNotNone(result["oldest_timestamp"])
        self.assertIsNotNone(result["newest_timestamp"])
        self.assertIn("batches_fetched", result)

        # Check that cache was created
        cached = ReviewStatisticsCache.objects.filter(wiki=self.wiki)
        self.assertEqual(cached.count(), 1)
        self.assertEqual(cached.first().reviewer_name, "Reviewer1")
        self.assertEqual(cached.first().reviewed_revision_id, 456)
        self.assertEqual(cached.first().pending_revision_id, 455)

        # Check that metadata was created
        metadata = ReviewStatisticsMetadata.objects.get(wiki=self.wiki)
        self.assertEqual(metadata.total_records, 1)

    @mock.patch("review_statistics.services.SupersetQuery")
    def test_fetch_review_statistics_with_invalid_timestamp(self, mock_superset):
        """Test handling of invalid timestamps in statistics."""
        from reviews.services import WikiClient

        mock_superset.return_value.query.return_value = [
            {
                "log_id": 12345,
                "reviewer_name": "Reviewer1",
                "reviewed_user_name": "User1",
                "page_title": "Test_Page",
                "page_id": 123,
                "reviewed_revision_id": 456,
                "pending_revision_id": 455,
                "reviewed_timestamp": None,
                "pending_timestamp": "20250110120000",
                "review_delay_days": 5,
            }
        ]

        client = WikiClient(self.wiki)
        result = client.fetch_review_statistics(days=1)

        # Should handle invalid timestamps gracefully
        self.assertEqual(result["total_records"], 0)


class StatisticsFilteringTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

        # Create some test data
        from reviews.models import EditorProfile

        # Create auto-reviewer profile
        EditorProfile.objects.create(
            wiki=self.wiki,
            username="AutoUser",
            usergroups=["autoreview"],
            is_autoreviewed=True,
        )

        # Create statistics entries
        base_time = datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
        ReviewStatisticsCache.objects.create(
            wiki=self.wiki,
            reviewer_name="Reviewer1",
            reviewed_user_name="AutoUser",
            page_title="Page1",
            page_id=1,
            reviewed_revision_id=10,
            pending_revision_id=9,
            reviewed_timestamp=base_time,
            pending_timestamp=base_time - timedelta(days=2),
            review_delay_days=2,
        )
        ReviewStatisticsCache.objects.create(
            wiki=self.wiki,
            reviewer_name="Reviewer1",
            reviewed_user_name="RegularUser",
            page_title="Page2",
            page_id=2,
            reviewed_revision_id=20,
            pending_revision_id=19,
            reviewed_timestamp=base_time + timedelta(days=1),
            pending_timestamp=base_time - timedelta(days=1),
            review_delay_days=2,
        )

    def test_exclude_auto_reviewers_filter(self):
        """Test filtering out users with auto-review rights."""
        response = self.client.get(
            reverse("api_statistics", args=[self.wiki.pk]) + "?exclude_auto_reviewers=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should only show reviews of RegularUser
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["reviewed_user_name"], "RegularUser")

    def test_time_filter_day(self):
        """Test day time filter."""
        response = self.client.get(
            reverse("api_statistics", args=[self.wiki.pk]) + "?time_filter=day"
        )
        self.assertEqual(response.status_code, 200)
        # Results depend on test execution time, just check it doesn't error

    def test_chart_endpoint(self):
        """Test the chart data endpoint."""
        response = self.client.get(reverse("api_statistics_charts", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("reviewers_over_time", data)
        self.assertIn("pending_reviews_per_day", data)
        self.assertIn("average_delay_over_time", data)
        self.assertIn("delay_percentiles", data)
        self.assertIn("overall_stats", data)

        # Check overall stats structure
        self.assertIn("avg_delay", data["overall_stats"])
        self.assertIn("p10", data["overall_stats"])
        self.assertIn("p50", data["overall_stats"])
        self.assertIn("p90", data["overall_stats"])

    def test_chart_with_filters(self):
        """Test chart endpoint with filters."""
        response = self.client.get(
            reverse("api_statistics_charts", args=[self.wiki.pk]) + "?exclude_auto_reviewers=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should exclude AutoUser reviews
        self.assertEqual(data["overall_stats"]["total_reviews"], 1)

    def test_metadata_last_data_loaded_at(self):
        """Test that last_data_loaded_at is set when data is loaded."""
        from reviews.services import WikiClient

        # Create metadata without last_data_loaded_at
        metadata = ReviewStatisticsMetadata.objects.create(
            wiki=self.wiki,
            total_records=0,
        )
        self.assertIsNone(metadata.last_data_loaded_at)

        # Mock fetch to populate last_data_loaded_at
        with mock.patch("review_statistics.services.SupersetQuery") as mock_superset:
            mock_superset.return_value.query.return_value = [
                {
                    "log_id": 12345,
                    "reviewer_name": "Reviewer1",
                    "reviewed_user_name": "User1",
                    "page_title": "Test_Page",
                    "page_id": 123,
                    "reviewed_revision_id": 456,
                    "pending_revision_id": 455,
                    "reviewed_timestamp": "20250115120000",
                    "pending_timestamp": "20250110120000",
                    "review_delay_days": 5,
                }
            ]

            client = WikiClient(self.wiki)
            client.fetch_review_statistics(days=1)

        # Check that last_data_loaded_at is now set
        metadata.refresh_from_db()
        self.assertIsNotNone(metadata.last_data_loaded_at)

    def test_batch_limit_not_reached(self):
        """Test that batch_limit_reached is False for small datasets."""
        from reviews.services import WikiClient

        with mock.patch("review_statistics.services.SupersetQuery") as mock_superset:
            # First call returns data, second call returns empty (pagination stops)
            mock_superset.return_value.query.side_effect = [
                [
                    {
                        "log_id": 12345,
                        "reviewer_name": "Reviewer1",
                        "reviewed_user_name": "User1",
                        "page_title": "Test_Page",
                        "page_id": 123,
                        "reviewed_revision_id": 456,
                        "pending_revision_id": 455,
                        "reviewed_timestamp": "20250115120000",
                        "pending_timestamp": "20250110120000",
                        "review_delay_days": 5,
                    }
                ],
                [],  # Second call returns empty - stops pagination
            ]

            client = WikiClient(self.wiki)
            result = client.fetch_review_statistics(days=1)

        self.assertFalse(result["batch_limit_reached"])
        # Note: batches_fetched is 2 because pagination fetches once with data,
        # then fetches again (gets empty) to confirm no more data exists
        self.assertEqual(result["batches_fetched"], 2)


class FlaggedRevsStatisticsModelTests(TestCase):
    """Tests for FlaggedRevsStatistics model."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wikipedia",
            code="test",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

    def test_create_statistics(self):
        """Test creating statistics record."""
        stat = FlaggedRevsStatistics.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            total_pages_ns0=1000,
            synced_pages_ns0=800,
            reviewed_pages_ns0=900,
            pending_lag_average=2.5,
        )

        self.assertEqual(stat.wiki, self.wiki)
        self.assertEqual(stat.total_pages_ns0, 1000)
        self.assertEqual(stat.synced_pages_ns0, 800)
        self.assertEqual(stat.reviewed_pages_ns0, 900)
        self.assertEqual(stat.pending_lag_average, 2.5)

    def test_pending_changes_calculation(self):
        """Test that pending_changes is calculated automatically."""
        stat = FlaggedRevsStatistics.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            reviewed_pages_ns0=900,
            synced_pages_ns0=800,
        )

        # pending_changes should be reviewed - synced = 900 - 800 = 100
        self.assertEqual(stat.pending_changes, 100)

    def test_unique_together_constraint(self):
        """Test that wiki and date must be unique together."""
        from django.db import transaction
        from django.db.utils import IntegrityError

        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            total_pages_ns0=1000,
        )

        # Creating another record with same wiki and date should raise IntegrityError
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                FlaggedRevsStatistics.objects.create(
                    wiki=self.wiki,
                    date=date(2024, 1, 1),
                    total_pages_ns0=2000,
                )

        # Should only have one record
        self.assertEqual(FlaggedRevsStatistics.objects.count(), 1)


class ReviewActivityModelTests(TestCase):
    """Tests for ReviewActivity model."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wikipedia",
            code="test",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

    def test_create_review_activity(self):
        """Test creating review activity record."""
        activity = ReviewActivity.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            number_of_reviewers=10,
            number_of_reviews=50,
            number_of_pages=45,
        )

        self.assertEqual(activity.wiki, self.wiki)
        self.assertEqual(activity.number_of_reviewers, 10)
        self.assertEqual(activity.number_of_reviews, 50)
        self.assertEqual(activity.number_of_pages, 45)

    def test_reviews_per_reviewer_calculation(self):
        """Test that reviews_per_reviewer is calculated automatically."""
        activity = ReviewActivity.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            number_of_reviewers=10,
            number_of_reviews=50,
            number_of_pages=45,
        )

        # reviews_per_reviewer should be 50 / 10 = 5.0
        self.assertEqual(activity.reviews_per_reviewer, 5.0)

    def test_reviews_per_reviewer_zero_reviewers(self):
        """Test that reviews_per_reviewer handles zero reviewers."""
        activity = ReviewActivity.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            number_of_reviewers=0,
            number_of_reviews=50,
            number_of_pages=45,
        )

        # Should not crash, reviews_per_reviewer should be None
        self.assertIsNone(activity.reviews_per_reviewer)


class StatisticsAPITests(TestCase):
    """Tests for statistics API endpoints."""

    def setUp(self):
        self.wiki1 = Wiki.objects.create(
            name="Test Wikipedia 1",
            code="test1",
            api_endpoint="https://test1.wikipedia.org/w/api.php",
        )
        self.wiki2 = Wiki.objects.create(
            name="Test Wikipedia 2",
            code="test2",
            api_endpoint="https://test2.wikipedia.org/w/api.php",
        )

        # Create some test data
        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki1,
            date=date(2024, 1, 1),
            total_pages_ns0=1000,
            synced_pages_ns0=800,
            reviewed_pages_ns0=900,
            pending_lag_average=2.5,
        )
        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki2,
            date=date(2024, 1, 1),
            total_pages_ns0=2000,
            synced_pages_ns0=1800,
            reviewed_pages_ns0=1900,
            pending_lag_average=1.5,
        )

    def test_api_statistics_all_wikis(self):
        """Test API returns statistics for all wikis."""
        response = self.client.get(reverse("api_flaggedrevs_statistics"))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("data", data)
        self.assertEqual(len(data["data"]), 2)

    def test_api_statistics_single_wiki(self):
        """Test API filters by wiki."""
        response = self.client.get(reverse("api_flaggedrevs_statistics"), {"wiki": "test1"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["wiki"], "test1")
        self.assertEqual(data["data"][0]["totalPages_ns0"], 1000)

    def test_api_statistics_data_format(self):
        """Test API returns correct data format."""
        response = self.client.get(reverse("api_flaggedrevs_statistics"), {"wiki": "test1"})
        data = response.json()["data"][0]

        self.assertIn("wiki", data)
        self.assertIn("date", data)
        self.assertIn("totalPages_ns0", data)
        self.assertIn("syncedPages_ns0", data)
        self.assertIn("reviewedPages_ns0", data)
        self.assertIn("pendingLag_average", data)
        self.assertIn("pendingChanges", data)

    def test_api_statistics_date_filtering(self):
        """Test API filters by date range."""
        # Add more data for different dates
        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki1,
            date=date(2024, 2, 1),
            total_pages_ns0=1100,
        )
        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki1,
            date=date(2024, 3, 1),
            total_pages_ns0=1200,
        )

        # Filter for January only
        response = self.client.get(
            reverse("api_flaggedrevs_statistics"),
            {"wiki": "test1", "start_date": "2024-01-01", "end_date": "2024-01-31"},
        )
        data = response.json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["date"], "2024-01-01")


class ReviewActivityAPITests(TestCase):
    """Tests for review activity API endpoint."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wikipedia",
            code="test",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

        ReviewActivity.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            number_of_reviewers=10,
            number_of_reviews=50,
            number_of_pages=45,
        )

    def test_api_review_activity(self):
        """Test review activity API endpoint."""
        response = self.client.get(reverse("api_flaggedrevs_activity"))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("data", data)
        self.assertEqual(len(data["data"]), 1)

    def test_api_review_activity_data_format(self):
        """Test review activity API returns correct format."""
        response = self.client.get(reverse("api_flaggedrevs_activity"), {"wiki": "test"})
        data = response.json()["data"][0]

        self.assertIn("wiki", data)
        self.assertIn("date", data)
        self.assertIn("number_of_reviewers", data)
        self.assertIn("number_of_reviews", data)
        self.assertIn("number_of_pages", data)
        self.assertIn("reviews_per_reviewer", data)


class StatisticsPageTests(TestCase):
    """Tests for statistics page view."""

    def test_statistics_page_loads(self):
        """Test that statistics page loads successfully."""
        response = self.client.get(reverse("flaggedrevs_statistics_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FlaggedRevs Statistics")

    def test_statistics_page_includes_wikis(self):
        """Test that statistics page includes wiki data."""
        Wiki.objects.create(
            name="Test Wikipedia",
            code="test",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

        response = self.client.get(reverse("flaggedrevs_statistics_page"))
        self.assertContains(response, "test")


class LoadStatisticsCommandTests(TestCase):
    """Tests for load_statistics management command."""

    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wikipedia",
            code="test",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )

    @patch("review_statistics.management.commands.load_flaggedrevs_statistics.logger")
    @patch("review_statistics.management.commands.load_flaggedrevs_statistics.SupersetQuery")
    @patch("review_statistics.management.commands.load_flaggedrevs_statistics.pywikibot.Site")
    def test_load_statistics_command(self, mock_site, mock_superset_query, mock_logger):
        """Test load_statistics management command."""
        # Mock the Superset response with the correct aggregated format
        mock_superset = MagicMock()
        mock_superset.query.return_value = [
            {
                "yearmonth": 202401,  # Changed from "d" to "yearmonth"
                "totalPages_ns0_avg": 1000,  # Changed to _avg suffix
                "syncedPages_ns0_avg": 800,
                "reviewedPages_ns0_avg": 900,
                "pendingLag_average_avg": 2.5,
            }
        ]
        mock_superset_query.return_value = mock_superset

        out = StringIO()
        call_command("load_flaggedrevs_statistics", "--wiki", "test", stdout=out, stderr=StringIO())

        stats = FlaggedRevsStatistics.objects.filter(wiki=self.wiki)
        self.assertEqual(stats.count(), 1)

        stat = stats.first()
        self.assertEqual(stat.total_pages_ns0, 1000)
        self.assertEqual(stat.synced_pages_ns0, 800)
        self.assertEqual(stat.reviewed_pages_ns0, 900)
        self.assertEqual(stat.pending_lag_average, 2.5)
        self.assertEqual(stat.date, date(2024, 1, 1))

    @patch("review_statistics.management.commands.load_flaggedrevs_statistics.SupersetQuery")
    @patch("review_statistics.management.commands.load_flaggedrevs_statistics.pywikibot.Site")
    def test_load_statistics_clear_command(self, mock_site, mock_superset_query):
        """Test load_statistics --clear command."""
        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki,
            date=date(2024, 1, 1),
            total_pages_ns0=1000,
        )

        call_command("load_flaggedrevs_statistics", "--clear", stdout=StringIO(), stderr=StringIO())

        self.assertEqual(FlaggedRevsStatistics.objects.count(), 0)


class StatisticsAPIIntegrationTests(TestCase):
    """Integration tests for statistics API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.wiki1 = Wiki.objects.create(
            name="Finnish Wikipedia",
            code="fi",
            api_endpoint="https://fi.wikipedia.org/w/api.php",
        )
        self.wiki2 = Wiki.objects.create(
            name="German Wikipedia",
            code="de",
            api_endpoint="https://de.wikipedia.org/w/api.php",
        )

        # Create statistics data
        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki1,
            date=date(2024, 1, 1),
            total_pages_ns0=1000,
            synced_pages_ns0=800,
            reviewed_pages_ns0=900,
            pending_lag_average=2.5,
        )
        FlaggedRevsStatistics.objects.create(
            wiki=self.wiki2,
            date=date(2024, 1, 1),
            total_pages_ns0=2000,
            synced_pages_ns0=1800,
            reviewed_pages_ns0=1900,
            pending_lag_average=1.5,
        )

        # Create review activity data
        ReviewActivity.objects.create(
            wiki=self.wiki1,
            date=date(2024, 1, 1),
            number_of_reviewers=10,
            number_of_reviews=50,
            number_of_pages=45,
        )
        ReviewActivity.objects.create(
            wiki=self.wiki2,
            date=date(2024, 1, 1),
            number_of_reviewers=15,
            number_of_reviews=75,
            number_of_pages=70,
        )

    def test_api_statistics_with_specific_wiki(self):
        """Test API filters by specific wiki code."""
        response = self.client.get(reverse("api_flaggedrevs_statistics"), {"wiki": "fi"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["wiki"], "fi")
        self.assertEqual(data["data"][0]["totalPages_ns0"], 1000)

    def test_api_statistics_month_filtering(self):
        """Test API filtering by month (YYYYMM format)."""
        response = self.client.get(reverse("api_flaggedrevs_statistics"), {"month": "202401"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should return data for the specific month
        self.assertEqual(len(data["data"]), 2)

        # All data should be from January 2024
        for item in data["data"]:
            self.assertEqual(item["date"], "2024-01-01")

    def test_api_review_activity_with_specific_wiki(self):
        """Test review activity API with specific wiki code."""
        response = self.client.get(reverse("api_flaggedrevs_activity"), {"wiki": "fi"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["wiki"], "fi")
        self.assertEqual(data["data"][0]["number_of_reviewers"], 10)

    def test_data_consistency_across_apis(self):
        """Test that data is consistent between statistics and review activity APIs."""
        # Get statistics data
        stats_response = self.client.get(reverse("api_flaggedrevs_statistics"))
        stats_data = stats_response.json()["data"]

        # Get review activity data
        activity_response = self.client.get(reverse("api_flaggedrevs_activity"))
        activity_data = activity_response.json()["data"]

        # Both should have the same wikis
        stats_wikis = set(item["wiki"] for item in stats_data)
        activity_wikis = set(item["wiki"] for item in activity_data)

        self.assertEqual(stats_wikis, activity_wikis)
