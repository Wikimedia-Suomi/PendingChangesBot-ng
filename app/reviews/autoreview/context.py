from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reviews.models import EditorProfile, PendingRevision
    from reviews.services import WikiClient


@dataclass
class CheckContext:
    """Shared context passed to all check functions."""

    revision: PendingRevision
    client: WikiClient
    profile: EditorProfile | None
    auto_groups: dict[str, str]
    blocking_categories: dict[str, str]
    redirect_aliases: list[str]
