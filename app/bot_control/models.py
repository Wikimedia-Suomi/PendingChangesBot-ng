from django.db import models
from django.utils import timezone


class BotStatus(models.Model):
    """Tracks the current state of the PendingChangesBot"""

    is_running = models.BooleanField(default=False)
    process_id = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "bot_status"
        verbose_name = "Bot Status"
        verbose_name_plural = "Bot Statuses"

    def __str__(self):
        status = "Running" if self.is_running else "Stopped"
        return f"Bot Status: {status}"

    @classmethod
    def get_current_status(cls):
        """Get or create the singleton status record"""
        status, created = cls.objects.get_or_create(pk=1)
        return status


class BotActivity(models.Model):
    """Tracks individual bot review activities"""

    DECISION_CHOICES = [
        ("approve", "Approved"),
        ("blocked", "Blocked"),
        ("manual", "Manual Review Required"),
    ]

    wiki_code = models.CharField(max_length=20)
    page_id = models.IntegerField()
    page_title = models.CharField(max_length=500)
    revision_id = models.IntegerField()
    user_name = models.CharField(max_length=255, blank=True)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    decision_label = models.CharField(max_length=100, blank=True)
    decision_reason = models.TextField(blank=True)
    determining_check = models.CharField(max_length=100, blank=True)
    total_checks_run = models.IntegerField(default=0)
    execution_time_ms = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    is_dry_run = models.BooleanField(default=True)

    class Meta:
        db_table = "bot_activity"
        verbose_name = "Bot Activity"
        verbose_name_plural = "Bot Activities"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["wiki_code", "-created_at"]),
            models.Index(fields=["decision"]),
        ]

    def __str__(self):
        return f"{self.wiki_code}: {self.page_title} - {self.decision}"

    @classmethod
    def log_activity(
        cls,
        wiki_code,
        page_id,
        page_title,
        revision_id,
        user_name,
        decision,
        decision_label="",
        decision_reason="",
        determining_check="",
        total_checks_run=0,
        execution_time_ms=None,
        is_dry_run=True,
    ):
        """Log a bot review activity"""
        return cls.objects.create(
            wiki_code=wiki_code,
            page_id=page_id,
            page_title=page_title,
            revision_id=revision_id,
            user_name=user_name,
            decision=decision,
            decision_label=decision_label,
            decision_reason=decision_reason,
            determining_check=determining_check,
            total_checks_run=total_checks_run,
            execution_time_ms=execution_time_ms,
            is_dry_run=is_dry_run,
        )


class AuditLog(models.Model):
    """Tracks all HTTP requests to the server for public transparency."""

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=2048)
    status_code = models.IntegerField()
    username = models.CharField(max_length=255, default="anonymous")
    role = models.CharField(max_length=20, default="public")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    query_params = models.TextField(blank=True)
    response_time_ms = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["method"]),
            models.Index(fields=["status_code"]),
            models.Index(fields=["username", "-timestamp"]),
        ]

    def __str__(self):
        return f"[{self.timestamp}] {self.method} {self.path} → {self.status_code}"
