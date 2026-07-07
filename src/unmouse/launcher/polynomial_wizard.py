"""Nine-point polynomial calibration wizard with fullscreen target overlay."""

from __future__ import annotations

import queue
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import numpy as np

from unmouse.broker.video_broker import FrameSource, create_frame_source
from unmouse.config import Settings
from unmouse.gaze.calibration import (
    CalibrationModel,
    PointPair,
    calibration_path,
    fit_calibration,
    mean_residual_error,
    save_calibration,
)
from unmouse.gaze.tracker import GazeTracker, create_gaze_tracker
from unmouse.overlay.indicator import TRANSPARENT_CHROMA, apply_click_through_styles

if TYPE_CHECKING:
    import tkinter as tk

NUM_POLY_TARGETS = 9
GRID_SIZE = 3
DEFAULT_TARGET_INSET = 0.05
TARGET_DOT_DIAMETER = 24
TARGET_DOT_COLOR = "#FFFFFF"


@dataclass(frozen=True)
class PolynomialTarget:
    index: int
    x: float
    y: float


@dataclass(frozen=True)
class GazeSample:
    timestamp_s: float
    x: float
    y: float
    confidence: float = 1.0


@dataclass(frozen=True)
class PolynomialWizardOutcome:
    success: bool
    model: CalibrationModel | None
    residual_px: float
    message: str
    retry_recommended: bool


class WizardOverlayBackend(Protocol):
    def show_target(self, x: float, y: float, *, label: str) -> None: ...

    def hide(self) -> None: ...


@dataclass
class FakeWizardOverlayBackend:
    shown: list[tuple[float, float, str]] = field(default_factory=list)

    def show_target(self, x: float, y: float, *, label: str) -> None:
        self.shown.append((x, y, label))

    def hide(self) -> None:
        self.shown.clear()


class PolynomialWizardRunner:
    """Collect nine stare samples and fit a polynomial calibration model."""

    def __init__(
        self,
        settings: Settings,
        *,
        targets: Sequence[PolynomialTarget] | None = None,
        max_residual_px: float | None = None,
    ) -> None:
        self._settings = settings
        self._targets = tuple(targets or build_polynomial_targets(
            settings.screen_width,
            settings.screen_height,
        ))
        if len(self._targets) != NUM_POLY_TARGETS:
            msg = f"expected {NUM_POLY_TARGETS} calibration targets"
            raise ValueError(msg)
        self._max_residual_px = max_residual_px or settings.calibration_max_residual_px
        self._point_duration_s = settings.calibration_point_duration_s
        self._discard_s = settings.calibration_discard_s
        self._index = 0
        self._points: list[PointPair] = []
        self._samples: list[GazeSample] = []
        self._point_started_s: float | None = None
        self._outcome: PolynomialWizardOutcome | None = None

    @property
    def done(self) -> bool:
        return self._outcome is not None

    @property
    def outcome(self) -> PolynomialWizardOutcome | None:
        return self._outcome

    @property
    def current_target(self) -> PolynomialTarget | None:
        if self.done or self._index >= len(self._targets):
            return None
        return self._targets[self._index]

    @property
    def current_index(self) -> int:
        return self._index

    def begin_point(self, timestamp_s: float) -> PolynomialTarget:
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

    def finish_from_pairs(self, pairs: Sequence[PointPair]) -> PolynomialWizardOutcome:
        if len(pairs) != NUM_POLY_TARGETS:
            msg = f"expected {NUM_POLY_TARGETS} point pairs"
            raise ValueError(msg)
        self._points = list(pairs)
        return self._evaluate()

    def _complete_current_point(self) -> None:
        assert self._point_started_s is not None
        filtered = filter_samples_for_point(
            self._samples,
            point_started_s=self._point_started_s,
            discard_s=self._discard_s,
            point_duration_s=self._point_duration_s,
        )
        raw_x, raw_y = geometric_mean_gaze(filtered)
        target = self._targets[self._index]
        self._points.append((raw_x, raw_y, target.x, target.y))
        self._index += 1
        self._point_started_s = None
        if self._index >= NUM_POLY_TARGETS:
            self._outcome = self._evaluate()

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


def run_polynomial_wizard(
    settings: Settings,
    *,
    tracker: GazeTracker | None = None,
    frame_source: FrameSource | None = None,
    overlay: WizardOverlayBackend | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.perf_counter,
    max_residual_px: float | None = None,
    prefer_win32_overlay: bool = True,
) -> PolynomialWizardOutcome:
    """Run the full nine-point calibration sequence and save on success."""
    runner = PolynomialWizardRunner(settings, max_residual_px=max_residual_px)
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
        msg = "wizard ended before collecting all calibration points"
        raise RuntimeError(msg)
    if outcome.success and outcome.model is not None:
        save_calibration(calibration_path(settings), outcome.model)
    return outcome


def create_wizard_overlay(*, prefer_win32: bool = True) -> WizardOverlayBackend:
    if prefer_win32 and sys.platform == "win32":
        return TkPolynomialWizardOverlay()
    return FakeWizardOverlayBackend()


class TkPolynomialWizardOverlay:
    """Fullscreen always-on-top dot renderer for calibration targets."""

    def __init__(self, *, dot_diameter: int = TARGET_DOT_DIAMETER) -> None:
        self._diameter = dot_diameter
        self._commands: queue.Queue[tuple[float, float, str] | None] = queue.Queue()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    def show_target(self, x: float, y: float, *, label: str) -> None:
        self._ensure_thread()
        self._commands.put((x, y, label))

    def hide(self) -> None:
        if self._thread and self._thread.is_alive():
            self._commands.put(None)

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="poly-cal-overlay", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=2.0):
            msg = "calibration overlay failed to start"
            raise RuntimeError(msg)

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=TRANSPARENT_CHROMA)
        root.attributes("-transparentcolor", TRANSPARENT_CHROMA)
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.geometry(f"{screen_w}x{screen_h}+0+0")

        canvas = tk.Canvas(
            root,
            width=screen_w,
            height=screen_h,
            highlightthickness=0,
            bg=TRANSPARENT_CHROMA,
        )
        canvas.pack()
        label = tk.Label(root, text="", fg="white", bg="black")
        label.place(relx=0.5, y=24, anchor="n")

        apply_click_through_styles(root.winfo_id())
        self._ready.set()
        self._poll(root, canvas, label)
        root.mainloop()

    def _poll(self, root: tk.Tk, canvas: tk.Canvas, label: tk.Label) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                break
            if command is None:
                root.quit()
                return
            x, y, text = command
            self._render(canvas, label, x, y, text)
        root.after(50, lambda: self._poll(root, canvas, label))

    def _render(self, canvas: tk.Canvas, label: tk.Label, x: float, y: float, text: str) -> None:
        canvas.delete("all")
        label.config(text=text)
        radius = self._diameter / 2
        padding = 2
        canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=TARGET_DOT_COLOR,
            outline=TARGET_DOT_COLOR,
            width=padding,
        )


def _axis_positions(span: float, inset: float) -> tuple[float, float, float]:
    margin = span * inset
    usable = span - (2 * margin)
    return (margin, margin + usable / 2, span - margin)


def _target_label(index: int) -> str:
    return f"Look here ({index + 1}/{NUM_POLY_TARGETS})"
