from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from unmouse.gestures.landmarks import HandLandmarks, LandmarkDetectionResult


class NullHandLandmarkDetector:
    def __init__(self, hands: Sequence[HandLandmarks] | None = None) -> None:
        self._hands = tuple(hands or ())

    def detect(self, frame: npt.NDArray[np.uint8]) -> LandmarkDetectionResult:
        _ = frame
        return LandmarkDetectionResult(hands=self._hands)
