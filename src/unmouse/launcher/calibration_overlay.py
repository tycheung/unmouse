"""Fullscreen click-through overlay for calibration target dots."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from unmouse.launcher.wizard_common import FakeWizardOverlayBackend, WizardOverlayBackend
from unmouse.overlay.tk_overlay import TkFullscreenOverlay

if TYPE_CHECKING:
    import tkinter as tk

TARGET_DOT_DIAMETER = 24
TARGET_DOT_COLOR = "#FFFFFF"


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
    if prefer_win32 and sys.platform == "win32":
        return TkCalibrationOverlay()
    return FakeWizardOverlayBackend()
