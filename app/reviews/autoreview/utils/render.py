from __future__ import annotations

from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from reviews.models import PendingRevision
    from reviews.services import WikiClient


def get_render_error_count(revision: PendingRevision, html: str) -> int:
    """Calculate and cache the number of rendering errors in the HTML."""
    if revision.render_error_count is not None:
        return revision.render_error_count

    soup = BeautifulSoup(html, "lxml")
    error_count = len(soup.find_all(class_="error"))

    revision.render_error_count = error_count
    revision.save(update_fields=["render_error_count"])
    return error_count


def check_for_new_render_errors(revision: PendingRevision, client: WikiClient) -> bool:
    """Check if a revision introduces new HTML elements with class='error'."""
    if not revision.parentid:
        return False

    current_html = client.get_rendered_html(revision.revid)
    previous_html = client.get_rendered_html(revision.parentid)

    if not current_html or not previous_html:
        return False

    current_error_count = get_render_error_count(revision, current_html)

    from reviews.models import PendingRevision as PR

    parent_revision = PR.objects.filter(
        page__wiki=revision.page.wiki, revid=revision.parentid
    ).first()
    previous_error_count = (
        get_render_error_count(parent_revision, previous_html) if parent_revision else 0
    )

    return current_error_count > previous_error_count
