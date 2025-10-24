from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision


def check_manual_unapproval(context: CheckContext) -> CheckResult:
    """Check if revision was manually un-approved."""
    is_manually_unapproved = context.client.has_manual_unapproval(
        context.revision.page.title, context.revision.revid
    )

    if is_manually_unapproved:
        return CheckResult(
            check_id="manual-unapproval",
            check_title="Manual un-approval check",
            status="fail",
            message=(
                "This revision was manually un-approved by a human reviewer "
                "and should not be auto-approved."
            ),
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="Revision was manually un-approved by a human reviewer.",
            ),
            should_stop=True,
        )

    return CheckResult(
        check_id="manual-unapproval",
        check_title="Manual un-approval check",
        status="ok",
        message="This revision has not been manually un-approved.",
    )
