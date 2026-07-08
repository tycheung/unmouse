"""Shared action result type for launcher and onboarding flows."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    step_complete: bool = False
    gesture: str | None = None
    sample_count: int = 0
    done: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
