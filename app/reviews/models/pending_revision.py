from __future__ import annotations

import logging
import os

import pywikibot
from django.db import models

logger = logging.getLogger(__name__)

os.environ.setdefault("PYWIKIBOT2_NO_USER_CONFIG", "1")
os.environ.setdefault("PYWIKIBOT_NO_USER_CONFIG", "2")


class PendingRevision(models.Model):
    """Revision data cached from the wiki API."""

    page = models.ForeignKey(
        "reviews.PendingPage", on_delete=models.CASCADE, related_name="revisions"
    )
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

    def __str__(self) -> str:
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
        from ..services import parse_categories

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
        except Exception:
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

    def get_rendered_html(self, force: bool = False) -> str:
        """
        Get the rendered HTML for this revision.
        Args:
            force: If True, force refresh from API even if cached.
        """
        # Use cached version if available and not forcing refresh
        if not force and self.rendered_html:
            return self.rendered_html

        # Fetch from API
        site = pywikibot.Site(
            code=self.page.wiki.code,
            fam=self.page.wiki.family,
        )
        request = site.simple_request(
            action="parse",
            oldid=str(self.revid),
            prop="text",
            formatversion=2,
        )
        try:
            response = request.submit()
        except Exception:
            logger.exception("Failed to fetch rendered HTML for revision %s", self.revid)
            return ""

        parse_result = response.get("parse", {})
        html_text = parse_result.get("text", "")
        rendered = html_text if isinstance(html_text, str) else ""

        # Save to database if we fetched new content
        if rendered and rendered != self.rendered_html:
            self.rendered_html = rendered
            self.save(update_fields=["rendered_html"])

        return rendered
