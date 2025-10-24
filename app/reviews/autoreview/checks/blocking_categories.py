from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.categories import blocking_category_hits


def check_blocking_categories(context: CheckContext) -> CheckResult:
    """Check if revision belongs to blocking categories."""
    blocking_hits = blocking_category_hits(context.revision, context.blocking_categories)

    if blocking_hits:
        return CheckResult(
            check_id="blocking-categories",
            check_title="Blocking categories",
            status="fail",
            message="The previous version belongs to blocking categories: {}.".format(
                ", ".join(sorted(blocking_hits))
            ),
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="The previous version belongs to blocking categories.",
            ),
            should_stop=True,
        )

    return CheckResult(
        check_id="blocking-categories",
        check_title="Blocking categories",
        status="ok",
        message="The previous version is not in blocking categories.",
    )
