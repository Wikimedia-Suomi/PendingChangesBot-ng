"""Utilities for detecting broken wikicode indicators in rendered HTML."""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from reviews.models import PendingRevision

logger = logging.getLogger(__name__)


def get_visible_text(html_content: str) -> str:
    """
    Extract only visible text from HTML, excluding code blocks, pre tags, and script/style content.

    This helps avoid false positives from legitimate code examples or technical documentation.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "lxml")

    # Remove script, style, code, pre, and tt tags (they contain legitimate syntax examples)
    for tag in soup.find_all(["script", "style", "code", "pre", "tt", "syntaxhighlight"]):
        tag.decompose()

    # Get visible text
    visible_text = soup.get_text()
    return visible_text


def detect_broken_wikicode_indicators(html_content: str, wiki_lang: str = "en") -> Counter:
    """
    Detect broken wikicode indicators in rendered HTML content.

    Returns a Counter with counts of each indicator type found.
    Only checks visible text to avoid false positives from code examples.
    """
    if not html_content:
        return Counter()

    # Extract only visible text (excluding code blocks, pre tags, etc.)
    visible_text = get_visible_text(html_content)

    indicators: Counter[str] = Counter()

    # Template syntax
    indicators["{{"] = visible_text.count("{{")
    indicators["}}"] = visible_text.count("}}")

    # Internal link syntax
    indicators["[["] = visible_text.count("[[")
    indicators["]]"] = visible_text.count("]]")

    # Reference tags (case insensitive) - only in visible text
    indicators["<ref"] = len(re.findall(r"<ref\b", visible_text, re.IGNORECASE))
    indicators["</ref"] = len(re.findall(r"</ref>", visible_text, re.IGNORECASE))
    indicators["ref>"] = len(re.findall(r"\bref>", visible_text, re.IGNORECASE))

    # Div tags
    indicators["<div"] = len(re.findall(r"<div\b", visible_text, re.IGNORECASE))
    indicators["</div"] = len(re.findall(r"</div>", visible_text, re.IGNORECASE))
    indicators["div>"] = len(re.findall(r"\bdiv>", visible_text, re.IGNORECASE))

    # Span tags
    indicators["<span"] = len(re.findall(r"<span\b", visible_text, re.IGNORECASE))
    indicators["</span"] = len(re.findall(r"</span>", visible_text, re.IGNORECASE))
    indicators["span>"] = len(re.findall(r"\bspan>", visible_text, re.IGNORECASE))

    # Media/category syntax with localization
    media_keywords = get_localized_media_keywords(wiki_lang)
    for keyword in media_keywords:
        pattern = re.escape(f"[{keyword}:")
        indicators[f"[{keyword}:"] = len(re.findall(pattern, visible_text, re.IGNORECASE))

    # Section headers (==) - check if article might be math-related
    # Only count if not in a math context
    if not is_math_article(html_content):
        indicators["=="] = visible_text.count("==")

    return indicators


def get_localized_media_keywords(wiki_lang: str) -> list[str]:
    """
    Get localized keywords for File/Image/Category in different languages.

    Returns a list of keywords to check for broken media/category syntax.
    """
    # Mapping of language codes to their File/Image/Category keywords
    keywords_map = {
        "en": ["File", "Image", "Category"],
        "de": ["Datei", "Bild", "Kategorie"],
        "fr": ["Fichier", "Image", "Catégorie"],
        "es": ["Archivo", "Imagen", "Categoría"],
        "it": ["File", "Immagine", "Categoria"],
        "pt": ["Ficheiro", "Imagem", "Categoria"],
        "pl": ["Plik", "Grafika", "Kategoria"],
        "ru": ["Файл", "Изображение", "Категория"],
        "ja": ["ファイル", "画像", "カテゴリ"],
        "zh": ["文件", "图像", "分类"],
        "hu": ["Fájl", "Kép", "Kategória"],  # Hungarian
        "nl": ["Bestand", "Afbeelding", "Categorie"],  # Dutch
        "sv": ["Fil", "Bild", "Kategori"],  # Swedish
        "fi": ["Tiedosto", "Kuva", "Luokka"],  # Finnish
        "no": ["Fil", "Bilde", "Kategori"],  # Norwegian
        "da": ["Fil", "Billede", "Kategori"],  # Danish
        "cs": ["Soubor", "Obrázek", "Kategorie"],  # Czech
        "tr": ["Dosya", "Resim", "Kategori"],  # Turkish
        "ar": ["ملف", "صورة", "تصنيف"],  # Arabic
        "ko": ["파일", "그림", "분류"],  # Korean
    }

    return keywords_map.get(wiki_lang, keywords_map["en"])


def is_math_article(html_content: str) -> bool:
    """
    Check if the article content suggests it's math-related.

    Math articles legitimately use == for equations, so we should skip
    checking for == as a broken wikicode indicator in those cases.
    """
    if not html_content:
        return False

    # Check for math-related patterns
    math_indicators = [
        r'class="[^"]*math[^"]*"',  # Math class in HTML
        r"<math",  # Math tags
        r"\\",  # LaTeX backslash
        r"\$",  # Dollar sign for inline math
    ]

    for pattern in math_indicators:
        if re.search(pattern, html_content, re.IGNORECASE):
            return True

    return False


def check_broken_wikicode(
    current_html: str, parent_html: str | None, wiki_lang: str = "en"
) -> tuple[bool, str]:
    """
    Check if the current revision introduces new broken wikicode.

    Compares current revision HTML with parent revision HTML to detect
    NEW broken wikicode indicators (not pre-existing ones).

    Only flags if multiple types of indicators are found OR if a single
    indicator appears multiple times (threshold >= 3 for single type).

    Args:
        current_html: Rendered HTML of the current revision
        parent_html: Rendered HTML of the parent revision (or None)
        wiki_lang: Language code for localized keyword detection

    Returns:
        Tuple of (has_broken_wikicode: bool, details: str)
    """
    current_indicators = detect_broken_wikicode_indicators(current_html, wiki_lang)

    # If we have a parent, compare to find NEW indicators
    if parent_html:
        parent_indicators = detect_broken_wikicode_indicators(parent_html, wiki_lang)
        # Only flag indicators that increased in count
        new_indicators = {
            key: count - parent_indicators.get(key, 0)
            for key, count in current_indicators.items()
            if count > parent_indicators.get(key, 0)
        }
    else:
        # No parent to compare with, all indicators are "new"
        new_indicators = dict(current_indicators)

    if not new_indicators or all(count == 0 for count in new_indicators.values()):
        return False, ""

    # Filter out noise: require either multiple indicator types OR significant count
    significant_indicators = {key: count for key, count in new_indicators.items() if count > 0}

    # Check if we have enough evidence of broken wikicode
    indicator_types = len(significant_indicators)
    total_count = sum(significant_indicators.values())

    # Threshold logic:
    # - Multiple different types (2+) = likely broken wikicode
    # - Single type but high count (3+) = likely broken wikicode
    # - Single type with low count (1-2) = likely false positive, ignore
    if indicator_types == 1 and total_count < 3:
        return False, ""

    # Build detailed message
    indicator_list = [
        f"{key}: {count}" for key, count in significant_indicators.items() if count > 0
    ]
    details = f"Introduced broken wikicode: {', '.join(indicator_list)}"

    return True, details


def get_parent_html(revision: PendingRevision) -> str:
    """Get parent revision rendered HTML from local database."""
    if not revision.parentid:
        return ""

    try:
        from reviews.models import PendingRevision as PR

        parent_revision = PR.objects.get(page=revision.page, revid=revision.parentid)
        return parent_revision.get_rendered_html()
    except PR.DoesNotExist:
        logger.debug(
            "Parent revision %s not found in local database for revision %s",
            revision.parentid,
            revision.revid,
        )
        return ""
