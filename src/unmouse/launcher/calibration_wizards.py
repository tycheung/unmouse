from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Protocol

import numpy as np

from unmouse.broker.video_broker import FrameSource, create_frame_source
from unmouse.config import Settings
from unmouse.gaze.tracker import GazeTracker, create_gaze_tracker, save_gaze_model
from unmouse.overlay.tk_overlay import TkFullscreenOverlay
from unmouse.platform import is_windows

if TYPE_CHECKING:
    import tkinter as tk

MAX_FRAMES_PER_POINT = 240
TARGET_DOT_DIAMETER = 24
TARGET_DOT_COLOR = "#FFFFFF"


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    gesture: str | None = None
    sample_count: int = 0
    done: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WizardOverlayBackend(Protocol):
    def show_target(self, x: float, y: float, *, label: str) -> None: ...

    def hide(self) -> None: ...


@dataclass
class NoopWizardOverlayBackend:
    shown: list[tuple[float, float, str]] | None = None

    def __post_init__(self) -> None:
        if self.shown is None:
            self.shown = []

    def show_target(self, x: float, y: float, *, label: str) -> None:
        if self.shown is None:
            self.shown = []
        self.shown.append((x, y, label))

    def hide(self) -> None:
        if self.shown is not None:
            self.shown.clear()


class TkCalibrationOverlay(TkFullscreenOverlay):
    def __init__(self, *, dot_diameter: int = TARGET_DOT_DIAMETER) -> None:
        super().__init__(thread_name="calibration-overlay")
        self._diameter = dot_diameter

    def show_target(self, x: float, y: float, *, label: str) -> None:
        self.send_command((x, y, label))

    def _render(self, canvas: tk.Canvas, label_widget: tk.Label, command: object) -> None:
        if not isinstance(command, tuple) or len(command) != 3:
            return
        x, y, text = command
        canvas.delete("all")
        label_widget.config(text=str(text))
        radius = self._diameter / 2
        canvas.create_oval(
            float(x) - radius,
            float(y) - radius,
            float(x) + radius,
            float(y) + radius,
            fill=TARGET_DOT_COLOR,
            outline=TARGET_DOT_COLOR,
            width=2,
        )


def create_calibration_overlay(*, prefer_win32: bool = True) -> WizardOverlayBackend:
    if prefer_win32 and is_windows():
        return TkCalibrationOverlay()
    return NoopWizardOverlayBackend()


def run_calibration_wizard(
    settings: Settings,
    *,
    tracker: GazeTracker | None = None,
    frame_source: FrameSource | None = None,
    overlay: WizardOverlayBackend | None = None,
    sleep: Callable[[float], None] | None = None,
    prefer_win32_overlay: bool = True,
) -> ActionResult:
    wait = sleep or time.sleep
    gaze_tracker = tracker or create_gaze_tracker(settings)
    source = frame_source or create_frame_source(settings)
    ui = overlay or create_calibration_overlay(prefer_win32=prefer_win32_overlay)
    target_points = settings.gaze_calibration_points
    max_frames = target_points * MAX_FRAMES_PER_POINT
    completed = 0
    last_target: tuple[float, float] | None = None
    frames = 0
    try:
        while completed < target_points and frames < max_frames:
            ok, frame = source.read()
            frames += 1
            if ok and frame is not None:
                _sample, target = gaze_tracker.step(
                    np.asarray(frame, dtype=np.uint8), calibrate=True
                )
                if target is not None:
                    point = (target.x, target.y)
                    if point != last_target:
                        completed += 1
                        last_target = point
                        ui.show_target(
                            target.x,
                            target.y,
                            label=f"Look at the dot ({completed}/{target_points})",
                        )
            wait(0.01)
    finally:
        ui.hide()
        source.release()

    if completed < target_points:
        return ActionResult(False, "Calibration ended before all points were captured.")
    model = gaze_tracker.save_model()
    if model is None:
        return ActionResult(False, "Calibration did not produce a model. Please retry.")
    save_gaze_model(settings, model)
    return ActionResult(True, f"Calibration saved ({target_points} points).")
