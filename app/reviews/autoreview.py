"""Logic for simulating automatic review decisions for pending revisions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import pywikibot

from .models import EditorProfile, PendingPage, PendingRevision, Wiki
from bs4 import BeautifulSoup

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
    redirect_aliases = _get_redirect_aliases(page.wiki)
    client = WikiClient(page.wiki)

    results: list[dict] = []
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
    tests: list[dict] = []

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
    else:
        tests.append(
            {
                "id": "bot-user",
                "title": "Bot user",
                "status": "not_ok",
                "message": "The user is not marked as a bot.",
            }
        )

    # Test 2: Autoapproved editors can always be auto-approved.
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
        else:
            tests.append(
                {
                    "id": "auto-approved-group",
                    "title": "Auto-approved groups",
                    "status": "not_ok",
                    "message": "The user does not belong to auto-approved groups.",
                }
            )
    else:
        if profile and profile.is_autoreviewed:
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

    # Test 3: Do not approve article to redirect conversions
    is_redirect_conversion = _is_article_to_redirect_conversion(
        revision, redirect_aliases
    )

    if is_redirect_conversion:
        tests.append(
            {
                "id": "article-to-redirect-conversion",
                "title": "Article-to-redirect conversion",
                "status": "fail",
                "message": (
                    "Converting articles to redirects "
                    "requires autoreview rights."
                ),
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
    else:
        tests.append(
            {
                "id": "article-to-redirect-conversion",
                "title": "Article-to-redirect conversion",
                "status": "ok",
                "message": "This is not an article-to-redirect conversion.",
            }
        )

    # Check if user has autopatrolled rights (after redirect conversion check)
    if profile and profile.is_autopatrolled:
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The user has autopatrol rights that allow auto-approval.",
            ),
        }

    # Test 4: Blocking categories on the old version prevent automatic approval.
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

    # Test 4: Check for new rendering errors in the HTML.
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

    is_ref_only, has_ref_removals, added_or_modified_refs = _is_reference_only_edit(
        revision
    )

    if is_ref_only:
        if has_ref_removals:
            tests.append(
                {
                    "id": "reference-only-edit",
                    "title": "Reference-only edit",
                    "status": "fail",
                    "message": "The edit removes references, which requires manual review.",
                }
            )
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="manual",
                    label="Requires human review",
                    reason="Reference-only edits that remove references require manual review.",
                ),
            }

        urls = _extract_urls_from_references(added_or_modified_refs)

        if urls:
            domains = []
            for url in urls:
                domain = _extract_domain(url)
                if domain:
                    domains.append(domain)

            unknown_domains = []
            for domain in set(domains):
                if not _check_domain_usage_in_wikipedia(revision.page.wiki, domain):
                    unknown_domains.append(domain)

            if unknown_domains:
                domain_list = ", ".join(sorted(unknown_domains))
                tests.append(
                    {
                        "id": "reference-only-edit",
                        "title": "Reference-only edit",
                        "status": "fail",
                        "message": (
                            f"The edit adds references with new domains: "
                            f"{domain_list}. Manual review required."
                        ),
                    }
                )
                return {
                    "tests": tests,
                    "decision": AutoreviewDecision(
                        status="manual",
                        label="Requires human review",
                        reason=(
                            "Reference-only edits with new external domains "
                            "require manual review."
                        ),
                    ),
                }

        tests.append(
            {
                "id": "reference-only-edit",
                "title": "Reference-only edit",
                "status": "ok",
                "message": "The edit only adds or modifies references with known domains.",
            }
        )
        return {
            "tests": tests,
            "decision": AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The edit only adds or modifies references.",
            ),
        }
    else:
        tests.append(
            {
                "id": "reference-only-edit",
                "title": "Reference-only edit",
                "status": "not_ok",
                "message": "This is not a reference-only edit.",
            }
        )

    return {
        "tests": tests,
        "decision": AutoreviewDecision(
            status="manual",
            label="Requires human review",
            reason="In dry-run mode the edit would not be approved automatically.",
        ),
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
        _get_render_error_count(parent_revision, previous_html)
        if parent_revision
        else 0
    )

    return current_error_count > previous_error_count


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
    """
    Check if a user is a bot or former bot.

    Args:
        revision: The pending revision to check
        profile: The editor profile if available

    Returns:
        True if the user is a current bot or former bot, False otherwise
    """
    superset = revision.superset_data or {}
    if superset.get("rc_bot"):
        return True

    # Check if we have is_bot_edit result (checks both current and former bot status)
    if is_bot_edit(revision):
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


def is_bot_edit(revision: PendingRevision) -> bool:
    """Check if a revision was made by a bot or former bot."""
    if not revision.user_name:
        return False
    try:
        profile = EditorProfile.objects.get(
            wiki=revision.page.wiki,
            username=revision.user_name
        )
        # Check both current bot status and former bot status
        return profile.is_bot or profile.is_former_bot
    except EditorProfile.DoesNotExist:
        return False


def _get_redirect_aliases(wiki: Wiki) -> list[str]:
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
    except Exception:  # pragma: no cover - network failure fallback
        logger.exception("Failed to fetch redirect magic words for %s", wiki.code)

    language_fallbacks = {
        "de": ["#WEITERLEITUNG", "#REDIRECT"],
        "en": ["#REDIRECT"],
        "pl": ["#PATRZ", "#PRZEKIERUJ", "#TAM", "#REDIRECT"],
        "fi": ["#OHJAUS", "#UUDELLEENOHJAUS", "#REDIRECT"],
    }

    fallback_aliases = language_fallbacks.get(
        wiki.code,
        ["#REDIRECT"]  # fallback for non default languages
    )

    logger.warning(
        "Using fallback redirect aliases for %s: %s",
        wiki.code,
        fallback_aliases,
    )

    # Not saving fallback to cache, so it can be updated later using the API
    return fallback_aliases


def _is_redirect(wikitext: str, redirect_aliases: list[str]) -> bool:
    if not wikitext or not redirect_aliases:
        return False

    patterns = []
    for alias in redirect_aliases:
        word = alias.lstrip('#').strip()
        if word:
            patterns.append(re.escape(word))

    if not patterns:
        return False

    redirect_pattern = (
        r'^#[ \t]*(' + '|'.join(patterns) + r')[ \t]*\[\[([^\]\n\r]+?)\]\]'
    )

    match = re.match(redirect_pattern, wikitext, re.IGNORECASE)
    return match is not None


def _get_parent_wikitext(revision: PendingRevision) -> str:
    """Get parent revision wikitext from local database.

    The parent should always be available in the local PendingRevision table,
    as it includes the latest stable revision (fp_stable_id) which is the
    parent of the first pending change.
    """
    if not revision.parentid:
        return ""

    try:
        parent_revision = PendingRevision.objects.get(
            page=revision.page,
            revid=revision.parentid
        )
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
    current_wikitext = revision.get_wikitext()
    if not _is_redirect(current_wikitext, redirect_aliases):
        return False

    if not revision.parentid:
        return False

    parent_wikitext = _get_parent_wikitext(revision)
    if not parent_wikitext:
        return False

    if _is_redirect(parent_wikitext, redirect_aliases):
        return False

    return True


def _extract_references(wikitext: str) -> dict[str, str]:
    """Extract all reference tags from wikitext.

    Returns a dictionary mapping reference positions to their content.
    """
    if not wikitext:
        return {}

    references = {}
    ref_pattern = r'<ref(?:\s+[^>]*)?>(?:.*?)</ref>|<ref(?:\s+[^>]*)?/>'

    for i, match in enumerate(re.finditer(ref_pattern, wikitext, re.IGNORECASE | re.DOTALL)):
        references[f"ref_{i}"] = match.group(0)

    return references


def _remove_references(wikitext: str) -> str:
    """Remove all reference tags from wikitext, leaving other content."""
    if not wikitext:
        return ""

    ref_pattern = r'<ref(?:\s+[^>]*)?>(?:.*?)</ref>|<ref(?:\s+[^>]*)?/>'
    cleaned = re.sub(ref_pattern, '', wikitext, flags=re.IGNORECASE | re.DOTALL)

    return cleaned


def _is_reference_only_edit(revision: PendingRevision) -> tuple[bool, bool, list[str]]:
    """Check if an edit only adds or modifies references.

    Returns:
        tuple: (is_reference_only, has_removals, added_or_modified_refs)
            - is_reference_only: True if only references changed
            - has_removals: True if references were removed
            - added_or_modified_refs: List of new/modified reference content
    """
    if not revision.parentid:
        return False, False, []

    current_wikitext = revision.get_wikitext()
    parent_wikitext = _get_parent_wikitext(revision)

    if not parent_wikitext:
        return False, False, []

    current_refs = _extract_references(current_wikitext)
    parent_refs = _extract_references(parent_wikitext)

    current_content = _remove_references(current_wikitext)
    parent_content = _remove_references(parent_wikitext)

    current_content_normalized = ' '.join(current_content.split())
    parent_content_normalized = ' '.join(parent_content.split())

    if current_content_normalized != parent_content_normalized:
        return False, False, []

    if current_refs == parent_refs:
        return False, False, []

    current_ref_values = set(current_refs.values())
    parent_ref_values = set(parent_refs.values())

    has_removals = len(parent_ref_values - current_ref_values) > 0
    added_or_modified = list(current_ref_values - parent_ref_values)

    return True, has_removals, added_or_modified


def _extract_urls_from_references(references: list[str]) -> list[str]:
    """Extract URLs from reference tags.

    Args:
        references: List of reference tag content

    Returns:
        List of URLs found in the references
    """
    urls = []
    url_pattern = r'https?://[^\s\]<>"\'\|\{\}]+(?:\([^\s\)]*\))?'

    for ref in references:
        for match in re.finditer(url_pattern, ref, re.IGNORECASE):
            url = match.group(0)
            url = url.rstrip('.,;:!?}')
            urls.append(url)

    return urls


def _extract_domain(url: str) -> str | None:
    """Extract domain from URL.

    Args:
        url: Full URL string

    Returns:
        Domain name or None if parsing fails
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain:
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        return None
    except Exception:
        return None


def _check_domain_usage_in_wikipedia(wiki: Wiki, domain: str) -> bool:
    """Check if a domain has been previously used in Wikipedia articles.

    Args:
        wiki: The wiki to check against
        domain: Domain name to check

    Returns:
        True if domain has been used before, False otherwise
    """
    try:
        site = pywikibot.Site(code=wiki.code, fam=wiki.family)

        ext_url_usage = site.exturlusage(
            url=domain,
            protocol='http',
            namespaces=[0],
            total=1
        )

        for _ in ext_url_usage:
            return True

        return False
    except Exception as e:
        logger.warning(
            "Failed to check domain usage for %s on %s: %s",
            domain,
            wiki.code,
            str(e)
        )
        return False
