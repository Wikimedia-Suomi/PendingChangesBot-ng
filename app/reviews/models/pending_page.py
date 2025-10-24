from __future__ import annotations

from django.db import models


class PendingPage(models.Model):
    """Represents a page that currently has pending changes."""

    wiki = models.ForeignKey("reviews.Wiki", on_delete=models.CASCADE, related_name="pending_pages")
    pageid = models.BigIntegerField()
    title = models.CharField(max_length=500)
    stable_revid = models.BigIntegerField()
    pending_since = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)
    categories = models.JSONField(default=list, blank=True)
    wikidata_id = models.CharField(max_length=16, blank=True, null=True)

    class Meta:
        unique_together = ("wiki", "pageid")
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title
