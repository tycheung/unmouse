from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt

from unmouse.gaze.tracker import CalibrationTarget, GazeSample


class _FakeEvent:
    def __init__(
        self,
        point: tuple[float, float],
        *,
        fixation: float = 0.0,
        saccades: bool = False,
        blink: bool = False,
    ) -> None:
        self.point = point
        self.fixation = fixation
        self.saccades = saccades
        self.blink = blink


class FakeEyeGesturesEngine:
    def __init__(self) -> None:
        self.uploaded: tuple[Any, str] | None = None
        self.fixation: float | None = None
        self.saved = 0
        self.loaded: tuple[bytes, str] | None = None
        self.steps: list[tuple[bool, int, int, str]] = []

    def uploadCalibrationMap(self, points: Any, context: str) -> None:  # noqa: N802
        self.uploaded = (points, context)

    def setFixation(self, threshold: float) -> None:  # noqa: N802
        self.fixation = threshold

    def step(
        self, frame: Any, calibrate: bool, width: int, height: int, context: str
    ) -> tuple[_FakeEvent, _FakeEvent | None]:
        self.steps.append((calibrate, width, height, context))
        event = _FakeEvent(
            (width * 0.5, height * 0.5), fixation=0.9, saccades=True, blink=False
        )
        calibration_event = _FakeEvent((10.0, 20.0)) if calibrate else None
        return event, calibration_event

    def saveModel(self, context: str) -> bytes:  # noqa: N802
        self.saved += 1
        return b"model-bytes"

    def loadModel(self, data: bytes, context: str) -> None:  # noqa: N802
        self.loaded = (data, context)


class FakeGazeTracker:
    def __init__(
        self,
        *,
        sample: GazeSample | None = None,
        targets: Sequence[tuple[float, float]] = (),
        model: bytes | None = b"model-bytes",
    ) -> None:
        self._sample = sample or GazeSample(x=0.0, y=0.0, fixation=1.0)
        self._targets = list(targets)
        self._model = model
        self._calibration_index = 0
        self.saved = False
        self.loaded: bytes | None = None

    def step(
        self, frame: npt.NDArray[np.uint8], *, calibrate: bool
    ) -> tuple[GazeSample | None, CalibrationTarget | None]:
        _ = frame
        if calibrate and self._calibration_index < len(self._targets):
            point = self._targets[self._calibration_index]
            self._calibration_index += 1
            return self._sample, CalibrationTarget(x=point[0], y=point[1])
        return self._sample, None

    def save_model(self) -> bytes | None:
        self.saved = True
        return self._model

    def load_model(self, data: bytes) -> None:
        self.loaded = data
