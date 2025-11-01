"""Lift Wing ML model scores check."""

from __future__ import annotations

from ...liftwing_utils import get_liftwing_score, get_liftwing_thresholds
from ...ml_model_compatibility import get_incompatibility_reason, is_model_compatible
from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision


def check_liftwing_scores(context: CheckContext) -> CheckResult:
    """Check Lift Wing ML model scores."""
    configuration = context.revision.page.wiki.configuration
    model_type = configuration.ml_model_type
    threshold = configuration.ml_model_threshold

    # Skip if disabled
    if threshold <= 0:
        return CheckResult(
            check_id="liftwing-scores",
            check_title="Lift Wing ML model check",
            status="skip",
            message="Lift Wing ML checks are disabled (threshold set to 0).",
        )

    # Check language compatibility
    wiki_lang = context.revision.page.wiki.code
    if not is_model_compatible(model_type, wiki_lang):
        reason = get_incompatibility_reason(model_type, wiki_lang)
        return CheckResult(
            check_id="liftwing-scores",
            check_title="Lift Wing ML model check",
            status="skip",
            message=f"Model incompatible: {reason}",
        )

    # Fetch score
    score = get_liftwing_score(context.revision, model_type)
    _, display_name = get_liftwing_thresholds(context.revision, model_type)

    if score is None:
        return CheckResult(
            check_id="liftwing-scores",
            check_title=f"Lift Wing ML ({display_name})",
            status="fail",
            message=f"Could not fetch {model_type} score from Lift Wing API.",
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason=f"Failed to verify {model_type} score from Lift Wing ML.",
            ),
            should_stop=True,
        )

    # Check threshold
    if score > threshold:
        return CheckResult(
            check_id="liftwing-scores",
            check_title=f"Lift Wing ML ({display_name})",
            status="fail",
            message=f"{model_type} score ({score:.3f}) exceeds threshold ({threshold:.3f}).",
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason=f"High {model_type} score from Lift Wing ML indicates potential issues.",
            ),
            should_stop=True,
        )

    # Passed
    return CheckResult(
        check_id="liftwing-scores",
        check_title=f"Lift Wing ML ({display_name})",
        status="ok",
        message=f"{model_type} score ({score:.3f}) is within acceptable threshold ({threshold:.3f}).",
    )
