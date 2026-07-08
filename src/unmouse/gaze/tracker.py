"""Gaze tracker adapters."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class GazeResult:
    x: float
    y: float
    confidence: float
    head_yaw_deg: float = 0.0


class GazeTracker(Protocol):
    def predict(self, frame: npt.NDArray[np.uint8]) -> GazeResult: ...


class NullGazeTracker:
    def __init__(
        self,
        x: float,
        y: float,
        confidence: float = 1.0,
        head_yaw_deg: float = 0.0,
    ) -> None:
        self._result = GazeResult(x=x, y=y, confidence=confidence, head_yaw_deg=head_yaw_deg)

    def predict(self, frame: npt.NDArray[np.uint8]) -> GazeResult:
        _ = frame
        return self._result


class EyeGesturesTracker:
    """Adapter for EyeGestures V3 when installed."""

    def __init__(self) -> None:
        try:
            module = importlib.import_module("eyegestures")
        except ImportError as exc:
            msg = "EyeGestures is not installed"
            raise RuntimeError(msg) from exc
        self._engine: Any = module.init_v3_engine()

    def predict(self, frame: npt.NDArray[np.uint8]) -> GazeResult:
        raw_x, raw_y, meta = self._engine.predict(frame)
        confidence = float(meta.get("confidence", 1.0))
        head_yaw = float(meta.get("head_yaw_deg", 0.0))
        return GazeResult(
            x=float(raw_x),
            y=float(raw_y),
            confidence=confidence,
            head_yaw_deg=head_yaw,
        )


def create_gaze_tracker(prefer_eyegestures: bool = True) -> GazeTracker:
    if prefer_eyegestures:
        try:
            return EyeGesturesTracker()
        except RuntimeError:
            pass
    return NullGazeTracker(x=960.0, y=540.0)
