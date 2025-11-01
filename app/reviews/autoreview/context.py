from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reviews.models import EditorProfile, PendingRevision, WikiConfiguration
    from reviews.services import WikiClient


@dataclass
class CheckContext:
    """Shared context passed to all check functions."""

    revision: PendingRevision
    client: WikiClient | None = None
    profile: EditorProfile | None = None
    auto_groups: dict[str, str] | None = None
    blocking_categories: dict[str, str] | None = None
    redirect_aliases: list[str] | None = None
    config: WikiConfiguration | None = None
