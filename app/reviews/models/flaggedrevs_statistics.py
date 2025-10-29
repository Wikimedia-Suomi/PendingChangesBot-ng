from __future__ import annotations

from django.db import models

from .wiki import Wiki


class FlaggedRevsStatistics(models.Model):
    """Cached statistics data from Superset for flaggedrevs analysis."""

    wiki = models.ForeignKey(Wiki, on_delete=models.CASCADE, related_name="flaggedrevs_statistics")
    date = models.DateField(help_text="Date of the statistics (monthly resolution)")
    total_pages_ns0 = models.IntegerField(
        null=True, blank=True, help_text="Total articles in main namespace"
    )
    synced_pages_ns0 = models.IntegerField(
        null=True, blank=True, help_text="Articles reviewed to current revision"
    )
    reviewed_pages_ns0 = models.IntegerField(
        null=True, blank=True, help_text="Articles with at least one reviewed revision"
    )
    pending_lag_average = models.FloatField(
        null=True, blank=True, help_text="Average time articles wait for review"
    )
    pending_changes = models.IntegerField(
        null=True, blank=True, help_text="Calculated as reviewedPages_ns0 - syncedPages_ns0"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("wiki", "date")
        ordering = ["-date"]
        verbose_name_plural = "FlaggedRevs Statistics"

    def save(self, *args, **kwargs):
        if self.reviewed_pages_ns0 is not None and self.synced_pages_ns0 is not None:
            self.pending_changes = self.reviewed_pages_ns0 - self.synced_pages_ns0
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.wiki.code} statistics for {self.date}"


class ReviewActivity(models.Model):
    """Cached review activity data from flaggedrevs table."""

    wiki = models.ForeignKey(Wiki, on_delete=models.CASCADE, related_name="review_activity")
    date = models.DateField(help_text="Date of the review activity")
    number_of_reviewers = models.IntegerField(help_text="Number of unique reviewers on this date")
    number_of_reviews = models.IntegerField(help_text="Total number of reviews on this date")
    number_of_pages = models.IntegerField(help_text="Number of pages reviewed on this date")
    reviews_per_reviewer = models.FloatField(
        null=True, blank=True, help_text="Average reviews per reviewer"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("wiki", "date")
        ordering = ["-date"]
        verbose_name_plural = "Review Activity"

    def save(self, *args, **kwargs):
        if self.number_of_reviewers > 0:
            self.reviews_per_reviewer = self.number_of_reviews / self.number_of_reviewers
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.wiki.code} activity for {self.date}"
