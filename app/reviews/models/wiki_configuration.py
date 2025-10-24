from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from reviews.autoreview.checks import AVAILABLE_CHECKS


def _get_default_enabled_checks():
    """Return all available check IDs as default."""
    return [check["id"] for check in AVAILABLE_CHECKS]


class WikiConfiguration(models.Model):
    """Stores per-wiki rules that influence automatic approvals."""

    wiki = models.OneToOneField(
        "reviews.Wiki", on_delete=models.CASCADE, related_name="configuration"
    )
    blocking_categories = models.JSONField(default=list, blank=True)
    auto_approved_groups = models.JSONField(default=list, blank=True)
    redirect_aliases = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Cached redirect magic word aliases from wiki API "
            "(i.e: https://fi.wikipedia.org/w/api.php?"
            "action=query&meta=siteinfo&siprop=magicwords)"
        ),
    )
    superseded_similarity_threshold = models.FloatField(
        default=0.2,
        help_text=(
            "Similarity threshold (0.0-1.0) for detecting superseded additions. "
            "Lower values are more strict. If text additions from a pending revision "
            "have similarity below this threshold in the current stable version, "
            "the revision is considered superseded and can be auto-approved."
        ),
    )
    ores_damaging_threshold = models.FloatField(
        null=True,
        blank=True,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=("Edits with damaging probability above this will not be auto-approved. "),
    )
    ores_goodfaith_threshold = models.FloatField(
        null=True,
        blank=True,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=("Edits with goodfaith probability below this will not be auto-approved. "),
    )
    ores_damaging_threshold_living = models.FloatField(
        null=True,
        blank=True,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=("ORES damaging threshold for living person biographies (stricter). "),
    )
    ores_goodfaith_threshold_living = models.FloatField(
        null=True,
        blank=True,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=("ORES goodfaith threshold for living person biographies (stricter). "),
    )
    enabled_checks = models.JSONField(
        default=_get_default_enabled_checks,
        blank=True,
        help_text="List of check IDs to run. All checks are enabled by default.",
    )
    # Test mode: use test_revision_ids instead of flaggedpages for testing
    test_mode = models.BooleanField(
        default=False,
        help_text=(
            "Enable test mode to use specific revision IDs "
            "instead of live flaggedpages data."
        ),
    )
    test_revision_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of revision IDs to use when test mode is enabled.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Configuration for {self.wiki.code}"
