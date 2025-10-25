from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import pywikibot

if TYPE_CHECKING:
    from reviews.models import Wiki

logger = logging.getLogger(__name__)


def get_redirect_aliases(wiki: Wiki) -> list[str]:
    """Get and cache redirect aliases for a wiki."""
    config = wiki.configuration
    if config.redirect_aliases:
        return config.redirect_aliases

    try:
        site = pywikibot.Site(code=wiki.code, fam=wiki.family)
        request = site.simple_request(
            action="query",
            meta="siteinfo",
            siprop="magicwords",
            formatversion=2,
        )
        response = request.submit()

        magic_words = response.get("query", {}).get("magicwords", [])
        for magic_word in magic_words:
            if magic_word.get("name") == "redirect":
                aliases = magic_word.get("aliases", [])
                config.redirect_aliases = aliases
                config.save(update_fields=["redirect_aliases", "updated_at"])
                return aliases
    except Exception:
        logger.exception("Failed to fetch redirect magic words for %s", wiki.code)

    language_fallbacks = {
        "de": ["#WEITERLEITUNG", "#REDIRECT"],
        "en": ["#REDIRECT"],
        "pl": ["#PATRZ", "#PRZEKIERUJ", "#TAM", "#REDIRECT"],
        "fi": ["#OHJAUS", "#UUDELLEENOHJAUS", "#REDIRECT"],
    }

    return language_fallbacks.get(wiki.code, ["#REDIRECT"])


def is_redirect(wikitext: str, redirect_aliases: list[str]) -> bool:
    """Check if wikitext represents a redirect page."""
    if not wikitext or not redirect_aliases:
        return False

    patterns = [
        re.escape(alias.lstrip("#").strip())
        for alias in redirect_aliases
        if alias.lstrip("#").strip()
    ]
    if not patterns:
        return False

    redirect_pattern = r"^#[ \t]*(" + "|".join(patterns) + r")[ \t]*\[\[([^\]\n\r]+?)\]\]"
    return bool(re.match(redirect_pattern, wikitext, re.IGNORECASE))
