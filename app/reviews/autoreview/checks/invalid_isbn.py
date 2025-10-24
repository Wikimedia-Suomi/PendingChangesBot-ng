from __future__ import annotations

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.isbn import find_invalid_isbns


def check_invalid_isbn(context: CheckContext) -> CheckResult:
    """Check if revision contains invalid ISBNs."""
    wikitext = context.revision.get_wikitext()
    invalid_isbns = find_invalid_isbns(wikitext)

    if invalid_isbns:
        return CheckResult(
            check_id="invalid-isbn",
            check_title="ISBN checksum validation",
            status="fail",
            message="The edit contains invalid ISBN(s): {}.".format(", ".join(invalid_isbns)),
            decision=AutoreviewDecision(
                status="blocked",
                label="Cannot be auto-approved",
                reason="The edit contains ISBN(s) with invalid checksums.",
            ),
            should_stop=True,
        )

    return CheckResult(
        check_id="invalid-isbn",
        check_title="ISBN checksum validation",
        status="ok",
        message="No invalid ISBNs detected.",
    )
