"""Logic for simulating automatic review decisions for pending revisions."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .models import EditorProfile, PendingPage, PendingRevision

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoreviewDecision:
    """Represents the aggregated outcome for a revision."""

    status: str
    label: str
    reason: str


def run_autoreview_for_page(page: PendingPage) -> list[dict]:
    """Run the configured autoreview checks for each pending revision of a page."""

    revisions = list(
        page.revisions.exclude(revid=page.stable_revid)
        .order_by("timestamp", "revid")
    )  # Oldest revision first.
    usernames = {revision.user_name for revision in revisions if revision.user_name}
    profiles = {
        profile.username: profile
        for profile in EditorProfile.objects.filter(
            wiki=page.wiki, username__in=usernames
        )
    }
    configuration = page.wiki.configuration

    auto_groups = _normalize_to_lookup(configuration.auto_approved_groups)
    blocking_categories = _normalize_to_lookup(configuration.blocking_categories)

    # Get stable revision for comparison
    stable_revision = None
    try:
        stable_revision = page.revisions.get(revid=page.stable_revid)
    except page.revisions.model.DoesNotExist:
        logger.debug(
            "No stable revision %s for page %s",
            page.stable_revid,
            page.pageid,
        )

    results: list[dict] = []
    for i, revision in enumerate(revisions):
        profile = profiles.get(revision.user_name or "")
        # Get parent revision (either previous in list or stable revision)
        parent_revision = revisions[i - 1] if i > 0 else stable_revision

        revision_result = _evaluate_revision(
            revision,
            profile,
            parent_revision=parent_revision,
            auto_groups=auto_groups,
            blocking_categories=blocking_categories,
        )
        results.append(
            {
                "revid": revision.revid,
                "tests": revision_result["tests"],
                "decision": {
                    "status": revision_result["decision"].status,
                    "label": revision_result["decision"].label,
                    "reason": revision_result["decision"].reason,
                },
            }
        )

    return results


def _evaluate_revision(
    revision: PendingRevision,
    profile: EditorProfile | None,
    *,
    parent_revision: PendingRevision | None = None,
    auto_groups: dict[str, str],
    blocking_categories: dict[str, str],
) -> dict:
    tests: list[dict] = []

    # Test 0: Check for broken wikicode (non-blocking check)
    broken_wikicode_result = check_broken_wikicode(revision, parent_revision)
    tests.append(broken_wikicode_result)

    # If broken wikicode detected, still continue with other tests but may influence decision
    has_broken_wikicode = broken_wikicode_result["status"] == "fail"

    # Test 1: Bot editors can always be auto-approved.
    if _is_bot_user(revision, profile):
        tests.append(
            {
                "id": "bot-user",
                "title": "Bot user",
                "status": "ok",
                "message": "The edit could be auto-approved because the user is a bot.",
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The user is recognized as a bot.",
            ),
        }

    tests.append(
        {
            "id": "bot-user",
            "title": "Bot user",
            "status": "not_ok",
            "message": "The user is not marked as a bot.",
        }
    )

    # Test 2: Editors in the allow-list can be auto-approved.
    if auto_groups:
        matched_groups = _matched_user_groups(
            revision, profile, allowed_groups=auto_groups
        )
        if matched_groups:
            tests.append(
                {
                    "id": "auto-approved-group",
                    "title": "Auto-approved groups",
                    "status": "ok",
                    "message": "The user belongs to groups: {}.".format(
                        ", ".join(sorted(matched_groups))
                    ),
                }
            )
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="approve",
                    label="Would be auto-approved",
                    reason="The user belongs to groups that are auto-approved.",
                ),
            }

        tests.append(
            {
                "id": "auto-approved-group",
                "title": "Auto-approved groups",
                "status": "not_ok",
                "message": "The user does not belong to auto-approved groups.",
            }
        )
    else:
        if profile and (profile.is_autopatrolled or profile.is_autoreviewed):
            default_rights: list[str] = []
            if profile.is_autopatrolled:
                default_rights.append("Autopatrolled")
            if profile.is_autoreviewed:
                default_rights.append("Autoreviewed")

            tests.append(
                {
                    "id": "auto-approved-group",
                    "title": "Auto-approved groups",
                    "status": "ok",
                    "message": "The user has default auto-approval rights: {}.".format(
                        ", ".join(default_rights)
                    ),
                }
            )
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="approve",
                    label="Would be auto-approved",
                    reason="The user has default rights that allow auto-approval.",
                ),
            }

        tests.append(
            {
                "id": "auto-approved-group",
                "title": "Auto-approved groups",
                "status": "not_ok",
                "message": "The user does not have default auto-approval rights.",
            }
        )

    # Test 3: Blocking categories on the old version prevent automatic approval.
    blocking_hits = _blocking_category_hits(revision, blocking_categories)
    if blocking_hits:
        tests.append(
            {
                "id": "blocking-categories",
                "title": "Blocking categories",
                "status": "fail",
                "message": "The previous version belongs to blocking categories: {}.".format(
                    ", ".join(sorted(blocking_hits))
                ),
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="The previous version belongs to blocking categories.",
            ),
        }

    tests.append(
        {
            "id": "blocking-categories",
            "title": "Blocking categories",
            "status": "ok",
            "message": "The previous version is not in blocking categories.",
        }
    )

    # Final decision: Consider broken wikicode for manual review recommendation
    if has_broken_wikicode:
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="manual",
                label="Requires human review",
                reason="Broken wikicode detected - manual review recommended.",
            ),
        }

    return {
        "tests": tests,
        "decision": AutoreviewDecision(
            status="manual",
            label="Requires human review",
            reason="In dry-run mode the edit would not be approved automatically.",
        ),
    }


def _normalize_to_lookup(values: Iterable[str] | None) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not values:
        return lookup
    for value in values:
        if not value:
            continue
        normalized = str(value).casefold()
        if normalized:
            lookup[normalized] = str(value)
    return lookup


def _is_bot_user(revision: PendingRevision, profile: EditorProfile | None) -> bool:
    if profile and profile.is_bot:
        return True
    superset = revision.superset_data or {}
    if superset.get("rc_bot"):
        return True
    groups = superset.get("user_groups") or []
    for group in groups:
        if isinstance(group, str) and group.casefold() == "bot":
            return True
    return False


def _matched_user_groups(
    revision: PendingRevision,
    profile: EditorProfile | None,
    *,
    allowed_groups: dict[str, str],
) -> set[str]:
    if not allowed_groups:
        return set()

    groups: list[str] = []
    superset = revision.superset_data or {}
    superset_groups = superset.get("user_groups") or []
    if isinstance(superset_groups, list):
        groups.extend(str(group) for group in superset_groups if group)
    if profile and profile.usergroups:
        groups.extend(str(group) for group in profile.usergroups if group)

    matched: set[str] = set()
    for group in groups:
        normalized = group.casefold()
        if normalized in allowed_groups:
            matched.add(allowed_groups[normalized])
    return matched


def _blocking_category_hits(
    revision: PendingRevision, blocking_lookup: dict[str, str]
) -> set[str]:
    if not blocking_lookup:
        return set()

    categories = list(revision.get_categories())
    page_categories = revision.page.categories or []
    if isinstance(page_categories, list):
        categories.extend(str(category) for category in page_categories if category)

    matched: set[str] = set()
    for category in categories:
        normalized = str(category).casefold()
        if normalized in blocking_lookup:
            matched.add(blocking_lookup[normalized])
    return matched


def detect_broken_wikicode_indicators(html_content: str, wiki_lang: str = "en") -> Counter:
    """
    Detect broken wikicode indicators in rendered HTML content.

    Returns a Counter with counts of each indicator type found.
    """
    if not html_content:
        return Counter()

    indicators = Counter()

    # Template syntax
    indicators["{{"] = html_content.count("{{")
    indicators["}}"] = html_content.count("}}")

    # Internal link syntax
    indicators["[["] = html_content.count("[[")
    indicators["]]"] = html_content.count("]]")

    # Reference tags (case insensitive)
    indicators["<ref"] = len(re.findall(r'<ref\b', html_content, re.IGNORECASE))
    indicators["</ref"] = len(re.findall(r'</ref>', html_content, re.IGNORECASE))
    indicators["ref>"] = len(re.findall(r'\bref>', html_content, re.IGNORECASE))

    # Div tags
    indicators["<div"] = len(re.findall(r'<div\b', html_content, re.IGNORECASE))
    indicators["</div"] = len(re.findall(r'</div>', html_content, re.IGNORECASE))
    indicators["div>"] = len(re.findall(r'\bdiv>', html_content, re.IGNORECASE))

    # Span tags
    indicators["<span"] = len(re.findall(r'<span\b', html_content, re.IGNORECASE))
    indicators["</span"] = len(re.findall(r'</span>', html_content, re.IGNORECASE))
    indicators["span>"] = len(re.findall(r'\bspan>', html_content, re.IGNORECASE))

    # Media/category syntax with localization
    media_keywords = get_localized_media_keywords(wiki_lang)
    for keyword in media_keywords:
        pattern = re.escape(f"[{keyword}:")
        indicators[f"[{keyword}:"] = len(re.findall(pattern, html_content, re.IGNORECASE))

    # Section headers (==) - check if article might be math-related
    # Only count if not in a math context
    if not is_math_article(html_content):
        indicators["=="] = html_content.count("==")

    return indicators


def get_localized_media_keywords(wiki_lang: str) -> list[str]:
    """
    Get localized keywords for File, Image, and Category based on wiki language.

    Similar to how #REDIRECT magic words are translated.
    """
    # Base English keywords
    keywords = ["File", "Image", "Category"]

    # Add localized versions based on language
    localizations = {
        "fi": ["Tiedosto", "Kuva", "Luokka"],
        "de": ["Datei", "Bild", "Kategorie"],
        "pl": ["Plik", "Grafika", "Kategoria"],
        "fr": ["Fichier", "Image", "Catégorie"],
        "es": ["Archivo", "Imagen", "Categoría"],
        "sv": ["Fil", "Bild", "Kategori"],
        "it": ["File", "Immagine", "Categoria"],
        "nl": ["Bestand", "Afbeelding", "Categorie"],
        "ru": ["Файл", "Изображение", "Категория"],
        "ja": ["ファイル", "画像", "カテゴリ"],
    }

    if wiki_lang in localizations:
        keywords.extend(localizations[wiki_lang])

    return keywords


def is_math_article(html_content: str) -> bool:
    """
    Check if article appears to be math-related to avoid false positives with ==.

    Uses multiple heuristics:
    - Presence of <math> tags in content
    - Mathematical notation patterns
    """
    if not html_content:
        return False

    # Check for math tags
    if "<math" in html_content.lower():
        return True

    # Check for common mathematical notation
    math_patterns = [
        r'\$.*\$',  # LaTeX-style inline math
        r'\\[a-zA-Z]+\{',  # LaTeX commands
        r'[∑∏∫∂∇]',  # Mathematical symbols
    ]

    for pattern in math_patterns:
        if re.search(pattern, html_content):
            return True

    return False


def check_broken_wikicode(
    current_revision: PendingRevision,
    parent_revision: PendingRevision | None
) -> dict:
    """
    Check if a revision introduces new broken wikicode indicators.

    Compares indicator counts between parent and current revision.
    Returns a test result dict.
    """
    wiki_lang = current_revision.page.wiki.code

    # Get rendered HTML for both revisions
    current_html = current_revision.get_rendered_html()
    current_indicators = detect_broken_wikicode_indicators(current_html, wiki_lang)

    if not parent_revision:
        # No parent to compare against
        total_indicators = sum(current_indicators.values())
        if total_indicators > 0:
            return {
                "id": "broken-wikicode",
                "title": "Broken wikicode check",
                "status": "warning",
                "message": f"Found {total_indicators} wikicode indicator(s) but no parent revision to compare.",
            }
        return {
            "id": "broken-wikicode",
            "title": "Broken wikicode check",
            "status": "ok",
            "message": "No broken wikicode indicators detected.",
        }

    parent_html = parent_revision.get_rendered_html()
    parent_indicators = detect_broken_wikicode_indicators(parent_html, wiki_lang)

    # Find indicators that increased
    increased_indicators = []
    for indicator, current_count in current_indicators.items():
        parent_count = parent_indicators.get(indicator, 0)
        if current_count > parent_count:
            increase = current_count - parent_count
            increased_indicators.append(f"{indicator} (+{increase})")

    if increased_indicators:
        return {
            "id": "broken-wikicode",
            "title": "Broken wikicode check",
            "status": "fail",
            "message": f"New broken wikicode detected: {', '.join(increased_indicators)}",
        }

    # Check if there are any indicators at all
    total_current = sum(current_indicators.values())
    if total_current > 0:
        return {
            "id": "broken-wikicode",
            "title": "Broken wikicode check",
            "status": "ok",
            "message": f"Found {total_current} indicator(s) but no new ones introduced.",
        }

    return {
        "id": "broken-wikicode",
        "title": "Broken wikicode check",
        "status": "ok",
        "message": "No broken wikicode indicators detected.",
    }
