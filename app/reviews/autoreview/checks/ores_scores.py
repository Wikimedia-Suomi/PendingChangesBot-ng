from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.ores import get_ores_scores, get_ores_thresholds


def check_ores_scores(context: CheckContext) -> CheckResult:
    """Check ORES damaging and goodfaith scores."""
    damaging_threshold, goodfaith_threshold = get_ores_thresholds(context.revision)

    check_damaging = damaging_threshold > 0
    check_goodfaith = goodfaith_threshold > 0

    if not check_damaging and not check_goodfaith:
        return CheckResult(
            check_id="ores-scores",
            check_title="ORES edit quality scores",
            status="skip",
            message="ORES checks are disabled (thresholds set to 0).",
        )

    damaging_prob, goodfaith_prob = get_ores_scores(
        context.revision, check_damaging, check_goodfaith
    )

    if damaging_prob is None and goodfaith_prob is None:
        return CheckResult(
            check_id="ores-scores",
            check_title="ORES edit quality check failed",
            status="fail",
            message="Could not verify ORES edit quality scores.",
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="ORES edit quality scores indicate potential issues.",
            ),
            should_stop=True,
        )

    if damaging_threshold > 0 and damaging_prob is not None:
        if damaging_prob > damaging_threshold:
            return CheckResult(
                check_id="ores-scores",
                check_title="ORES edit quality scores",
                status="fail",
                message=(
                    f"ORES damaging score ({damaging_prob:.3f}) "
                    f"exceeds threshold ({damaging_threshold:.3f})."
                ),
                decision=AutoreviewDecision(
                    status="blocked",
                    label="Cannot be auto-approved",
                    reason="ORES edit quality scores indicate potential issues.",
                ),
                should_stop=True,
            )

    if goodfaith_threshold > 0 and goodfaith_prob is not None:
        if goodfaith_prob < goodfaith_threshold:
            return CheckResult(
                check_id="ores-scores",
                check_title="ORES edit quality scores",
                status="fail",
                message=(
                    f"ORES goodfaith score ({goodfaith_prob:.3f}) "
                    f"is below threshold ({goodfaith_threshold:.3f})."
                ),
                decision=AutoreviewDecision(
                    status="blocked",
                    label="Cannot be auto-approved",
                    reason="ORES edit quality scores indicate potential issues.",
                ),
                should_stop=True,
            )

    messages = []
    if damaging_threshold > 0 and damaging_prob is not None:
        messages.append(f"damaging: {damaging_prob:.3f}")
    if goodfaith_threshold > 0 and goodfaith_prob is not None:
        messages.append(f"goodfaith: {goodfaith_prob:.3f}")

    return CheckResult(
        check_id="ores-scores",
        check_title="ORES edit quality scores",
        status="ok",
        message=f"ORES scores are within acceptable thresholds ({', '.join(messages)}).",
    )
