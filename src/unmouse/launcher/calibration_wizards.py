from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

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
    OutcomeT,
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
OFFSET_PREREQUISITE_MESSAGE = (
    "Complete 9-point polynomial calibration before offset calibration."
)


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


def polynomial_outcome_from_pairs(
    pairs: Sequence[PointPair],
    *,
    max_residual_px: float,
) -> PolynomialWizardOutcome:
    if len(pairs) != NUM_POLY_TARGETS:
        msg = f"expected {NUM_POLY_TARGETS} point pairs"
        raise ValueError(msg)
    points = list(pairs)
    model = fit_calibration(points)
    residual = mean_residual_error(points, model)
    if residual > max_residual_px:
        return PolynomialWizardOutcome(
            success=False,
            model=model,
            residual_px=residual,
            message=(
                f"Calibration residual {residual:.1f}px exceeds "
                f"{max_residual_px:.1f}px. Adjust lighting and retry."
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


def offset_outcome_from_measurements(
    settings: Settings,
    *,
    targets: Sequence[WizardTarget],
    measurements: Sequence[tuple[float, float]],
) -> OffsetWizardOutcome:
    if len(measurements) != NUM_OFFSET_TARGETS:
        msg = f"expected {NUM_OFFSET_TARGETS} gaze measurements"
        raise ValueError(msg)
    measurements_list = list(measurements)
    profile = build_profile_from_measurements(
        settings.screen_width,
        settings.screen_height,
        measurements_list,
    )
    errors = [
        ((target.x - measured_x) ** 2 + (target.y - measured_y) ** 2) ** 0.5
        for target, (measured_x, measured_y) in zip(targets, measurements_list, strict=True)
    ]
    mean_error = float(sum(errors) / len(errors))
    save_offset_profile(offset_profile_path(settings), profile)
    return OffsetWizardOutcome(
        success=True,
        message=f"Offset profile saved ({mean_error:.1f}px average error).",
        mean_error_px=mean_error,
    )


def _create_stare_runner(
    settings: Settings,
    targets: Sequence[WizardTarget],
    *,
    expected_count: int,
    on_point_complete: Callable[[Sequence[GazeSample], WizardTarget], None],
    evaluate: Callable[[], OutcomeT],
) -> StareCalibrationRunner[OutcomeT]:
    resolved = tuple(targets)
    if len(resolved) != expected_count:
        msg = f"expected {expected_count} calibration targets"
        raise ValueError(msg)
    return StareCalibrationRunner(
        targets=resolved,
        point_duration_s=settings.calibration_point_duration_s,
        discard_s=settings.calibration_discard_s,
        on_point_complete=on_point_complete,
        evaluate=evaluate,
    )


def create_polynomial_stare_runner(
    settings: Settings,
    *,
    targets: Sequence[WizardTarget] | None = None,
    max_residual_px: float | None = None,
) -> StareCalibrationRunner[PolynomialWizardOutcome]:
    resolved = targets or build_polynomial_targets(settings.screen_width, settings.screen_height)
    max_residual = max_residual_px or settings.calibration_max_residual_px
    points: list[PointPair] = []

    def on_point_complete(samples: Sequence[GazeSample], target: WizardTarget) -> None:
        raw_x, raw_y = geometric_mean_gaze(samples)
        points.append((raw_x, raw_y, target.x, target.y))

    return _create_stare_runner(
        settings,
        resolved,
        expected_count=NUM_POLY_TARGETS,
        on_point_complete=on_point_complete,
        evaluate=lambda: polynomial_outcome_from_pairs(points, max_residual_px=max_residual),
    )


def create_offset_stare_runner(
    settings: Settings,
    calibration: CalibrationModel,
    *,
    targets: Sequence[WizardTarget] | None = None,
) -> StareCalibrationRunner[OffsetWizardOutcome]:
    resolved = targets or build_offset_targets(settings.screen_width, settings.screen_height)
    measurements: list[tuple[float, float]] = []

    def on_point_complete(samples: Sequence[GazeSample], _target: WizardTarget) -> None:
        measurements.append(calibrated_mean_gaze(samples, calibration))

    return _create_stare_runner(
        settings,
        resolved,
        expected_count=NUM_OFFSET_TARGETS,
        on_point_complete=on_point_complete,
        evaluate=lambda: offset_outcome_from_measurements(
            settings,
            targets=resolved,
            measurements=measurements,
        ),
    )


def _targets_from_positions(
    positions: Sequence[tuple[float, float]],
) -> tuple[WizardTarget, ...]:
    return tuple(
        WizardTarget(index=index, x=x, y=y) for index, (x, y) in enumerate(positions)
    )


def build_polynomial_targets(
    screen_width: float,
    screen_height: float,
    *,
    inset: float = DEFAULT_TARGET_INSET,
) -> tuple[WizardTarget, ...]:
    return _targets_from_positions(
        build_square_grid_positions(
            screen_width,
            screen_height,
            grid_size=GRID_SIZE,
            inset=inset,
        )
    )


def build_offset_targets(
    screen_width: float,
    screen_height: float,
) -> tuple[WizardTarget, ...]:
    return _targets_from_positions(build_calibration_targets(screen_width, screen_height))


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


def _look_here_label(target_count: int) -> Callable[[WizardTarget], str]:
    return lambda target: f"Look here ({target.index + 1}/{target_count})"


def run_polynomial_wizard(
    settings: Settings,
    *,
    tracker: GazeTracker | None = None,
    frame_source: FrameSource | None = None,
    overlay: WizardOverlayBackend | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    max_residual_px: float | None = None,
    prefer_win32_overlay: bool = True,
) -> PolynomialWizardOutcome:
    outcome = run_stare_wizard(
        settings,
        create_polynomial_stare_runner(settings, max_residual_px=max_residual_px),
        target_label=_look_here_label(NUM_POLY_TARGETS),
        tracker=tracker,
        frame_source=frame_source,
        overlay=overlay,
        sleep=sleep,
        clock=clock,
        prefer_win32_overlay=prefer_win32_overlay,
        incomplete_message="wizard ended before collecting all calibration points",
    )
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
    model = calibration or load_calibration(calibration_path(settings))
    if model is None:
        return OffsetWizardOutcome(success=False, message=OFFSET_PREREQUISITE_MESSAGE)

    outcome = run_stare_wizard(
        settings,
        create_offset_stare_runner(settings, model),
        target_label=_look_here_label(NUM_OFFSET_TARGETS),
        tracker=tracker,
        frame_source=frame_source,
        overlay=overlay,
        sleep=sleep,
        clock=clock,
        prefer_win32_overlay=prefer_win32_overlay,
        incomplete_message="wizard ended before collecting all offset calibration points",
    )
    return outcome


def run_full_calibration(settings: Settings) -> OffsetWizardOutcome:
    if load_calibration(calibration_path(settings)) is None:
        poly = run_polynomial_wizard(settings)
        if not poly.success:
            return OffsetWizardOutcome(success=False, message=poly.message)
    return run_offset_wizard(settings)
