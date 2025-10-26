from __future__ import annotations

from django.db import models


class WordAnnotation(models.Model):
    """Store word/token level annotations for tracking authorship across revisions."""

    page = models.ForeignKey(
        "reviews.PendingPage", on_delete=models.CASCADE, related_name="word_annotations"
    )
    revision_id = models.BigIntegerField(db_index=True)
    stable_word_id = models.CharField(max_length=100, db_index=True)
    word = models.CharField(max_length=500)
    author_user_name = models.CharField(max_length=255, blank=True)
    author_user_id = models.BigIntegerField(null=True, blank=True)
    previous_word_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    position = models.IntegerField()
    is_moved = models.BooleanField(default=False)
    is_modified = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    exists_in_latest = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("page", "revision_id", "stable_word_id", "position")
        ordering = ["revision_id", "position"]
        indexes = [
            models.Index(fields=["page", "revision_id"]),
            models.Index(fields=["stable_word_id"]),
            models.Index(fields=["author_user_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.page.title}#{self.revision_id}:{self.stable_word_id}"


class RevisionAnnotation(models.Model):
    """Store annotation metadata for revisions."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("error", "Error"),
    ]

    page = models.ForeignKey(
        "reviews.PendingPage", on_delete=models.CASCADE, related_name="revision_annotations"
    )
    revision_id = models.BigIntegerField()
    start_revision_id = models.BigIntegerField(null=True, blank=True)
    end_revision_id = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    words_annotated = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("page", "revision_id")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.page.title}#{self.revision_id} ({self.status})"
