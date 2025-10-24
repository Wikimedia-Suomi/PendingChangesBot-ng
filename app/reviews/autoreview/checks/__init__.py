from __future__ import annotations

from .article_to_redirect import check_article_to_redirect
from .auto_approved_groups import check_auto_approved_groups
from .blocking_categories import check_blocking_categories
from .bot_user import check_bot_user
from .broken_wikicode import check_broken_wikicode_indicators
from .invalid_isbn import check_invalid_isbn
from .manual_unapproval import check_manual_unapproval
from .ores_scores import check_ores_scores
from .render_errors import check_render_errors
from .superseded_additions import check_superseded_additions
from .user_block import check_user_block

AVAILABLE_CHECKS = [
    {
        "id": "broken-wikicode",
        "name": "Broken wikicode indicators",
        "function": check_broken_wikicode_indicators,
        "priority": 0,
    },
    {
        "id": "manual-unapproval",
        "name": "Manual un-approval check",
        "function": check_manual_unapproval,
        "priority": 1,
    },
    {
        "id": "bot-user",
        "name": "Bot user",
        "function": check_bot_user,
        "priority": 2,
    },
    {
        "id": "blocked-user",
        "name": "User block status",
        "function": check_user_block,
        "priority": 3,
    },
    {
        "id": "auto-approved-group",
        "name": "Auto-approved groups",
        "function": check_auto_approved_groups,
        "priority": 4,
    },
    {
        "id": "article-to-redirect-conversion",
        "name": "Article-to-redirect conversion",
        "function": check_article_to_redirect,
        "priority": 5,
    },
    {
        "id": "blocking-categories",
        "name": "Blocking categories",
        "function": check_blocking_categories,
        "priority": 6,
    },
    {
        "id": "new-render-errors",
        "name": "New render errors",
        "function": check_render_errors,
        "priority": 7,
    },
    {
        "id": "invalid-isbn",
        "name": "ISBN checksum validation",
        "function": check_invalid_isbn,
        "priority": 8,
    },
    {
        "id": "superseded-additions",
        "name": "Superseded additions",
        "function": check_superseded_additions,
        "priority": 9,
    },
    {
        "id": "ores-scores",
        "name": "ORES edit quality scores",
        "function": check_ores_scores,
        "priority": 10,
    },
]


def get_all_checks():
    """Get all available checks sorted by priority."""
    return sorted(AVAILABLE_CHECKS, key=lambda c: c["priority"])


def get_check_by_id(check_id: str):
    """Get a specific check by ID."""
    return next((c for c in AVAILABLE_CHECKS if c["id"] == check_id), None)


def get_enabled_checks(wiki_config):
    """Get checks that should run based on wiki configuration."""
    if not hasattr(wiki_config, "enabled_checks"):
        return get_all_checks()

    enabled = wiki_config.enabled_checks
    if enabled is None or (isinstance(enabled, list) and len(enabled) == 0):
        return get_all_checks()

    return [c for c in get_all_checks() if c["id"] in enabled]
