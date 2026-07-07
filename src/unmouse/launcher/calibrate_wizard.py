"""Sixteen-point offset calibration wizard with fullscreen target overlay."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from unmouse.broker.video_broker import FrameSource, create_frame_source
from unmouse.config import Settings
from unmouse.gaze.calibration import (
    CalibrationModel,
    apply_calibration,
    calibration_path,
    load_calibration,
)
from unmouse.gaze.offset_profile import (
    NUM_SAMPLES,
    build_calibration_targets,
    build_profile_from_measurements,
    offset_profile_path,
    save_offset_profile,
)
from unmouse.gaze.tracker import GazeTracker, create_gaze_tracker
from unmouse.launcher.polynomial_wizard import (
    GazeSample,
    WizardOverlayBackend,
    create_wizard_overlay,
    filter_samples_for_point,
    geometric_mean_gaze,
)

NUM_OFFSET_TARGETS = NUM_SAMPLES


@dataclass(frozen=True)
class OffsetTarget:
    index: int
    x: float
    y: float


@dataclass(frozen=True)
class OffsetWizardOutcome:
    success: bool
    message: str
    mean_error_px: float = 0.0


class OffsetWizardRunner:
    """Collect sixteen stare samples and build an offset correction profile."""

    def __init__(
        self,
        settings: Settings,
        calibration: CalibrationModel,
        *,
        targets: Sequence[OffsetTarget] | None = None,
    ) -> None:
        self._settings = settings
        self._calibration = calibration
        self._targets = tuple(
            targets
            or build_offset_targets(settings.screen_width, settings.screen_height),
        )
        if len(self._targets) != NUM_OFFSET_TARGETS:
            msg = f"expected {NUM_OFFSET_TARGETS} calibration targets"
            raise ValueError(msg)
        self._point_duration_s = settings.calibration_point_duration_s
        self._discard_s = settings.calibration_discard_s
        self._index = 0
        self._measurements: list[tuple[float, float]] = []
        self._samples: list[GazeSample] = []
        self._point_started_s: float | None = None
        self._outcome: OffsetWizardOutcome | None = None

    @property
    def done(self) -> bool:
        return self._outcome is not None

    @property
    def outcome(self) -> OffsetWizardOutcome | None:
        return self._outcome

    @property
    def current_target(self) -> OffsetTarget | None:
        if self.done or self._index >= len(self._targets):
            return None
        return self._targets[self._index]

    @property
    def current_index(self) -> int:
        return self._index

    def begin_point(self, timestamp_s: float) -> OffsetTarget:
        if self.done:
            msg = "wizard already finished"
            raise RuntimeError(msg)
        target = self.current_target
        if target is None:
            msg = "no remaining calibration targets"
            raise RuntimeError(msg)
        self._point_started_s = timestamp_s
        self._samples.clear()
        return target

    def add_sample(self, sample: GazeSample) -> bool:
        if self._point_started_s is None:
            msg = "call begin_point before add_sample"
            raise RuntimeError(msg)
        self._samples.append(sample)
        elapsed = sample.timestamp_s - self._point_started_s
        if elapsed < self._point_duration_s:
            return False
        self._complete_current_point()
        return True

    def finish_from_measurements(
        self,
        measurements: Sequence[tuple[float, float]],
    ) -> OffsetWizardOutcome:
        if len(measurements) != NUM_OFFSET_TARGETS:
            msg = f"expected {NUM_OFFSET_TARGETS} gaze measurements"
            raise ValueError(msg)
        self._measurements = list(measurements)
        return self._evaluate()

    def _complete_current_point(self) -> None:
        assert self._point_started_s is not None
        filtered = filter_samples_for_point(
            self._samples,
            point_started_s=self._point_started_s,
            discard_s=self._discard_s,
            point_duration_s=self._point_duration_s,
        )
        measured_x, measured_y = calibrated_mean_gaze(filtered, self._calibration)
        self._measurements.append((measured_x, measured_y))
        self._index += 1
        self._point_started_s = None
        if self._index >= NUM_OFFSET_TARGETS:
            self._outcome = self._evaluate()

    def _evaluate(self) -> OffsetWizardOutcome:
        profile = build_profile_from_measurements(
            self._settings.screen_width,
            self._settings.screen_height,
            self._measurements,
        )
        errors = [
            (
                (target.x - measured_x) ** 2 + (target.y - measured_y) ** 2
            ) ** 0.5
            for target, (measured_x, measured_y) in zip(
                self._targets,
                self._measurements,
                strict=True,
            )
        ]
        mean_error = float(sum(errors) / len(errors))
        save_offset_profile(offset_profile_path(self._settings), profile)
        return OffsetWizardOutcome(
            success=True,
            message=f"Offset profile saved ({mean_error:.1f}px average error).",
            mean_error_px=mean_error,
        )


def build_offset_targets(
    screen_width: float,
    screen_height: float,
) -> tuple[OffsetTarget, ...]:
    positions = build_calibration_targets(screen_width, screen_height)
    return tuple(
        OffsetTarget(index=index, x=x, y=y)
        for index, (x, y) in enumerate(positions)
    )


def polynomial_prerequisite_message(settings: Settings) -> str | None:
    if load_calibration(calibration_path(settings)) is None:
        return "Complete 9-point polynomial calibration before offset calibration."
    return None


def calibrated_mean_gaze(
    samples: Sequence[GazeSample],
    calibration: CalibrationModel,
) -> tuple[float, float]:
    calibrated = [
        GazeSample(
            sample.timestamp_s,
            *apply_calibration(sample.x, sample.y, calibration),
            confidence=sample.confidence,
        )
        for sample in samples
    ]
    return geometric_mean_gaze(calibrated)


def run_offset_wizard(
    settings: Settings,
    *,
    calibration: CalibrationModel | None = None,
    tracker: GazeTracker | None = None,
    frame_source: FrameSource | None = None,
    overlay: WizardOverlayBackend | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.perf_counter,
    prefer_win32_overlay: bool = True,
) -> OffsetWizardOutcome:
    """Run the full sixteen-point offset sequence and save on success."""
    missing = polynomial_prerequisite_message(settings)
    if missing is not None:
        return OffsetWizardOutcome(success=False, message=missing)
    model = calibration or load_calibration(calibration_path(settings))
    if model is None:
        return OffsetWizardOutcome(
            success=False,
            message="Complete 9-point polynomial calibration before offset calibration.",
        )

    runner = OffsetWizardRunner(settings, model)
    gaze_tracker = tracker or create_gaze_tracker(prefer_eyegestures=False)
    source = frame_source or create_frame_source(settings)
    ui = overlay or create_wizard_overlay(prefer_win32=prefer_win32_overlay)
    try:
        started = clock()
        target = runner.begin_point(started)
        ui.show_target(target.x, target.y, label=_target_label(target.index))
        while not runner.done:
            ok, frame = source.read()
            now = clock()
            if ok and frame is not None:
                gaze = gaze_tracker.predict(np.asarray(frame, dtype=np.uint8))
                if runner.add_sample(GazeSample(now, gaze.x, gaze.y, gaze.confidence)):
                    if runner.done:
                        break
                    target = runner.begin_point(now)
                    ui.show_target(target.x, target.y, label=_target_label(target.index))
            sleep(0.01)
    finally:
        ui.hide()
        source.release()

    outcome = runner.outcome
    if outcome is None:
        msg = "wizard ended before collecting all offset calibration points"
        raise RuntimeError(msg)
    return outcome


def _target_label(index: int) -> str:
    return f"Look here ({index + 1}/{NUM_OFFSET_TARGETS})"
