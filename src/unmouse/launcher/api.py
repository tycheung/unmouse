"""JavaScript ↔ Python bridge for the control panel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from unmouse.config import Settings, get_settings

PanelView = Literal["main", "settings", "onboarding"]


@dataclass(frozen=True)
class PanelStatus:
    message: str
    fps: float | None = None
    confidence: float | None = None
    tracking: bool = False


@dataclass(frozen=True)
class PanelActionResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class UpdateCheckResult:
    available: bool
    message: str
    version: str | None = None


class PanelApi:
    """Methods exposed to Alpine.js through pywebview's js_api."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._view: PanelView = "main"
        self._status = PanelStatus(message="Ready")

    @property
    def view(self) -> PanelView:
        return self._view

    def get_status(self) -> dict[str, object]:
        return asdict(self._status)

    def get_view(self) -> dict[str, str]:
        return {"view": self._view}

    def check_for_updates(self) -> dict[str, object]:
        result = UpdateCheckResult(
            available=False,
            message="Update check not configured yet.",
        )
        return asdict(result)

    def start_calibrate(self) -> dict[str, object]:
        result = PanelActionResult(
            ok=False,
            message="Calibration wizard will run in a future epic.",
        )
        return asdict(result)

    def start_launch(self) -> dict[str, object]:
        result = PanelActionResult(
            ok=False,
            message="Engine launch will spawn the tracking process in a future epic.",
        )
        return asdict(result)

    def show_settings(self) -> dict[str, str]:
        self._view = "settings"
        return {"view": self._view}

    def show_onboarding(self) -> dict[str, str]:
        self._view = "onboarding"
        return {"view": self._view}

    def show_main(self) -> dict[str, str]:
        self._view = "main"
        return {"view": self._view}

    def set_status_message(self, message: str) -> dict[str, object]:
        self._status = PanelStatus(
            message=message,
            fps=self._status.fps,
            confidence=self._status.confidence,
            tracking=self._status.tracking,
        )
        return asdict(self._status)
