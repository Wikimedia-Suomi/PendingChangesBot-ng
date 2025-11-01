from __future__ import annotations

# Re-export for test compatibility
from pywikibot.data.superset import SupersetQuery

# Re-export revert detection functions for backward compatibility with tests
from .checks.revert_detection import (
    _find_reviewed_revisions_by_sha1,
    _parse_revert_params,
    check_revert_detection,
)

# Alias for backward compatibility
_check_revert_detection = check_revert_detection

__all__ = [
    "check_revert_detection",
    "_check_revert_detection",
    "_find_reviewed_revisions_by_sha1",
    "_parse_revert_params",
    "SupersetQuery",
]
