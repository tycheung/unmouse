"""Nine-point polynomial calibration wizard with fullscreen target overlay."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from unmouse.config import Settings
from unmouse.gaze.calibration import (
    CalibrationModel,
    PointPair,
    calibration_path,
    fit_calibration,
    mean_residual_error,
    save_calibration,
)
from unmouse.launcher.wizard_common import (
    FakeWizardOverlayBackend as FakeWizardOverlayBackend,
)
from unmouse.launcher.wizard_common import (
    GazeSample,
    StareCalibrationRunner,
    WizardTarget,
    geometric_mean_gaze,
    run_stare_wizard,
)
from unmouse.launcher.wizard_common import (
    filter_samples_for_point as filter_samples_for_point,
)

NUM_POLY_TARGETS = 9
GRID_SIZE = 3
DEFAULT_TARGET_INSET = 0.05


@dataclass(frozen=True)
class PolynomialTarget:
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


class PolynomialWizardRunner(StareCalibrationRunner):
    """Collect nine stare samples and fit a polynomial calibration model."""

    def __init__(
        self,
        settings: Settings,
        *,
        targets: Sequence[PolynomialTarget] | None = None,
        max_residual_px: float | None = None,
    ) -> None:
        resolved = tuple(targets or build_polynomial_targets(
            settings.screen_width,
            settings.screen_height,
        ))
        if len(resolved) != NUM_POLY_TARGETS:
            msg = f"expected {NUM_POLY_TARGETS} calibration targets"
            raise ValueError(msg)
        super().__init__(
            targets=resolved,
            point_duration_s=settings.calibration_point_duration_s,
            discard_s=settings.calibration_discard_s,
        )
        self._max_residual_px = max_residual_px or settings.calibration_max_residual_px
        self._points: list[PointPair] = []

    @property
    def outcome(self) -> PolynomialWizardOutcome | None:
        return self._outcome  # type: ignore[return-value]

    def finish_from_pairs(self, pairs: Sequence[PointPair]) -> PolynomialWizardOutcome:
        if len(pairs) != NUM_POLY_TARGETS:
            msg = f"expected {NUM_POLY_TARGETS} point pairs"
            raise ValueError(msg)
        self._points = list(pairs)
        self._index = len(self._targets)
        self._outcome = self.evaluate()
        return self._outcome

    def on_point_complete(self, samples: Sequence[GazeSample], target: WizardTarget) -> None:
        raw_x, raw_y = geometric_mean_gaze(samples)
        self._points.append((raw_x, raw_y, target.x, target.y))

    def evaluate(self) -> PolynomialWizardOutcome:
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


def build_polynomial_targets(
    screen_width: float,
    screen_height: float,
    *,
    inset: float = DEFAULT_TARGET_INSET,
) -> tuple[PolynomialTarget, ...]:
    if screen_width <= 0 or screen_height <= 0:
        msg = "screen dimensions must be positive"
        raise ValueError(msg)
    xs = _axis_positions(screen_width, inset)
    ys = _axis_positions(screen_height, inset)
    targets: list[PolynomialTarget] = []
    index = 0
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            targets.append(PolynomialTarget(index=index, x=xs[col], y=ys[row]))
            index += 1
    return tuple(targets)


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
    """Run the full nine-point calibration sequence and save on success."""
    import time

    runner = PolynomialWizardRunner(settings, max_residual_px=max_residual_px)
    outcome = run_stare_wizard(
        settings,
        runner,
        target_label=lambda target: f"Look here ({target.index + 1}/{NUM_POLY_TARGETS})",
        tracker=tracker,
        frame_source=frame_source,
        overlay=overlay,
        sleep=sleep or time.sleep,
        clock=clock or time.perf_counter,
        prefer_win32_overlay=prefer_win32_overlay,
        incomplete_message="wizard ended before collecting all calibration points",
    )
    assert isinstance(outcome, PolynomialWizardOutcome)
    if outcome.success and outcome.model is not None:
        save_calibration(calibration_path(settings), outcome.model)
    return outcome


def _axis_positions(span: float, inset: float) -> tuple[float, float, float]:
    margin = span * inset
    usable = span - (2 * margin)
    return (margin, margin + usable / 2, span - margin)


def create_wizard_overlay(*, prefer_win32: bool = True) -> object:
    from unmouse.launcher.calibration_overlay import create_calibration_overlay

    return create_calibration_overlay(prefer_win32=prefer_win32)
