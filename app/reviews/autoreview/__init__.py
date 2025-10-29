from __future__ import annotations

# Backwards-compatibility exports for older test imports
from pywikibot.data.superset import SupersetQuery  # re-export for tests

from .checks.revert_detection import (
    _find_reviewed_revisions_by_sha1,
    _parse_revert_params,
    check_revert_detection,
)
from .context import CheckContext


def _check_revert_detection(revision, client):
    """Compatibility wrapper matching legacy signature used in tests."""
    context = CheckContext(
        revision=revision,
        client=client,
        profile=None,
        auto_groups={},
        blocking_categories={},
        redirect_aliases=[],
    )
    return check_revert_detection(context)


__all__ = [
    "SupersetQuery",
    "_check_revert_detection",
    "_find_reviewed_revisions_by_sha1",
    "_parse_revert_params",
]