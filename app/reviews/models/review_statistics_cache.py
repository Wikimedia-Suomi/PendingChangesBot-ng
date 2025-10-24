from __future__ import annotations

from django.db import models

from .wiki import Wiki


class ReviewStatisticsCache(models.Model):
    """Caches raw review statistics data from MediaWiki database."""

    wiki = models.ForeignKey(Wiki, on_delete=models.CASCADE, related_name="review_statistics")
    reviewer_name = models.CharField(max_length=255)
    reviewed_user_name = models.CharField(max_length=255)
    page_title = models.CharField(max_length=500)
    page_id = models.BigIntegerField()
    reviewed_revision_id = models.BigIntegerField()
    pending_revision_id = models.BigIntegerField()
    reviewed_timestamp = models.DateTimeField()
    pending_timestamp = models.DateTimeField()
    review_delay_days = models.IntegerField(help_text="Review delay in days")
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("wiki", "reviewed_revision_id")
        ordering = ["-reviewed_timestamp"]
        indexes = [
            models.Index(fields=["wiki", "reviewer_name"]),
            models.Index(fields=["wiki", "reviewed_user_name"]),
            models.Index(fields=["wiki", "reviewed_timestamp"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.wiki.code} - {self.reviewer_name} reviewed {self.reviewed_user_name}"
