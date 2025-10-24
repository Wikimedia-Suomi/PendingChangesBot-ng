from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.user import is_bot_user


def check_bot_user(context: CheckContext) -> CheckResult:
    """Check if user is a bot."""
    if is_bot_user(context.revision, context.profile):
        return CheckResult(
            check_id="bot-user",
            check_title="Bot user",
            status="ok",
            message="The edit could be auto-approved because the user is a bot.",
            decision=AutoreviewDecision(
                status="approve",
                label="Would be auto-approved",
                reason="The user is recognized as a bot.",
            ),
            should_stop=True,
        )

    return CheckResult(
        check_id="bot-user",
        check_title="Bot user",
        status="not_ok",
        message="The user is not marked as a bot.",
    )
