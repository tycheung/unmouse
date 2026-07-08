from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from unmouse.broker.video_broker import FrameSource, create_frame_source
from unmouse.config import Settings
from unmouse.gaze.tracker import GazeTracker, create_gaze_tracker, save_gaze_model
from unmouse.launcher.api_helpers import ActionResult
from unmouse.launcher.wizard_common import WizardOverlayBackend, create_calibration_overlay

MAX_FRAMES_PER_POINT = 240


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
