from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RevisionPayload:
    revid: int
    parentid: int | None
    user: str | None
    userid: int | None
    timestamp: datetime
    comment: str
    sha1: str
    tags: list[str]
    superset_data: dict | None = None
