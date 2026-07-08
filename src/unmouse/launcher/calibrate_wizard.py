"""Sixteen-point offset calibration wizard with fullscreen target overlay."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from unmouse.broker.video_broker import FrameSource
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
from unmouse.gaze.tracker import GazeTracker
from unmouse.launcher.wizard_common import (
    GazeSample,
    StareCalibrationRunner,
    WizardOverlayBackend,
    WizardTarget,
    geometric_mean_gaze,
    run_stare_wizard,
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


class OffsetWizardRunner(StareCalibrationRunner):
    def __init__(
        self,
        settings: Settings,
        calibration: CalibrationModel,
        *,
        targets: Sequence[OffsetTarget] | None = None,
    ) -> None:
        resolved = tuple(
            targets
            or build_offset_targets(settings.screen_width, settings.screen_height),
        )
        if len(resolved) != NUM_OFFSET_TARGETS:
            msg = f"expected {NUM_OFFSET_TARGETS} calibration targets"
            raise ValueError(msg)
        super().__init__(
            targets=resolved,
            point_duration_s=settings.calibration_point_duration_s,
            discard_s=settings.calibration_discard_s,
        )
        self._settings = settings
        self._calibration = calibration
        self._measurements: list[tuple[float, float]] = []

    @property
    def outcome(self) -> OffsetWizardOutcome | None:
        return self._outcome  # type: ignore[return-value]

    def finish_from_measurements(
        self,
        measurements: Sequence[tuple[float, float]],
    ) -> OffsetWizardOutcome:
        if len(measurements) != NUM_OFFSET_TARGETS:
            msg = f"expected {NUM_OFFSET_TARGETS} gaze measurements"
            raise ValueError(msg)
        self._measurements = list(measurements)
        self._index = len(self._targets)
        self._outcome = self.evaluate()
        return self._outcome

    def on_point_complete(self, samples: Sequence[GazeSample], _target: WizardTarget) -> None:
        measured_x, measured_y = calibrated_mean_gaze(samples, self._calibration)
        self._measurements.append((measured_x, measured_y))

    def evaluate(self) -> OffsetWizardOutcome:
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
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    prefer_win32_overlay: bool = True,
) -> OffsetWizardOutcome:
    import time

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
    outcome = run_stare_wizard(
        settings,
        runner,
        target_label=lambda target: f"Look here ({target.index + 1}/{NUM_OFFSET_TARGETS})",
        tracker=tracker,
        frame_source=frame_source,
        overlay=overlay,
        sleep=sleep or time.sleep,
        clock=clock or time.perf_counter,
        prefer_win32_overlay=prefer_win32_overlay,
        incomplete_message="wizard ended before collecting all offset calibration points",
    )
    assert isinstance(outcome, OffsetWizardOutcome)
    return outcome
