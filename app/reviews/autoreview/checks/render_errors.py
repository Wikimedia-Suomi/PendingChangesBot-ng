from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.render import check_for_new_render_errors


def check_render_errors(context: CheckContext) -> CheckResult:
    """Check if revision introduces new rendering errors."""
    new_render_errors = check_for_new_render_errors(context.revision, context.client)

    if new_render_errors:
        return CheckResult(
            check_id="new-render-errors",
            check_title="New render errors",
            status="fail",
            message="The edit introduces new rendering errors.",
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="The edit introduces new rendering errors.",
            ),
            should_stop=True,
        )

    return CheckResult(
        check_id="new-render-errors",
        check_title="New render errors",
        status="ok",
        message="The edit does not introduce new rendering errors.",
    )
