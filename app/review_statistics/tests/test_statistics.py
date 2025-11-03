from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse
from review_statistics.models import (
    ReviewStatisticsCache,
    ReviewStatisticsMetadata,
)
from reviews.models import Wiki, WikiConfiguration


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

    @mock.patch("review_statistics.views.WikiClient")
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

    @mock.patch("review_statistics.views.logger")
    @mock.patch("review_statistics.views.WikiClient")
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
