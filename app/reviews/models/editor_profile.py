from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.utils import timezone


class EditorProfile(models.Model):
    """Caches information about editors to avoid repeated API calls."""

    wiki = models.ForeignKey(
        "reviews.Wiki", on_delete=models.CASCADE, related_name="editor_profiles"
    )
    username = models.CharField(max_length=255)
    usergroups = models.JSONField(default=list, blank=True)
    is_blocked = models.BooleanField(default=False)
    is_bot = models.BooleanField(default=False)
    is_former_bot = models.BooleanField(default=False)
    is_autopatrolled = models.BooleanField(default=False)
    is_autoreviewed = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("wiki", "username")
        ordering = ["username"]

    @property
    def is_expired(self) -> bool:
        return self.fetched_at < timezone.now() - timedelta(minutes=120)

    def __str__(self) -> str:
        return f"{self.username} on {self.wiki.code}"
