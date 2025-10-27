from __future__ import annotations

import logging

from ..base import CheckResult
from ..context import CheckContext
from ..decision import AutoreviewDecision
from ..utils.wikitext import (
    extract_domain_from_url,
    extract_references,
    extract_urls_from_references,
    get_parent_wikitext,
    is_reference_only_edit,
)

logger = logging.getLogger(__name__)


def check_reference_only_edit(context: CheckContext) -> CheckResult:
    """Check if revision only adds or modifies references."""
    pending_wikitext = context.revision.get_wikitext()
    parent_wikitext = get_parent_wikitext(context.revision)

    if not is_reference_only_edit(parent_wikitext, pending_wikitext):
        return CheckResult(
            check_id="reference-only-edit",
            check_title="Reference-only edit detection",
            status="skip",
            message="Edit modifies content beyond references.",
        )

    parent_refs = set(extract_references(parent_wikitext or ""))
    pending_refs = set(extract_references(pending_wikitext))
    new_or_modified_refs = [ref for ref in pending_refs if ref not in parent_refs]

    if not new_or_modified_refs:
        return CheckResult(
            check_id="reference-only-edit",
            check_title="Reference-only edit detection",
            status="skip",
            message="No new or modified references detected.",
        )

    urls = extract_urls_from_references(new_or_modified_refs)

    if not urls:
        logger.info(
            "Auto-approving reference-only edit %s (no URLs in new references)",
            context.revision.revid,
        )
        ref_count = len(new_or_modified_refs)
        return CheckResult(
            check_id="reference-only-edit",
            check_title="Reference-only edit detection",
            status="ok",
            message=f"Edit only modifies references ({ref_count} reference(s) added/modified).",
            decision=AutoreviewDecision(
                status="approve",
                label="Can be auto-approved",
                reason="Edit only adds or modifies references without external URLs.",
            ),
            should_stop=True,
        )

    domains = []
    for url in urls:
        domain = extract_domain_from_url(url)
        if domain:
            domains.append(domain)

    new_domains = []
    checked_domains = set()

    for domain in domains:
        if domain in checked_domains:
            continue
        checked_domains.add(domain)

        has_been_used = context.client.has_domain_been_used(domain)

        if not has_been_used:
            new_domains.append(domain)
            logger.info(
                "Domain %s has not been used before in revision %s",
                domain,
                context.revision.revid,
            )

    if new_domains:
        domain_list = ", ".join(new_domains[:3])
        if len(new_domains) > 3:
            domain_list += "..."
        domain_count = len(new_domains)

        return CheckResult(
            check_id="reference-only-edit",
            check_title="Reference-only edit detection",
            status="not_ok",
            message=f"Edit adds references with new domain(s): {domain_list}",
            decision=AutoreviewDecision(
                status="manual",
                label="Requires manual review",
                reason=f"Reference-only edit contains {domain_count} previously unused domain(s).",
            ),
            should_stop=True,
        )

    logger.info(
        "Auto-approving reference-only edit %s with %s known domain(s)",
        context.revision.revid,
        len(checked_domains),
    )
    ref_count = len(new_or_modified_refs)
    domain_count = len(checked_domains)
    return CheckResult(
        check_id="reference-only-edit",
        check_title="Reference-only edit detection",
        status="ok",
        message=f"Edit only modifies references ({ref_count} reference(s) with "
        f"{domain_count} known domain(s)).",
        decision=AutoreviewDecision(
            status="approve",
            label="Can be auto-approved",
            reason="Edit only adds or modifies references with known domains.",
        ),
        should_stop=True,
    )
