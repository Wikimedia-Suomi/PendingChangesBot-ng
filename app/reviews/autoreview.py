"""Logic for simulating automatic review decisions for pending revisions."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

import pywikibot
from bs4 import BeautifulSoup
from django.conf import settings
from pywikibot.comms import http
from reviewer.utils.is_living_person import is_living_person

from .models import EditorProfile, ModelScores, PendingPage, PendingRevision, Wiki
from .services import WikiClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoreviewDecision:
    """Represents the aggregated outcome for a revision."""

    status: str
    label: str
    reason: str


def run_autoreview_for_page(page: PendingPage) -> list[dict]:
    """Run the configured autoreview checks for each pending revision of a page."""
    # Fetch all needed data once outside the loop
    revisions = list(page.revisions.exclude(revid=page.stable_revid).order_by("timestamp", "revid"))
    if not revisions:
        return []

    usernames = {rev.user_name for rev in revisions if rev.user_name}
    profiles = (
        {
            profile.username: profile
            for profile in EditorProfile.objects.filter(wiki=page.wiki, username__in=usernames)
        }
        if usernames
        else {}
    )

    configuration = page.wiki.configuration
    auto_groups = _normalize_to_lookup(configuration.auto_approved_groups)
    blocking_categories = _normalize_to_lookup(configuration.blocking_categories)
    redirect_aliases = _get_redirect_aliases(page.wiki)
    client = WikiClient(page.wiki)

    results = []
    for revision in revisions:
        profile = profiles.get(revision.user_name or "")
        revision_result = _evaluate_revision(
            revision,
            client,
            profile,
            auto_groups=auto_groups,
            blocking_categories=blocking_categories,
            redirect_aliases=redirect_aliases,
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
    client: WikiClient,
    profile: EditorProfile | None,
    *,
    auto_groups: dict[str, str],
    blocking_categories: dict[str, str],
    redirect_aliases: list[str],
) -> dict:
    """Evaluate a revision using the autoreview checks in optimized order."""
    tests = []

    # TEST 1: Manual un-approval check (fastest, blocks immediately)
    is_manually_unapproved = client.has_manual_unapproval(revision.page.title, revision.revid)
    if is_manually_unapproved:
        tests.append(
            {
                "id": "manual-unapproval",
                "title": "Manual un-approval check",
                "status": "fail",
                "message": "This revision was manually un-approved by a human reviewer and should not be auto-approved.",  # noqa: E501
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="Revision was manually un-approved by a human reviewer.",
            ),
        }
    tests.append(
        {
            "id": "manual-unapproval",
            "title": "Manual un-approval check",
            "status": "ok",
            "message": "This revision has not been manually un-approved.",
        }
    )

    # TEST 2: Bot user check (approves immediately)
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

    # TEST 3: User block status (blocks immediately)
    try:
        if client.is_user_blocked_after_edit(revision.user_name, revision.timestamp):
            tests.append(
                {
                    "id": "blocked-user",
                    "title": "User blocked after edit",
                    "status": "fail",
                    "message": "User was blocked after making this edit.",
                }
            )
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="blocked",
                    label="Cannot be auto-approved",
                    reason="User was blocked after making this edit.",
                ),
            }
        tests.append(
            {
                "id": "blocked-user",
                "title": "User block status",
                "status": "ok",
                "message": "User has not been blocked since making this edit.",
            }
        )
    except Exception as e:
        logger.error(f"Error checking blocks for {revision.user_name}: {e}")
        tests.append(
            {
                "id": "blocked-user",
                "title": "Block check failed",
                "status": "fail",
                "message": "Could not verify user block status.",
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="error",
                label="Cannot be auto-approved",
                reason="Unable to verify user was not blocked.",
            ),
        }

    # TEST 4: Auto-approved groups (approves immediately)
    if auto_groups:
        matched_groups = _matched_user_groups(revision, profile, allowed_groups=auto_groups)
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
    elif profile and profile.is_autoreviewed:
        tests.append(
            {
                "id": "auto-approved-group",
                "title": "Auto-approved groups",
                "status": "ok",
                "message": "The user has default auto-approval rights: Autoreviewed.",
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The user has autoreview rights that allow auto-approval.",
            ),
        }
    else:
        tests.append(
            {
                "id": "auto-approved-group",
                "title": "Auto-approved groups",
                "status": "not_ok",
                "message": (
                    "The user does not have autoreview rights."
                    if profile and profile.is_autopatrolled
                    else "The user does not have default auto-approval rights."
                ),
            }
        )

    # TEST 5: Article-to-redirect conversion (blocks immediately)
    if _is_article_to_redirect_conversion(revision, redirect_aliases):
        tests.append(
            {
                "id": "article-to-redirect-conversion",
                "title": "Article-to-redirect conversion",
                "status": "fail",
                "message": "Converting articles to redirects requires autoreview rights.",
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="Article-to-redirect conversions require autoreview rights.",
            ),
        }
    tests.append(
        {
            "id": "article-to-redirect-conversion",
            "title": "Article-to-redirect conversion",
            "status": "ok",
            "message": "This is not an article-to-redirect conversion.",
        }
    )

    # Autopatrolled users approved after redirect check
    if profile and profile.is_autopatrolled:
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The user has autopatrol rights that allow auto-approval.",
            ),
        }

    # TEST 6: Blocking categories (blocks immediately)
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

    # TEST 7: Check for new rendering errors (blocks immediately)
    new_render_errors = _check_for_new_render_errors(revision, client)
    if new_render_errors:
        tests.append(
            {
                "id": "new-render-errors",
                "title": "New render errors",
                "status": "fail",
                "message": "The edit introduces new rendering errors.",
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="The edit introduces new rendering errors.",
            ),
        }
    tests.append(
        {
            "id": "new-render-errors",
            "title": "New render errors",
            "status": "ok",
            "message": "The edit does not introduce new rendering errors.",
        }
    )

    # TEST 8: Invalid ISBN checksums (blocks immediately)
    wikitext = revision.get_wikitext()
    invalid_isbns = _find_invalid_isbns(wikitext)
    if invalid_isbns:
        tests.append(
            {
                "id": "invalid-isbn",
                "title": "ISBN checksum validation",
                "status": "fail",
                "message": "The edit contains invalid ISBN(s): {}.".format(
                    ", ".join(invalid_isbns)
                ),
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="The edit contains ISBN(s) with invalid checksums.",
            ),
        }
    tests.append(
        {
            "id": "invalid-isbn",
            "title": "ISBN checksum validation",
            "status": "ok",
            "message": "No invalid ISBNs detected.",
        }
    )

    # TEST 9: Check if additions have been superseded (approves immediately)
    try:
        stable_revision = PendingRevision.objects.filter(
            page=revision.page, revid=revision.page.stable_revid
        ).first()

        if stable_revision:
            current_stable_wikitext = stable_revision.get_wikitext()
            threshold = revision.page.wiki.configuration.superseded_similarity_threshold

            if _is_addition_superseded(revision, current_stable_wikitext, threshold):
                tests.append(
                    {
                        "id": "superseded-additions",
                        "title": "Superseded additions",
                        "status": "ok",
                        "message": "The additions from this revision have been superseded or removed in the latest version.",  # noqa: E501
                    }
                )
                return {
                    "tests": tests,
                    "decision": AutoreviewDecision(
                        status="approve",
                        label="Would be auto-approved",
                        reason="The additions from this revision have been superseded or removed in the latest version.",  # noqa: E501
                    ),
                }
        tests.append(
            {
                "id": "superseded-additions",
                "title": "Superseded additions",
                "status": "not_ok",
                "message": "The additions from this revision are still relevant.",
            }
        )
    except Exception as e:
        logger.error(f"Error checking superseded additions for revision {revision.revid}: {e}")
        tests.append(
            {
                "id": "superseded-additions",
                "title": "Superseded additions check",
                "status": "not_ok",
                "message": "Could not verify if additions were superseded.",
            }
        )

    # TEST 10: ORES edit quality scores (expensive API call, do last)
    ores_result = _evaluate_ores_thresholds(revision)
    if ores_result:
        tests.append(ores_result["test"])
        if ores_result["should_block"]:
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="blocked",
                    label="Cannot be auto-approved",
                    reason="ORES edit quality scores indicate potential issues.",
                ),
            }

    # No automatic approval criteria met
    return {
        "tests": tests,
        "decision": AutoreviewDecision(
            status="manual",
            label="Requires human review",
            reason="In dry-run mode the edit would not be approved automatically.",
        ),
    }


def _is_bot_user(revision: PendingRevision, profile: EditorProfile | None) -> bool:
    """Check if a user is a bot or former bot."""
    # Check revision metadata first (faster)
    superset = revision.superset_data or {}
    if superset.get("rc_bot"):
        return True

    # Check user profile
    if profile and (profile.is_bot or profile.is_former_bot):
        return True

    return False


def _get_redirect_aliases(wiki: Wiki) -> list[str]:
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


def _normalize_to_lookup(values: Iterable[str] | None) -> dict[str, str]:
    """Convert list of strings to case-folded lookup dictionary."""
    if not values:
        return {}
    return {str(v).casefold(): str(v) for v in values if v}


def _matched_user_groups(
    revision: PendingRevision,
    profile: EditorProfile | None,
    *,
    allowed_groups: dict[str, str],
) -> set[str]:
    """Check which allowed groups the user belongs to."""
    if not allowed_groups:
        return set()

    groups = []
    superset = revision.superset_data or {}
    superset_groups = superset.get("user_groups") or []
    if isinstance(superset_groups, list):
        groups.extend(str(group) for group in superset_groups if group)
    if profile and profile.usergroups:
        groups.extend(str(group) for group in profile.usergroups if group)

    return {allowed_groups[g.casefold()] for g in groups if g.casefold() in allowed_groups}


def _blocking_category_hits(revision: PendingRevision, blocking_lookup: dict[str, str]) -> set[str]:
    """Check if revision belongs to any blocking categories."""
    if not blocking_lookup:
        return set()

    categories = list(revision.get_categories())
    page_categories = revision.page.categories or []
    if isinstance(page_categories, list):
        categories.extend(str(category) for category in page_categories if category)

    return {
        blocking_lookup[cat.casefold()] for cat in categories if cat.casefold() in blocking_lookup
    }


def _get_render_error_count(revision: PendingRevision, html: str) -> int:
    """Calculate and cache the number of rendering errors in the HTML."""
    if revision.render_error_count is not None:
        return revision.render_error_count

    soup = BeautifulSoup(html, "lxml")
    error_count = len(soup.find_all(class_="error"))

    revision.render_error_count = error_count
    revision.save(update_fields=["render_error_count"])
    return error_count


def _check_for_new_render_errors(revision: PendingRevision, client: WikiClient) -> bool:
    """Check if a revision introduces new HTML elements with class='error'."""
    if not revision.parentid:
        return False

    current_html = client.get_rendered_html(revision.revid)
    previous_html = client.get_rendered_html(revision.parentid)

    if not current_html or not previous_html:
        return False

    current_error_count = _get_render_error_count(revision, current_html)

    parent_revision = PendingRevision.objects.filter(
        page__wiki=revision.page.wiki, revid=revision.parentid
    ).first()
    previous_error_count = (
        _get_render_error_count(parent_revision, previous_html) if parent_revision else 0
    )

    return current_error_count > previous_error_count


def _is_redirect(wikitext: str, redirect_aliases: list[str]) -> bool:
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


def _get_parent_wikitext(revision: PendingRevision) -> str:
    """Get parent revision wikitext from local database."""
    if not revision.parentid:
        return ""

    try:
        parent_revision = PendingRevision.objects.get(page=revision.page, revid=revision.parentid)
        return parent_revision.get_wikitext()
    except PendingRevision.DoesNotExist:
        logger.warning(
            "Parent revision %s not found in local database for revision %s",
            revision.parentid,
            revision.revid,
        )
        return ""


def _is_article_to_redirect_conversion(
    revision: PendingRevision,
    redirect_aliases: list[str],
) -> bool:
    """Check if revision converts an article to a redirect."""
    current_wikitext = revision.get_wikitext()

    # Fast check if current revision isn't a redirect
    if not _is_redirect(current_wikitext, redirect_aliases):
        return False

    if not revision.parentid:
        return False

    # Current is redirect, check if parent wasn't
    parent_wikitext = _get_parent_wikitext(revision)
    return parent_wikitext and not _is_redirect(parent_wikitext, redirect_aliases)


def _normalize_wikitext(text: str) -> str:
    """Normalize wikitext for similarity comparison."""
    if not text:
        return ""

    # Remove ref tags and their content
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<ref[^>]*/>", "", text, flags=re.IGNORECASE)

    # Remove templates (simplified approach for performance)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # Run again for nested templates

    # Remove HTML comments, categories, file links
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[Category:[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[(File|Image):[^\]]+\]\]", "", text, flags=re.IGNORECASE | re.DOTALL)

    # Strip wiki formatting but keep link text
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)  # [[link|text]] -> text
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)  # [[link]] -> link
    text = re.sub(r"'{2,}", "", text)  # Remove bold/italic markup

    # Normalize whitespace
    return re.sub(r"\s+", " ", text).strip()


def _extract_additions(parent_wikitext: str, pending_wikitext: str) -> list[str]:
    """Extract text additions from parent to pending revision."""
    if not pending_wikitext:
        return []

    if not parent_wikitext:
        return [pending_wikitext]  # If no parent, entire text is addition

    matcher = SequenceMatcher(None, parent_wikitext, pending_wikitext)
    additions = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            added_text = pending_wikitext[j1:j2]
            if added_text.strip():
                additions.append(added_text)

    return additions


def _is_addition_superseded(
    revision: PendingRevision,
    current_stable_wikitext: str,
    threshold: float,
) -> bool:
    """Check if text additions from a pending revision have been superseded."""
    # Get the latest revision for the page
    latest_revision = PendingRevision.objects.filter(page=revision.page).order_by("-revid").first()

    if not latest_revision or latest_revision.revid == revision.revid:
        return False

    # Get the latest version wikitext
    latest_wikitext = latest_revision.get_wikitext()
    if not latest_wikitext:
        return False

    # Get parent and pending wikitext
    parent_wikitext = _get_parent_wikitext(revision)
    pending_wikitext = revision.get_wikitext()
    if not pending_wikitext:
        return False

    # Extract additions
    additions = _extract_additions(parent_wikitext, pending_wikitext)
    if not additions:
        return False

    # Normalize latest text once for all comparisons
    normalized_latest = _normalize_wikitext(latest_wikitext)
    if not normalized_latest:
        return False

    # Check each significant addition against the latest text
    for addition in additions:
        normalized_addition = _normalize_wikitext(addition)

        # Skip very short additions
        if len(normalized_addition) < 20:
            continue

        # Calculate what percentage of the addition is present in latest version
        matcher = SequenceMatcher(None, normalized_addition, normalized_latest)
        significant_match_length = sum(
            block.size for block in matcher.get_matching_blocks()[:-1] if block.size >= 4
        )

        if len(normalized_addition) > 0:
            match_ratio = significant_match_length / len(normalized_addition)
            if match_ratio < threshold:
                logger.info(
                    "Revision %s appears superseded: addition has %.2f%% match (< %.2f%% threshold)",  # noqa: E501
                    revision.revid,
                    match_ratio * 100,
                    threshold * 100,
                )
                return True

    return False


def _validate_isbn_10(isbn: str) -> bool:
    """Validate ISBN-10 checksum."""
    if len(isbn) != 10:
        return False

    total = 0
    for i in range(9):
        if not isbn[i].isdigit():
            return False
        total += int(isbn[i]) * (10 - i)

    check_digit = 10 if isbn[9].upper() == "X" else int(isbn[9]) if isbn[9].isdigit() else -1
    if check_digit < 0:
        return False

    return total % 11 == (11 - check_digit) % 11


def _validate_isbn_13(isbn: str) -> bool:
    """Validate ISBN-13 checksum."""
    if (
        len(isbn) != 13
        or not isbn.isdigit()
        or not (isbn.startswith("978") or isbn.startswith("979"))
    ):
        return False

    total = sum(int(isbn[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
    check_digit = (10 - (total % 10)) % 10
    return int(isbn[12]) == check_digit


def _find_invalid_isbns(text: str) -> list[str]:
    """Find all ISBNs in text and return list of invalid ones."""
    isbn_pattern = re.compile(
        r"isbn\s*[=:]?\s*([0-9Xx\-\s]{1,30}?)(?=\s+\d{4}(?:\D|$)|[^\d\sXx\-]|$)", re.IGNORECASE
    )

    invalid_isbns = []
    for match in isbn_pattern.finditer(text):
        isbn_raw = match.group(1)
        isbn_clean = re.sub(r"[\s\-]", "", isbn_raw)

        if not isbn_clean:
            continue

        is_valid = (len(isbn_clean) == 10 and _validate_isbn_10(isbn_clean)) or (
            len(isbn_clean) == 13 and _validate_isbn_13(isbn_clean)
        )

        if not is_valid:
            invalid_isbns.append(isbn_raw.strip())

    return invalid_isbns


def _is_living_person_article(revision: PendingRevision) -> bool:
    """Check if article is about a living person."""
    try:
        return is_living_person(revision.page.wiki.code, revision.page.title)
    except Exception as e:
        logger.warning(
            f"Error checking if {revision.page.title} is living person: {e}. "
            "Assuming not a living person for safety."
        )
        return False


def _evaluate_ores_thresholds(revision: PendingRevision) -> dict | None:
    """Evaluate ORES thresholds with living person adjustments."""
    configuration = revision.page.wiki.configuration

    # Base thresholds - fallback to settings if 0
    damaging_threshold = configuration.ores_damaging_threshold or settings.ORES_DAMAGING_THRESHOLD
    goodfaith_threshold = (
        configuration.ores_goodfaith_threshold or settings.ORES_GOODFAITH_THRESHOLD
    )

    # Apply stricter thresholds for living person biographies
    if _is_living_person_article(revision):
        living_damaging = (
            configuration.ores_damaging_threshold_living or settings.ORES_DAMAGING_THRESHOLD_LIVING
        )
        living_goodfaith = (
            configuration.ores_goodfaith_threshold_living
            or settings.ORES_GOODFAITH_THRESHOLD_LIVING
        )
        damaging_threshold = living_damaging
        goodfaith_threshold = living_goodfaith

    if damaging_threshold == 0 and goodfaith_threshold == 0:
        return None

    return _check_ores_scores(revision, damaging_threshold, goodfaith_threshold)


def _check_ores_scores(
    revision: PendingRevision,
    damaging_threshold: float,
    goodfaith_threshold: float,
) -> dict:
    """Check ORES damaging and goodfaith scores for a revision."""
    # Determine which models need to be checked
    check_damaging = damaging_threshold > 0
    check_goodfaith = goodfaith_threshold > 0

    if not check_damaging and not check_goodfaith:
        return {
            "should_block": False,
            "test": {
                "id": "ores-scores",
                "title": "ORES edit quality scores",
                "status": "skip",
                "message": "ORES checks are disabled (thresholds set to 0).",
            },
        }

    # Try to get cached scores first
    try:
        model_scores = ModelScores.objects.get(revision=revision)
        damaging_prob = model_scores.ores_damaging_score
        goodfaith_prob = model_scores.ores_goodfaith_score
    except ModelScores.DoesNotExist:
        # No cached scores, fetch from API
        damaging_prob, goodfaith_prob = _fetch_ores_scores_from_api(
            revision, check_damaging, check_goodfaith
        )

    # Evaluate thresholds and return result
    return _evaluate_ores_thresholds_result(
        damaging_prob, goodfaith_prob, damaging_threshold, goodfaith_threshold
    )


def _fetch_ores_scores_from_api(
    revision: PendingRevision, check_damaging: bool, check_goodfaith: bool
) -> tuple[float | None, float | None]:
    """Fetch ORES scores from API and cache them."""
    wiki_code = revision.page.wiki.code
    wiki_family = revision.page.wiki.family
    ores_wiki = f"{wiki_code}{wiki_family[0:4]}"

    # Build models parameter
    models_to_check = []
    if check_damaging:
        models_to_check.append("damaging")
    if check_goodfaith:
        models_to_check.append("goodfaith")
    models_param = "|".join(models_to_check)

    url = f"https://ores.wikimedia.org/v3/scores/{ores_wiki}/{revision.revid}?models={models_param}"

    try:
        response = http.fetch(url, headers={"User-Agent": "PendingChangesBot/1.0"})
        data = json.loads(response.text)
        scores = data.get(ores_wiki, {}).get("scores", {}).get(str(revision.revid), {})

        # Extract scores from API response (only if threshold > 0)
        damaging_prob = (
            scores.get("damaging", {}).get("score", {}).get("probability", {}).get("true", 0.0)
            if check_damaging
            else None
        )
        goodfaith_prob = (
            scores.get("goodfaith", {}).get("score", {}).get("probability", {}).get("true", 1.0)
            if check_goodfaith
            else None
        )

        # Cache the scores
        ModelScores.objects.create(
            revision=revision,
            ores_damaging_score=damaging_prob,
            ores_goodfaith_score=goodfaith_prob,
        )

        return damaging_prob, goodfaith_prob

    except Exception as e:
        logger.error(f"Error fetching ORES scores for revision {revision.revid}: {e}")
        # Return None to indicate error - will be handled by caller
        return None, None


def _evaluate_ores_thresholds_result(
    damaging_prob: float | None,
    goodfaith_prob: float | None,
    damaging_threshold: float,
    goodfaith_threshold: float,
) -> dict:
    """Evaluate ORES scores against thresholds and return test result."""
    # Handle error case (API failure)
    if damaging_prob is None and goodfaith_prob is None:
        return {
            "should_block": True,
            "test": {
                "id": "ores-scores",
                "title": "ORES edit quality check failed",
                "status": "fail",
                "message": "Could not verify ORES edit quality scores.",
            },
        }

    # Check damaging threshold
    if damaging_threshold > 0 and damaging_prob is not None:
        if damaging_prob > damaging_threshold:
            return {
                "should_block": True,
                "test": {
                    "id": "ores-scores",
                    "title": "ORES edit quality scores",
                    "status": "fail",
                    "message": f"ORES damaging score ({damaging_prob:.3f}) exceeds threshold ({damaging_threshold:.3f}).",  # noqa: E501
                },
            }

    # Check goodfaith threshold
    if goodfaith_threshold > 0 and goodfaith_prob is not None:
        if goodfaith_prob < goodfaith_threshold:
            return {
                "should_block": True,
                "test": {
                    "id": "ores-scores",
                    "title": "ORES edit quality scores",
                    "status": "fail",
                    "message": f"ORES goodfaith score ({goodfaith_prob:.3f}) is below threshold ({goodfaith_threshold:.3f}).",  # noqa: E501
                },
            }

    # Build success message
    messages = []
    if damaging_threshold > 0 and damaging_prob is not None:
        messages.append(f"damaging: {damaging_prob:.3f}")
    if goodfaith_threshold > 0 and goodfaith_prob is not None:
        messages.append(f"goodfaith: {goodfaith_prob:.3f}")

    return {
        "should_block": False,
        "test": {
            "id": "ores-scores",
            "title": "ORES edit quality scores",
            "status": "ok",
            "message": f"ORES scores are within acceptable thresholds ({', '.join(messages)}).",
        },
    }
