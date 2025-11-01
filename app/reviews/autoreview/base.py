from __future__ import annotations

from dataclasses import dataclass

from .decision import AutoreviewDecision


@dataclass
class CheckResult:
    """Result from running a single check."""

    check_id: str
    check_title: str
    status: str
    message: str
    decision: AutoreviewDecision | None = None
    should_stop: bool = False
    duration_ms: float | None = None
