from __future__ import annotations

import logging
import os
from datetime import timedelta

import pywikibot
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

os.environ.setdefault("PYWIKIBOT2_NO_USER_CONFIG", "1")
os.environ.setdefault("PYWIKIBOT_NO_USER_CONFIG", "2")


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

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.name} ({self.code})"


class WikiConfiguration(models.Model):
    """Stores per-wiki rules that influence automatic approvals."""

    wiki = models.OneToOneField(Wiki, on_delete=models.CASCADE, related_name="configuration")
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
    # Lift Wing ML Model Configuration
    ml_model_type = models.CharField(
        max_length=50,
        default='revertrisk_language_agnostic',
        choices=[
            ('revertrisk_language_agnostic', 'Revert Risk (language-agnostic, 250+ languages)'),
            ('revertrisk_multilingual', 'Revert Risk (multilingual, 47 languages, higher accuracy)'),
            ('damaging', 'Damaging Edit Detection (47 languages)'),
            ('goodfaith', 'Good Faith Prediction (47 languages)'),
            ('articlequality', 'Article Quality Assessment (wiki-specific)'),
            ('articletopic', 'Article Topic Classification (wiki-specific)'),
        ],
        help_text="Which Wikimedia Lift Wing ML model to use for this wiki. Check compatibility with your wiki language!"
    )

    ml_model_threshold = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=(
            "Threshold for Lift Wing ML model score (0.0-1.0). "
            "Edits with a score above this threshold will not be auto-approved. "
            "Set to 0.0 to disable Lift Wing ML model checking."
        ),
    )

    # Deprecated: Legacy field for backward compatibility
    revertrisk_threshold = models.FloatField(
        default=0.0,
        help_text=(
            "DEPRECATED: Use ml_model_threshold instead. "
            "Threshold for revertrisk score (0.0-1.0). "
            "Edits with a score above this threshold will not be auto-approved. "
            "Set to 0.0 to disable revertrisk checking."
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
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Configuration for {self.wiki.code}"


class PendingPage(models.Model):
    """Represents a page that currently has pending changes."""

    wiki = models.ForeignKey(Wiki, on_delete=models.CASCADE, related_name="pending_pages")
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

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return self.title


class PendingRevision(models.Model):
    """Revision data cached from the wiki API."""

    page = models.ForeignKey(PendingPage, on_delete=models.CASCADE, related_name="revisions")
    revid = models.BigIntegerField()
    parentid = models.BigIntegerField(null=True, blank=True)
    user_name = models.CharField(max_length=255, blank=True)
    user_id = models.BigIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    age_at_fetch = models.DurationField()
    sha1 = models.CharField(max_length=40)
    comment = models.TextField(blank=True)
    change_tags = models.JSONField(default=list, blank=True)
    wikitext = models.TextField()
    rendered_html = models.TextField(blank=True)
    render_error_count = models.IntegerField(null=True, blank=True)
    categories = models.JSONField(default=list, blank=True)
    superset_data = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("page", "revid")
        ordering = ["timestamp"]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.page.title}#{self.revid}"

    def get_wikitext(self) -> str:
        """Return the revision wikitext, fetching it via the API when missing."""

        if self.wikitext:
            return self.wikitext

        wikitext = self._fetch_wikitext_from_api()
        if wikitext != self.wikitext:
            self.wikitext = wikitext
            self.save(update_fields=["wikitext"])
        return self.wikitext or ""

    def get_categories(self) -> list[str]:
        """Return and cache the categories for the revision."""

        cached_categories = list(self.categories or [])
        if cached_categories:
            return cached_categories

        wikitext = self.get_wikitext()
        from .services import parse_categories

        categories = parse_categories(wikitext)
        if categories != (self.categories or []):
            self.categories = categories
            self.save(update_fields=["categories"])
        return categories

    def _fetch_wikitext_from_api(self) -> str:
        """Fetch the revision wikitext directly from the wiki API."""

        site = pywikibot.Site(
            code=self.page.wiki.code,
            fam=self.page.wiki.family,
        )
        request = site.simple_request(
            action="query",
            prop="revisions",
            revids=str(self.revid),
            rvprop="content",
            rvslots="main",
            formatversion=2,
        )
        try:
            response = request.submit()
        except Exception:  # pragma: no cover - network failure fallback
            logger.exception("Failed to fetch wikitext for revision %s", self.revid)
            return self.wikitext or ""

        pages = response.get("query", {}).get("pages", [])
        for page in pages:
            for revision in page.get("revisions", []) or []:
                slots = revision.get("slots", {}) or {}
                main = slots.get("main", {}) or {}
                content = main.get("content")
                if content is not None:
                    return str(content)
        return ""


class ModelScores(models.Model):
    """Caches ML model scores for revisions to avoid repeated API calls."""

    revision = models.OneToOneField(
        PendingRevision, on_delete=models.CASCADE, related_name="model_scores"
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

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Scores for {self.revision}"


class EditorProfile(models.Model):
    """Caches information about editors to avoid repeated API calls."""

    wiki = models.ForeignKey(Wiki, on_delete=models.CASCADE, related_name="editor_profiles")
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

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.username} on {self.wiki.code}"
