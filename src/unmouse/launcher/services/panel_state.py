from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from unmouse.config import Settings
from unmouse.launcher.enroll_ui import GestureEnrollmentSession
from unmouse.launcher.update import UpdateStatus

PanelView = Literal["main", "settings", "onboarding", "enrollment"]


@dataclass
class PanelStatus:
    message: str
    fps: float | None = None
    confidence: float | None = None
    tracking: bool = False
    paused: bool = False
    gaze_mode: str = "cursor_follow"
    last_calibrated: str | None = None


@dataclass
class PanelState:
    settings: Settings
    view: PanelView = "main"
    status: PanelStatus = field(default_factory=lambda: PanelStatus(message="Ready"))
    enrollment: GestureEnrollmentSession | None = None
    enrollment_return_view: PanelView = "main"
    update_status: UpdateStatus | None = None
