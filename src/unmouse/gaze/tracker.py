from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import numpy.typing as npt

from unmouse.config import Settings

GAZE_MODEL_FILENAME = "gaze_model.pkl"
_CONTEXT = "unmouse"


@dataclass(frozen=True)
class GazeSample:
    x: float
    y: float
    fixation: float = 0.0
    saccade: bool = False
    blink: bool = False


@dataclass(frozen=True)
class CalibrationTarget:
    x: float
    y: float


class EyeGesturesEngine(Protocol):
    def uploadCalibrationMap(  # noqa: N802 - matches eyeGestures API
        self, points: Any, context: str
    ) -> None: ...

    def setFixation(self, threshold: float) -> None: ...  # noqa: N802

    def step(
        self, frame: Any, calibrate: bool, width: int, height: int, context: str
    ) -> tuple[Any, Any]: ...

    def saveModel(self, context: str) -> bytes | None: ...  # noqa: N802

    def loadModel(self, data: bytes, context: str) -> None: ...  # noqa: N802


class GazeTracker(Protocol):
    def step(
        self, frame: npt.NDArray[np.uint8], *, calibrate: bool
    ) -> tuple[GazeSample | None, CalibrationTarget | None]: ...

    def save_model(self) -> bytes | None: ...

    def load_model(self, data: bytes) -> None: ...


class EyeGesturesTracker:
    def __init__(
        self,
        *,
        screen_width: int,
        screen_height: int,
        calibration_points: int,
        calibration_radius: int,
        fixation_threshold: float,
        engine: EyeGesturesEngine | None = None,
    ) -> None:
        self._width = screen_width
        self._height = screen_height
        self._engine = engine or _build_engine(calibration_radius)
        self._engine.uploadCalibrationMap(
            calibration_map(calibration_points), context=_CONTEXT
        )
        self._engine.setFixation(fixation_threshold)

    def step(
        self, frame: npt.NDArray[np.uint8], *, calibrate: bool
    ) -> tuple[GazeSample | None, CalibrationTarget | None]:
        event, calibration_event = self._engine.step(
            frame, calibrate, self._width, self._height, context=_CONTEXT
        )
        sample = _sample_from_event(event)
        target = _target_from_event(calibration_event)
        return sample, target

    def save_model(self) -> bytes | None:
        return self._engine.saveModel(context=_CONTEXT)

    def load_model(self, data: bytes) -> None:
        self._engine.loadModel(data, context=_CONTEXT)


def create_gaze_tracker(
    settings: Settings,
    *,
    engine: EyeGesturesEngine | None = None,
    model: bytes | None = None,
) -> GazeTracker:
    tracker = EyeGesturesTracker(
        screen_width=settings.screen_width,
        screen_height=settings.screen_height,
        calibration_points=settings.gaze_calibration_points,
        calibration_radius=settings.gaze_calibration_radius,
        fixation_threshold=settings.fixation_threshold,
        engine=engine,
    )
    if model is not None:
        tracker.load_model(model)
    return tracker


def calibration_map(points: int) -> npt.NDArray[np.float64]:
    side = max(2, int(np.ceil(np.sqrt(points))))
    axis = np.linspace(0.0, 1.0, side)
    grid_x, grid_y = np.meshgrid(axis, axis)
    grid = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    return grid[:points]


def gaze_model_path(settings: Settings) -> Path:
    return settings.profile_dir / GAZE_MODEL_FILENAME


def load_gaze_model(settings: Settings) -> bytes | None:
    path = gaze_model_path(settings)
    if not path.is_file():
        return None
    return path.read_bytes()


def save_gaze_model(settings: Settings, data: bytes) -> Path:
    path = gaze_model_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _build_engine(calibration_radius: int) -> EyeGesturesEngine:
    from eyeGestures import EyeGestures_v3

    return cast(EyeGesturesEngine, EyeGestures_v3(calibration_radius=calibration_radius))


def _sample_from_event(event: Any) -> GazeSample | None:
    if event is None:
        return None
    point = event.point
    return GazeSample(
        x=float(point[0]),
        y=float(point[1]),
        fixation=float(getattr(event, "fixation", 0.0)),
        saccade=bool(getattr(event, "saccades", False)),
        blink=bool(getattr(event, "blink", False)),
    )


def _target_from_event(event: Any) -> CalibrationTarget | None:
    if event is None:
        return None
    point = event.point
    return CalibrationTarget(x=float(point[0]), y=float(point[1]))
