from __future__ import annotations

from datetime import date
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from reviews.models.flaggedrevs_statistics import FlaggedRevsStatistics, ReviewActivity
from reviews.models.wiki import Wiki


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

    @patch("reviews.management.commands.load_flaggedrevs_statistics.logger")
    @patch("reviews.management.commands.load_flaggedrevs_statistics.SupersetQuery")
    @patch("reviews.management.commands.load_flaggedrevs_statistics.pywikibot.Site")
    def test_load_statistics_command(self, mock_site, mock_superset_query, mock_logger):
        """Test load_statistics management command."""
        # Mock the Superset response
        mock_superset = MagicMock()
        mock_superset.query.return_value = [
            {
                "yearmonth": "202401",
                "totalPages_ns0_avg": 1000,
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

    @patch("reviews.management.commands.load_flaggedrevs_statistics.SupersetQuery")
    @patch("reviews.management.commands.load_flaggedrevs_statistics.pywikibot.Site")
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
