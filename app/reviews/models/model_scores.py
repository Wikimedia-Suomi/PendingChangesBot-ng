from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ModelScores(models.Model):
    """Caches ML model scores for revisions to avoid repeated API calls."""

    revision = models.OneToOneField(
        "reviews.PendingRevision", on_delete=models.CASCADE, related_name="model_scores"
    )

    # ORES scores (legacy)
    ores_damaging_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="ORES damaging probability (0.0-1.0, higher = more likely damaging)",
    )
    ores_goodfaith_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="ORES goodfaith probability (0.0-1.0, higher = more likely good faith)",
    )
    ores_fetched_at = models.DateTimeField(
        null=True, blank=True, help_text="When ORES scores were fetched from the API"
    )

    # Lift Wing ML model scores (float-based models)
    lw_revertrisk_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Lift Wing language-agnostic revert risk probability (0.0-1.0)",
    )
    lw_revertrisk_language_agnostic_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Lift Wing language-agnostic revert risk probability (0.0-1.0)",
    )
    lw_revertrisk_multilingual_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Lift Wing multilingual revert risk probability (0.0-1.0)",
    )
    lw_damaging_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Lift Wing damaging probability (0.0-1.0)",
    )
    lw_goodfaith_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Lift Wing goodfaith probability (0.0-1.0)",
    )
    lw_fetched_at = models.DateTimeField(
        null=True, blank=True, help_text="When Lift Wing scores were fetched from the API"
    )

    # Note: articlequality and articletopic return JSON/strings, not cached here

    class Meta:
        verbose_name = "Model Scores"
        verbose_name_plural = "Model Scores"

    def __str__(self) -> str:
        return f"Scores for {self.revision}"
