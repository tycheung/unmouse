from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from unmouse.broker.video_broker import FrameSource
from unmouse.config import Settings
from unmouse.gaze.calibration import (
    CalibrationModel,
    PointPair,
    apply_calibration,
    calibration_path,
    fit_calibration,
    load_calibration,
    mean_residual_error,
    save_calibration,
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
    build_square_grid_positions,
    geometric_mean_gaze,
    run_stare_wizard,
)

NUM_POLY_TARGETS = 9
NUM_OFFSET_TARGETS = NUM_SAMPLES
GRID_SIZE = 3
DEFAULT_TARGET_INSET = 0.05


@dataclass(frozen=True)
class CalibrationTarget:
    index: int
    x: float
    y: float


@dataclass(frozen=True)
class PolynomialWizardOutcome:
    success: bool
    model: CalibrationModel | None
    residual_px: float
    message: str
    retry_recommended: bool


@dataclass(frozen=True)
class OffsetWizardOutcome:
    success: bool
    message: str
    mean_error_px: float = 0.0


class PolynomialWizardRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        targets: Sequence[CalibrationTarget] | None = None,
        max_residual_px: float | None = None,
    ) -> None:
        resolved = tuple(
            targets or build_polynomial_targets(
                settings.screen_width,
                settings.screen_height,
            ),
        )
        if len(resolved) != NUM_POLY_TARGETS:
            msg = f"expected {NUM_POLY_TARGETS} calibration targets"
            raise ValueError(msg)
        self._max_residual_px = max_residual_px or settings.calibration_max_residual_px
        self._points: list[PointPair] = []
        self._runner = StareCalibrationRunner(
            targets=resolved,
            point_duration_s=settings.calibration_point_duration_s,
            discard_s=settings.calibration_discard_s,
            on_point_complete=self._record_point,
            evaluate=self._evaluate,
        )

    @property
    def done(self) -> bool:
        return self._runner.done

    @property
    def current_index(self) -> int:
        return self._runner.current_index

    @property
    def outcome(self) -> PolynomialWizardOutcome | None:
        value = self._runner.outcome
        return value if isinstance(value, PolynomialWizardOutcome) else None

    def begin_point(self, timestamp_s: float) -> WizardTarget:
        return self._runner.begin_point(timestamp_s)

    def add_sample(self, sample: GazeSample) -> bool:
        return self._runner.add_sample(sample)

    def finish_from_pairs(self, pairs: Sequence[PointPair]) -> PolynomialWizardOutcome:
        if len(pairs) != NUM_POLY_TARGETS:
            msg = f"expected {NUM_POLY_TARGETS} point pairs"
            raise ValueError(msg)
        self._points = list(pairs)
        self._runner._index = len(self._runner._targets)
        self._runner._outcome = self._evaluate()
        outcome = self.outcome
        assert outcome is not None
        return outcome

    def _record_point(self, samples: Sequence[GazeSample], target: WizardTarget) -> None:
        raw_x, raw_y = geometric_mean_gaze(samples)
        self._points.append((raw_x, raw_y, target.x, target.y))

    def _evaluate(self) -> PolynomialWizardOutcome:
        model = fit_calibration(self._points)
        residual = mean_residual_error(self._points, model)
        if residual > self._max_residual_px:
            return PolynomialWizardOutcome(
                success=False,
                model=model,
                residual_px=residual,
                message=(
                    f"Calibration residual {residual:.1f}px exceeds "
                    f"{self._max_residual_px:.1f}px. Adjust lighting and retry."
                ),
                retry_recommended=True,
            )
        return PolynomialWizardOutcome(
            success=True,
            model=model,
            residual_px=residual,
            message=f"Calibration saved with {residual:.1f}px average error.",
            retry_recommended=False,
        )


