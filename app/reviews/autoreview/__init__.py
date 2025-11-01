from __future__ import annotations

# Re-export revert detection functions for backward compatibility with tests
from .checks.revert_detection import (
    _check_revert_detection,
    _find_reviewed_revisions_by_sha1,
    _parse_revert_params,
)

__all__ = [
    "_check_revert_detection",
    "_find_reviewed_revisions_by_sha1",
    "_parse_revert_params",
]
