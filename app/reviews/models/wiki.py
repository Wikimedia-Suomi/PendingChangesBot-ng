from __future__ import annotations

from django.db import models


class Wiki(models.Model):
    """Represents a Wikimedia project whose pending changes are inspected."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    family = models.CharField(max_length=100, default="wikipedia")
    api_endpoint = models.URLField(
        help_text=("Full API endpoint, e.g. https://fi.wikipedia.org/w/api.php")
    )
    script_path = models.CharField(max_length=255, default="/w")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"
