from __future__ import annotations

from datetime import timedelta
import logging
import os

from django.db import models
from django.utils import timezone

import pywikibot

logger = logging.getLogger(__name__)

os.environ.setdefault("PYWIKIBOT2_NO_USER_CONFIG", "1")
os.environ.setdefault("PYWIKIBOT_NO_USER_CONFIG", "2")


class Wiki(models.Model):
    """Represents a Wikimedia project whose pending changes are inspected."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    family = models.CharField(max_length=100, default="wikipedia")
    api_endpoint = models.URLField(
        help_text=(
            "Full API endpoint, e.g. https://fi.wikipedia.org/w/api.php"
        )
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
        )
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
