from __future__ import annotations

import logging

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision

logger = logging.getLogger(__name__)


def check_user_block(context: CheckContext) -> CheckResult:
    """Check if user was blocked after making this edit."""
    try:
        if context.client.is_user_blocked_after_edit(
            context.revision.user_name, context.revision.timestamp
        ):
            return CheckResult(
                check_id="blocked-user",
                check_title="User blocked after edit",
                status="fail",
                message="User was blocked after making this edit.",
                decision=AutoreviewDecision(
                    status="blocked",
                    label="Cannot be auto-approved",
                    reason="User was blocked after making this edit.",
                ),
                should_stop=True,
            )

        return CheckResult(
            check_id="blocked-user",
            check_title="User block status",
            status="ok",
            message="User has not been blocked since making this edit.",
        )
    except Exception as e:
        logger.error(f"Error checking blocks for {context.revision.user_name}: {e}")
        return CheckResult(
            check_id="blocked-user",
            check_title="Block check failed",
            status="fail",
            message="Could not verify user block status.",
            decision=AutoreviewDecision(
                status="error",
                label="Cannot be auto-approved",
                reason="Unable to verify user was not blocked.",
            ),
            should_stop=True,
        )
