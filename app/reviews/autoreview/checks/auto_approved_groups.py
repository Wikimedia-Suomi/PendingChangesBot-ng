from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.user import matched_user_groups


def check_auto_approved_groups(context: CheckContext) -> CheckResult:
    """Check if user belongs to auto-approved groups."""
    if context.auto_groups:
        matched_groups = matched_user_groups(
            context.revision, context.profile, allowed_groups=context.auto_groups
        )
        if matched_groups:
            return CheckResult(
                check_id="auto-approved-group",
                check_title="Auto-approved groups",
                status="ok",
                message="The user belongs to groups: {}.".format(", ".join(sorted(matched_groups))),
                decision=AutoreviewDecision(
                    status="approve",
                    label="Would be auto-approved",
                    reason="The user belongs to groups that are auto-approved.",
                ),
                should_stop=True,
            )

        return CheckResult(
            check_id="auto-approved-group",
            check_title="Auto-approved groups",
            status="not_ok",
            message="The user does not belong to auto-approved groups.",
        )
    elif context.profile and context.profile.is_autoreviewed:
        return CheckResult(
            check_id="auto-approved-group",
            check_title="Auto-approved groups",
            status="ok",
            message="The user has default auto-approval rights: Autoreviewed.",
            decision=AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The user has autoreview rights that allow auto-approval.",
            ),
            should_stop=True,
        )
    else:
        return CheckResult(
            check_id="auto-approved-group",
            check_title="Auto-approved groups",
            status="not_ok",
            message=(
                "The user does not have autoreview rights."
                if context.profile and context.profile.is_autopatrolled
                else "The user does not have default auto-approval rights."
            ),
        )
