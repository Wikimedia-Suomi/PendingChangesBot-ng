"""Logic for simulating automatic review decisions for pending revisions."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

import pywikibot
from bs4 import BeautifulSoup

from .models import EditorProfile, PendingPage, PendingRevision, Wiki
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
        page.revisions.exclude(revid=page.stable_revid).order_by("timestamp", "revid")
    )  # Oldest revision first.
    usernames = {revision.user_name for revision in revisions if revision.user_name}
    profiles = {
        profile.username: profile
        for profile in EditorProfile.objects.filter(wiki=page.wiki, username__in=usernames)
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

    # Test 1: Check if revision has been manually un-approved by a human reviewer
    is_manually_unapproved = client.has_manual_unapproval(revision.page.title, revision.revid)
    if is_manually_unapproved:
        tests.append(
            {
                "id": "manual-unapproval",
                "title": "Manual un-approval check",
                "status": "fail",
                "message": (
                    "This revision was manually un-approved by a human reviewer "
                    "and should not be auto-approved."
                ),
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
    else:
        tests.append(
            {
                "id": "manual-unapproval",
                "title": "Manual un-approval check",
                "status": "ok",
                "message": "This revision has not been manually un-approved.",
            }
        )

    # Test 2: Bot editors can always be auto-approved.
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

    # Test 3: Check if user was blocked after making the edit
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
        else:
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

    # Test 4: Autoapproved editors can always be auto-approved.
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

    # Test 5: Do not approve article to redirect conversions
    is_redirect_conversion = _is_article_to_redirect_conversion(revision, redirect_aliases)

    if is_redirect_conversion:
        tests.append(
            {
                "id": "article-to-redirect-conversion",
                "title": "Article-to-redirect conversion",
                "status": "fail",
                "message": ("Converting articles to redirects requires autoreview rights."),
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

    # Test 6: Blocking categories on the old version prevent automatic approval.
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

    # Test 7: Check for new rendering errors in the HTML.
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

    # Test 7: Reference-only edits can be auto-approved if domains are verified
    parent_wikitext = _get_parent_wikitext(revision)
    current_wikitext = revision.get_wikitext()
    ref_check = _is_reference_only_edit(parent_wikitext, current_wikitext)

    if ref_check['is_reference_only']:
        # Get domains from added and modified references
        all_changed_refs = ref_check['added_refs'] + ref_check['modified_refs']
        domains = _get_domains_from_references(all_changed_refs)

        if domains:
            # Check if all domains exist on the wiki
            unverified_domains = []
            for domain in domains:
                if not _check_domain_exists_on_wiki(domain, revision.page.wiki):
                    unverified_domains.append(domain)

            if unverified_domains:
                tests.append(
                    {
                        "id": "reference-only-edit",
                        "title": "Reference-only edit",
                        "status": "fail",
                        "message": (
                            "Edit only modifies references, but contains "
                            "unverified domains: {}.".format(
                                ", ".join(sorted(unverified_domains))
                            )
                        ),
                    }
                )
                return {
                    "tests": tests,
                    "decision": AutoreviewDecision(
                        status="manual",
                        label="Requires human review",
                        reason="Reference-only edit contains unverified external domains.",
                    ),
                }
            else:
                tests.append(
                    {
                        "id": "reference-only-edit",
                        "title": "Reference-only edit",
                        "status": "ok",
                        "message": (
                            "Edit only adds/modifies references with verified domains."
                        ),
                    }
                )
                return {
                    "tests": tests,
                    "decision": AutoreviewDecision(
                        status="approve",
                        label="Would be auto-approved",
                        reason="Edit only adds or modifies references with verified domains.",
                    ),
                }
        else:
            # No domains in references, can approve
            tests.append(
                {
                    "id": "reference-only-edit",
                    "title": "Reference-only edit",
                    "status": "ok",
                    "message": "Edit only adds/modifies references without external links.",
                }
            )
            return {
                "tests": tests,
                "decision": AutoreviewDecision(
                    status="approve",
                    label="Would be auto-approved",
                    reason="Edit only adds or modifies references without external links.",
                ),
            }
    elif ref_check['removed_refs'] and not ref_check['added_refs'] and not ref_check['modified_refs']:
        # Only removed references, require manual review
        tests.append(
            {
                "id": "reference-only-edit",
                "title": "Reference-only edit",
                "status": "fail",
                "message": "Edit only removes references, requires manual review.",
            }
        )
    else:
        # Not a reference-only edit
        tests.append(
            {
                "id": "reference-only-edit",
                "title": "Reference-only edit",
                "status": "not_ok",
                "message": "Edit is not reference-only.",
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
        _get_render_error_count(parent_revision, previous_html) if parent_revision else 0
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


def _blocking_category_hits(revision: PendingRevision, blocking_lookup: dict[str, str]) -> set[str]:
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
        profile = EditorProfile.objects.get(wiki=revision.page.wiki, username=revision.user_name)
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
        ["#REDIRECT"],  # fallback for non default languages
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
        word = alias.lstrip("#").strip()
        if word:
            patterns.append(re.escape(word))

    if not patterns:
        return False

    redirect_pattern = r"^#[ \t]*(" + "|".join(patterns) + r")[ \t]*\[\[([^\]\n\r]+?)\]\]"

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


def _extract_references(wikitext: str) -> list[dict[str, str]]:
    """Extract all reference tags from wikitext.

    Args:
        wikitext: The wikitext to parse

    Returns:
        List of dicts with keys: 'full_match', 'content', 'name', 'group'
        For self-closing refs, 'content' will be empty string
    """
    if not wikitext:
        return []

    references = []

    # Pattern for standard <ref>content</ref> tags (with optional attributes)
    # Captures: name attribute, group attribute, content
    standard_pattern = (
        r'<ref'
        r'(?:\s+name\s*=\s*"([^"]*)")?'  # Optional name attribute
        r'(?:\s+group\s*=\s*"([^"]*)")?'  # Optional group attribute
        r'(?:\s+[^>]*)?'  # Any other attributes
        r'>'
        r'(.*?)'  # Content (non-greedy)
        r'</ref>'
    )

    # Pattern for self-closing <ref /> tags
    # Captures: name attribute, group attribute
    self_closing_pattern = (
        r'<ref'
        r'(?:\s+name\s*=\s*"([^"]*)")?'  # Optional name attribute
        r'(?:\s+group\s*=\s*"([^"]*)")?'  # Optional group attribute
        r'(?:\s+[^>]*)?'  # Any other attributes
        r'\s*/>'
    )

    # Find all standard refs
    for match in re.finditer(standard_pattern, wikitext, re.DOTALL | re.IGNORECASE):
        references.append({
            'full_match': match.group(0),
            'name': match.group(1) or '',
            'group': match.group(2) or '',
            'content': match.group(3) or '',
        })

    # Find all self-closing refs
    for match in re.finditer(self_closing_pattern, wikitext, re.IGNORECASE):
        references.append({
            'full_match': match.group(0),
            'name': match.group(1) or '',
            'group': match.group(2) or '',
            'content': '',
        })

    return references


def _remove_references(wikitext: str) -> str:
    """Remove all reference tags from wikitext, leaving other content intact.

    Args:
        wikitext: The wikitext to process

    Returns:
        Wikitext with all <ref>...</ref> and <ref /> tags removed
    """
    if not wikitext:
        return ''

    # Remove standard refs
    result = re.sub(
        r'<ref(?:\s+[^>]*)?>.*?</ref>',
        '',
        wikitext,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Remove self-closing refs
    result = re.sub(
        r'<ref(?:\s+[^>]*)?/>',
        '',
        result,
        flags=re.IGNORECASE
    )

    return result


def _extract_urls_from_text(text: str) -> list[str]:
    """Extract URLs from text.

    Args:
        text: Text that may contain URLs

    Returns:
        List of URLs found in the text
    """
    if not text:
        return []

    # Pattern for URLs (http, https, ftp)
    url_pattern = r'https?://[^\s\]<>"\'}]+'

    urls = re.findall(url_pattern, text, re.IGNORECASE)
    return urls


def _extract_domain_from_url(url: str) -> str:
    """Extract domain from URL.

    Args:
        url: Full URL

    Returns:
        Domain extracted from URL, empty string if invalid
    """
    if not url:
        return ''

    # Simple domain extraction from URL
    # Match pattern: protocol://domain/path
    match = re.match(r'https?://([^/\s:]+)', url, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return ''


def _get_domains_from_references(refs: list[dict]) -> set[str]:
    """Extract all unique domains from a list of references.

    Args:
        refs: List of reference dicts with 'content' key

    Returns:
        Set of unique domains found in reference content
    """
    domains = set()
    for ref in refs:
        content = ref.get('content', '')
        urls = _extract_urls_from_text(content)
        for url in urls:
            domain = _extract_domain_from_url(url)
            if domain:
                domains.add(domain)
    return domains


def _check_domain_exists_on_wiki(domain: str, wiki: Wiki) -> bool:
    """Check if a domain has been used in articles on the wiki.

    Args:
        domain: Domain to check (e.g., "example.com")
        wiki: Wiki instance to check against

    Returns:
        True if domain has been used in namespace 0 (articles), False otherwise
    """
    if not domain:
        return False

    try:
        site = pywikibot.Site(code=wiki.code, fam=wiki.family)

        # Use exturlusage to check if domain exists in article namespace (0)
        # We only need to check if at least one result exists
        results = list(site.exturlusage(domain, namespaces=[0], total=1))

        return len(results) > 0

    except Exception:  # pragma: no cover - network failure fallback
        logger.exception("Failed to check domain %s on wiki %s", domain, wiki.code)
        # On failure, be conservative and return False (require manual review)
        return False


def _is_reference_only_edit(old_wikitext: str, new_wikitext: str) -> dict:
    """Detect if an edit only adds or modifies references.

    Args:
        old_wikitext: Previous version wikitext
        new_wikitext: Current version wikitext

    Returns:
        Dict with keys:
            - is_reference_only: bool indicating if only refs changed
            - added_refs: list of added reference dicts
            - modified_refs: list of modified reference dicts
            - removed_refs: list of removed reference dicts
            - non_ref_changed: bool indicating if non-ref content changed
    """
    old_refs = _extract_references(old_wikitext)
    new_refs = _extract_references(new_wikitext)

    # Remove refs to compare non-ref content
    old_without_refs = _remove_references(old_wikitext)
    new_without_refs = _remove_references(new_wikitext)

    # Normalize whitespace for comparison
    old_normalized = ' '.join(old_without_refs.split())
    new_normalized = ' '.join(new_without_refs.split())

    non_ref_changed = old_normalized != new_normalized

    # Build ref lookup by name (for named refs) or content (for unnamed refs)
    def ref_key(ref: dict) -> str:
        """Create unique key for reference matching."""
        if ref['name']:
            return f"name:{ref['name']}"
        return f"content:{ref['content']}"

    old_ref_map = {ref_key(ref): ref for ref in old_refs}
    new_ref_map = {ref_key(ref): ref for ref in new_refs}

    old_keys = set(old_ref_map.keys())
    new_keys = set(new_ref_map.keys())

    added_refs = [new_ref_map[key] for key in (new_keys - old_keys)]
    removed_refs = [old_ref_map[key] for key in (old_keys - new_keys)]

    # Check for modifications (same key but different content)
    modified_refs = []
    for key in old_keys & new_keys:
        if old_ref_map[key]['content'] != new_ref_map[key]['content']:
            modified_refs.append(new_ref_map[key])

    # It's reference-only if:
    # 1. Non-ref content hasn't changed
    # 2. At least some refs were added or modified
    # 3. No refs were removed (or only replaced)
    is_reference_only = (
        not non_ref_changed
        and (len(added_refs) > 0 or len(modified_refs) > 0)
        and len(removed_refs) == 0
    )

    return {
        'is_reference_only': is_reference_only,
        'added_refs': added_refs,
        'modified_refs': modified_refs,
        'removed_refs': removed_refs,
        'non_ref_changed': non_ref_changed,
    }
