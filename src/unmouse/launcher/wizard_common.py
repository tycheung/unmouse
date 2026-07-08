"""Shared stare-calibration helpers for polynomial and offset wizards."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

import numpy as np

from unmouse.broker.video_broker import FrameSource, create_frame_source
from unmouse.config import Settings
from unmouse.gaze.tracker import GazeTracker, create_gaze_tracker


@dataclass(frozen=True)
class GazeSample:
    timestamp_s: float
    x: float
    y: float
    confidence: float = 1.0


class WizardTarget(Protocol):
    index: int
    x: float
    y: float


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


OutcomeT = TypeVar("OutcomeT")


class StareCalibrationRunner:
    def __init__(
        self,
        *,
        targets: Sequence[Any],
        point_duration_s: float,
        discard_s: float,
    ) -> None:
        if not targets:
            msg = "at least one calibration target is required"
            raise ValueError(msg)
        self._targets = tuple(targets)
        self._point_duration_s = point_duration_s
        self._discard_s = discard_s
        self._index = 0
        self._samples: list[GazeSample] = []
        self._point_started_s: float | None = None
        self._outcome: object | None = None

    @property
    def done(self) -> bool:
        return self._outcome is not None

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def current_target(self) -> WizardTarget | None:
        if self.done or self._index >= len(self._targets):
            return None
        return cast(WizardTarget, self._targets[self._index])

    @property
    def outcome(self) -> object | None:
        return self._outcome

    def begin_point(self, timestamp_s: float) -> WizardTarget:
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

    def _complete_current_point(self) -> None:
        assert self._point_started_s is not None
        filtered = filter_samples_for_point(
            self._samples,
            point_started_s=self._point_started_s,
            discard_s=self._discard_s,
            point_duration_s=self._point_duration_s,
        )
        self.on_point_complete(filtered, self._targets[self._index])
        self._index += 1
        self._point_started_s = None
        if self._index >= len(self._targets):
            self._outcome = self.evaluate()

    def on_point_complete(self, samples: Sequence[GazeSample], target: WizardTarget) -> None:
        raise NotImplementedError

    def evaluate(self) -> object:
        raise NotImplementedError


def axis_positions(span: float, inset: float) -> tuple[float, float, float]:
    margin = span * inset
    usable = span - (2 * margin)
    return (margin, margin + usable / 2, span - margin)


def build_square_grid_positions(
    screen_width: float,
    screen_height: float,
    *,
    grid_size: int,
    inset: float,
) -> tuple[tuple[float, float], ...]:
    if screen_width <= 0 or screen_height <= 0:
        msg = "screen dimensions must be positive"
        raise ValueError(msg)
    xs = axis_positions(screen_width, inset)
    ys = axis_positions(screen_height, inset)
    positions: list[tuple[float, float]] = []
    for row in range(grid_size):
        for col in range(grid_size):
            positions.append((xs[col], ys[row]))
    return tuple(positions)


def filter_samples_for_point(
    samples: Sequence[GazeSample],
    *,
    point_started_s: float,
    discard_s: float,
    point_duration_s: float,
) -> list[GazeSample]:
    sample_start = point_started_s + discard_s
    sample_end = point_started_s + point_duration_s
    return [
        sample
        for sample in samples
        if sample_start <= sample.timestamp_s <= sample_end
    ]


def geometric_mean_gaze(samples: Sequence[GazeSample]) -> tuple[float, float]:
    if not samples:
        msg = "at least one gaze sample is required"
        raise ValueError(msg)
    weights = np.array([max(sample.confidence, 1e-6) for sample in samples], dtype=np.float64)
    xs = np.array([sample.x for sample in samples], dtype=np.float64)
    ys = np.array([sample.y for sample in samples], dtype=np.float64)
    total = float(weights.sum())
    mean_x = float(np.dot(xs, weights) / total)
    mean_y = float(np.dot(ys, weights) / total)
    return mean_x, mean_y


def run_stare_wizard(
    settings: Settings,
    runner: StareCalibrationRunner,
    *,
    target_label: Callable[[WizardTarget], str],
    tracker: GazeTracker | None = None,
    frame_source: FrameSource | None = None,
    overlay: WizardOverlayBackend | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.perf_counter,
    prefer_win32_overlay: bool = True,
    incomplete_message: str,
) -> object:
    from unmouse.launcher.calibration_overlay import create_calibration_overlay

    gaze_tracker = tracker or create_gaze_tracker(prefer_eyegestures=False)
    source = frame_source or create_frame_source(settings)
    ui = overlay or create_calibration_overlay(prefer_win32=prefer_win32_overlay)
    try:
        started = clock()
        target = runner.begin_point(started)
        ui.show_target(target.x, target.y, label=target_label(target))
        while not runner.done:
            ok, frame = source.read()
            now = clock()
            if ok and frame is not None:
                gaze = gaze_tracker.predict(np.asarray(frame, dtype=np.uint8))
                if runner.add_sample(GazeSample(now, gaze.x, gaze.y, gaze.confidence)):
                    if runner.done:
                        break
                    target = runner.begin_point(now)
                    ui.show_target(target.x, target.y, label=target_label(target))
            sleep(0.01)
    finally:
        ui.hide()
        source.release()

    outcome = runner.outcome
    if outcome is None:
        msg = incomplete_message
        raise RuntimeError(msg)
    return outcome
