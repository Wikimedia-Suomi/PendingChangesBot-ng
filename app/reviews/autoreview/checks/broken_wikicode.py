"""Check for broken wikicode indicators in revisions."""

from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.broken_wikicode import check_broken_wikicode, get_parent_html


def check_broken_wikicode_indicators(context: CheckContext) -> CheckResult:
    """
    Check if the revision introduces broken wikicode indicators.

    This detects when edits introduce visible wikicode or HTML markup that should
    be hidden. The system checks for common indicators like {{, [[, <ref>, <div>,
    <span>, and other similar patterns that appear as plain text instead of being
    properly rendered.

    Only flags NEW broken wikicode by comparing current revision with parent revision.
    """
    # Get rendered HTML for current revision
    current_html = context.revision.get_rendered_html()

    # If we can't get rendered HTML, skip the check
    if not current_html:
        return CheckResult(
            check_id="broken-wikicode",
            check_title="Broken wikicode indicators",
            status="ok",
            message="Could not fetch rendered HTML for analysis.",
        )

    # Get parent revision HTML if available
    parent_html = None
    if context.revision.parentid:
        parent_html = get_parent_html(context.revision)

    # Check for broken wikicode
    has_broken, details = check_broken_wikicode(
        current_html=current_html,
        parent_html=parent_html,
        wiki_lang=context.revision.page.wiki.code,
    )

    if has_broken:
        return CheckResult(
            check_id="broken-wikicode",
            check_title="Broken wikicode indicators",
            status="fail",
            message=details,
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason=details,
            ),
            should_stop=True,
        )

    return CheckResult(
        check_id="broken-wikicode",
        check_title="Broken wikicode indicators",
        status="ok",
        message="No broken wikicode indicators detected.",
    )
