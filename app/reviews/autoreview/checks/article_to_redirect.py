from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.redirect import is_redirect
from ..utils.wikitext import get_parent_wikitext


def check_article_to_redirect(context: CheckContext) -> CheckResult:
    """Check if revision converts an article to a redirect."""
    current_wikitext = context.revision.get_wikitext()

    if not is_redirect(current_wikitext, context.redirect_aliases):
        return CheckResult(
            check_id="article-to-redirect-conversion",
            check_title="Article-to-redirect conversion",
            status="ok",
            message="This is not an article-to-redirect conversion.",
        )

    if not context.revision.parentid:
        return CheckResult(
            check_id="article-to-redirect-conversion",
            check_title="Article-to-redirect conversion",
            status="ok",
            message="This is not an article-to-redirect conversion.",
        )

    parent_wikitext = get_parent_wikitext(context.revision)
    if parent_wikitext and not is_redirect(parent_wikitext, context.redirect_aliases):
        return CheckResult(
            check_id="article-to-redirect-conversion",
            check_title="Article-to-redirect conversion",
            status="fail",
            message="Converting articles to redirects requires autoreview rights.",
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="Article-to-redirect conversions require autoreview rights.",
            ),
            should_stop=True,
        )

    return CheckResult(
        check_id="article-to-redirect-conversion",
        check_title="Article-to-redirect conversion",
        status="ok",
        message="This is not an article-to-redirect conversion.",
    )
