from __future__ import annotations

from django.db import models

from .wiki import Wiki


class ReviewStatisticsMetadata(models.Model):
    """Tracks metadata about statistics cache (last refresh, row count, etc.)."""

    wiki = models.OneToOneField(Wiki, on_delete=models.CASCADE, related_name="statistics_metadata")
    last_refreshed_at = models.DateTimeField(auto_now=True)
    total_records = models.IntegerField(default=0)
    oldest_review_timestamp = models.DateTimeField(null=True, blank=True)
    newest_review_timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Review statistics metadata"

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Statistics metadata for {self.wiki.code}"