class OffsetWizardRunner:
    def __init__(
        self,
        settings: Settings,
        calibration: CalibrationModel,
        *,
        targets: Sequence[CalibrationTarget] | None = None,
    ) -> None:
        resolved = tuple(
            targets
            or build_offset_targets(settings.screen_width, settings.screen_height),
        )
        if len(resolved) != NUM_OFFSET_TARGETS:
            msg = f"expected {NUM_OFFSET_TARGETS} calibration targets"
            raise ValueError(msg)
        self._settings = settings
        self._calibration = calibration
        self._measurements: list[tuple[float, float]] = []
        self._runner = StareCalibrationRunner(
            targets=resolved,
            point_duration_s=settings.calibration_point_duration_s,
            discard_s=settings.calibration_discard_s,
            on_point_complete=self._record_measurement,
            evaluate=self._evaluate,
        )

    @property
    def done(self) -> bool:
        return self._runner.done

    @property
    def current_index(self) -> int:
        return self._runner.current_index

    @property
    def outcome(self) -> OffsetWizardOutcome | None:
        value = self._runner.outcome
        return value if isinstance(value, OffsetWizardOutcome) else None

    def begin_point(self, timestamp_s: float) -> WizardTarget:
        return self._runner.begin_point(timestamp_s)

    def add_sample(self, sample: GazeSample) -> bool:
        return self._runner.add_sample(sample)

    def finish_from_measurements(
        self,
        measurements: Sequence[tuple[float, float]],
    ) -> OffsetWizardOutcome:
        if len(measurements) != NUM_OFFSET_TARGETS:
            msg = f"expected {NUM_OFFSET_TARGETS} gaze measurements"
            raise ValueError(msg)
        self._measurements = list(measurements)
        self._runner._index = len(self._runner._targets)
        self._runner._outcome = self._evaluate()
        outcome = self.outcome
        assert outcome is not None
        return outcome

    def _record_measurement(self, samples: Sequence[GazeSample], _target: WizardTarget) -> None:
        measured_x, measured_y = calibrated_mean_gaze(samples, self._calibration)
        self._measurements.append((measured_x, measured_y))

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
                self._runner._targets,
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


def build_polynomial_targets(
    screen_width: float,
    screen_height: float,
    *,
    inset: float = DEFAULT_TARGET_INSET,
) -> tuple[CalibrationTarget, ...]:
    positions = build_square_grid_positions(
        screen_width,
        screen_height,
        grid_size=GRID_SIZE,
        inset=inset,
    )
    return tuple(
        CalibrationTarget(index=index, x=x, y=y)
        for index, (x, y) in enumerate(positions)
    )


def build_offset_targets(
    screen_width: float,
    screen_height: float,
) -> tuple[CalibrationTarget, ...]:
    positions = build_calibration_targets(screen_width, screen_height)
    return tuple(
        CalibrationTarget(index=index, x=x, y=y)
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


def _run_stare_calibration(
    settings: Settings,
    runner: StareCalibrationRunner,
    *,
    target_count: int,
    incomplete_message: str,
    tracker: Any = None,
    frame_source: FrameSource | None = None,
    overlay: WizardOverlayBackend | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    prefer_win32_overlay: bool = True,
) -> object:
    import time

    return run_stare_wizard(
        settings,
        runner,
        target_label=lambda target: f"Look here ({target.index + 1}/{target_count})",
        tracker=tracker,
        frame_source=frame_source,
        overlay=overlay,
        sleep=sleep or time.sleep,
        clock=clock or time.perf_counter,
        prefer_win32_overlay=prefer_win32_overlay,
        incomplete_message=incomplete_message,
    )


def run_polynomial_wizard(
    settings: Settings,
    *,
    tracker: Any = None,
    frame_source: Any = None,
    overlay: Any = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    max_residual_px: float | None = None,
    prefer_win32_overlay: bool = True,
) -> PolynomialWizardOutcome:
    wizard = PolynomialWizardRunner(settings, max_residual_px=max_residual_px)
    outcome = _run_stare_calibration(
        settings,
        wizard._runner,
        target_count=NUM_POLY_TARGETS,
        tracker=tracker,
        frame_source=frame_source,
        overlay=overlay,
        sleep=sleep,
        clock=clock,
        prefer_win32_overlay=prefer_win32_overlay,
        incomplete_message="wizard ended before collecting all calibration points",
    )
    assert isinstance(outcome, PolynomialWizardOutcome)
    if outcome.success and outcome.model is not None:
        save_calibration(calibration_path(settings), outcome.model)
    return outcome


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
    missing = polynomial_prerequisite_message(settings)
    if missing is not None:
        return OffsetWizardOutcome(success=False, message=missing)
    model = calibration or load_calibration(calibration_path(settings))
    if model is None:
        return OffsetWizardOutcome(
            success=False,
            message="Complete 9-point polynomial calibration before offset calibration.",
        )

    wizard = OffsetWizardRunner(settings, model)
    outcome = _run_stare_calibration(
        settings,
        wizard._runner,
        target_count=NUM_OFFSET_TARGETS,
        tracker=tracker,
        frame_source=frame_source,
        overlay=overlay,
        sleep=sleep,
        clock=clock,
        prefer_win32_overlay=prefer_win32_overlay,
        incomplete_message="wizard ended before collecting all offset calibration points",
    )
    assert isinstance(outcome, OffsetWizardOutcome)
    return outcome
