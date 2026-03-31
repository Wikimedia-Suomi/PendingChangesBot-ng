from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reviews.models import PendingRevision

logger = logging.getLogger(__name__)


def normalize_wikitext(text: str) -> str:
    """Normalize wikitext for similarity comparison."""
    if not text:
        return ""

    # TODO: check why text is not always suitable for re.
    text = str(text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<ref[^>]*/>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[Category:[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[(File|Image):[^\]]+\]\]", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_additions(parent_wikitext: str, pending_wikitext: str) -> list[str]:
    """Extract text additions from parent to pending revision."""
    if not pending_wikitext:
        return []

    if not parent_wikitext:
        return [pending_wikitext]

    matcher = SequenceMatcher(None, parent_wikitext, pending_wikitext)
    additions = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            added_text = pending_wikitext[j1:j2]
            if added_text.strip():
                additions.append(added_text)

    return additions


def get_parent_wikitext(revision: PendingRevision) -> str:
    """Get parent revision wikitext from local database or API."""
    cached_parent = getattr(revision, "parent_wikitext", None)
    if isinstance(cached_parent, str) and cached_parent:
        return cached_parent

    parentid = getattr(revision, "parentid", None)
    if not isinstance(parentid, (int, str)) or not parentid:
        return ""

    try:
        from reviews.models import PendingRevision as PR

        parent_revision = PR.objects.get(page=revision.page, revid=parentid)
        return parent_revision.get_wikitext()
    except Exception:
        logger.info(
            "Parent revision %s not in local database, fetching from API for revision %s",
            revision.parentid,
            revision.revid,
        )
        try:
            import pywikibot

            wiki = revision.page.wiki
            site = pywikibot.Site(code=wiki.code, fam=wiki.family)
            request = site.simple_request(
                action="query",
                prop="revisions",
                revids=str(parentid),
                rvprop="content",
                rvslots="main",
                formatversion=2,
            )
            response = request.submit()
            pages = response.get("query", {}).get("pages", [])

            if pages and len(pages) > 0:
                revisions = pages[0].get("revisions", [])
                if revisions and len(revisions) > 0:
                    slots = revisions[0].get("slots", {})
                    main_slot = slots.get("main", {})
                    content = main_slot.get("content", "")
                    if content:
                        logger.info("Fetched parent revision %s from API", parentid)
                        return content

            logger.warning("Could not fetch parent revision %s from API", parentid)
            return ""
        except Exception as e:
            logger.exception("Error fetching parent revision %s from API: %s", parentid, e)
            return ""


def extract_references(text: str) -> list[str]:
    """Extract all reference tags from wikitext."""
    if not text:
        return []

    references = []

    # Extract self-closing refs
    for match in re.finditer(r"<ref[^>]*/>", text, re.IGNORECASE):
        references.append(match.group(0))

    # Extract paired refs (excluding self-closing)
    for match in re.finditer(r"<ref(?:(?!/>)[^>])*>(?:.*?)</ref>", text, re.IGNORECASE | re.DOTALL):
        references.append(match.group(0))

    return references


def strip_references(text: str) -> str:
    """Remove all reference tags from wikitext."""
    if not text:
        return ""

    # First remove self-closing ref tags: <ref ... />
    text = re.sub(r"<ref[^>]*/>", "", text, flags=re.IGNORECASE)

    # Then remove paired ref tags: <ref ...>content</ref>
    # The opening tag must NOT end with />, so we use a negative lookahead
    text = re.sub(r"<ref(?:(?!/>)[^>])*>(?:.*?)</ref>", "", text, flags=re.IGNORECASE | re.DOTALL)

    return text


def is_reference_only_edit(
    parent_wikitext: str, pending_wikitext: str
) -> tuple[bool, bool, list[str]]:
    """Check if edit only modifies references without changing other content.

    Returns:
        tuple: (is_reference_only, has_removals, added_or_modified_refs)
            - is_reference_only: True if only references changed
            - has_removals: True if any references were removed
            - added_or_modified_refs: List of new/modified reference content
    """
    if not pending_wikitext:
        return False, False, []

    parent_without_refs = strip_references(parent_wikitext or "")
    pending_without_refs = strip_references(pending_wikitext)

    # Don't normalize whitespace too aggressively - preserve structure
    # Only collapse consecutive spaces/tabs on the same line
    parent_normalized = re.sub(r"[ \t]+", " ", parent_without_refs).strip()
    pending_normalized = re.sub(r"[ \t]+", " ", pending_without_refs).strip()

    if parent_normalized != pending_normalized:
        return False, False, []

    parent_refs = set(extract_references(parent_wikitext or ""))
    pending_refs = set(extract_references(pending_wikitext))

    if not parent_refs and not pending_refs:
        return False, False, []

    has_removals = len(parent_refs - pending_refs) > 0
    added_or_modified = list(pending_refs - parent_refs)

    if not added_or_modified and not has_removals:
        return False, False, []

    return True, has_removals, added_or_modified


def extract_urls_from_references(references: list[str]) -> list[str]:
    """Extract all URLs from reference tags."""
    urls = []
    url_pattern = r'https?://[^\s\]<>"\'\|\{\}]+(?:\([^\s\)]*\))?'

    for ref in references:
        for match in re.finditer(url_pattern, ref, re.IGNORECASE):
            url = match.group(0)
            url = url.rstrip(".,;:!?}")
            urls.append(url)

    return urls


def extract_domain_from_url(url: str) -> str | None:
    """Extract domain from URL without protocol, path, or query string."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain if domain else None
    except Exception:
        logger.warning("Failed to parse URL: %s", url)
        return None
