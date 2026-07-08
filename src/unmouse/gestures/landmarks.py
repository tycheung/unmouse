from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import cv2
import numpy as np
import numpy.typing as npt

NUM_HAND_LANDMARKS = 21
LandmarkPoint = tuple[float, float, float]

WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_TIP = 8
MIDDLE_MCP = 9
PINKY_MCP = 17


@dataclass(frozen=True)
class HandLandmarks:
    points: tuple[LandmarkPoint, ...]
    handedness: str = "Right"

    def __post_init__(self) -> None:
        if len(self.points) != NUM_HAND_LANDMARKS:
            msg = f"expected {NUM_HAND_LANDMARKS} landmarks, got {len(self.points)}"
            raise ValueError(msg)


@dataclass(frozen=True)
class LandmarkDetectionResult:
    hands: tuple[HandLandmarks, ...]


class HandLandmarkDetector(Protocol):
    def detect(self, frame: npt.NDArray[np.uint8]) -> LandmarkDetectionResult: ...


class MediaPipeHandDetector:
    def __init__(
        self,
        *,
        max_num_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        import mediapipe as mp  # type: ignore[import-untyped]

        self._mp = mp
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def detect(self, frame: npt.NDArray[np.uint8]) -> LandmarkDetectionResult:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb)
        if not results.multi_hand_landmarks:
            return LandmarkDetectionResult(hands=())

        handedness_labels = _handedness_labels(results)
        hands: list[HandLandmarks] = []
        for index, hand_landmarks in enumerate(results.multi_hand_landmarks):
            points = tuple(
                (float(lm.x), float(lm.y), float(lm.z)) for lm in hand_landmarks.landmark
            )
            label = handedness_labels[index] if index < len(handedness_labels) else "Right"
            hands.append(HandLandmarks(points=points, handedness=label))
        return LandmarkDetectionResult(hands=tuple(hands))

    def close(self) -> None:
        self._hands.close()


def draw_hand_skeleton(
    frame: npt.NDArray[np.uint8],
    hands: Sequence[HandLandmarks],
    *,
    draw: bool = True,
) -> npt.NDArray[np.uint8]:
    """Draw MediaPipe hand topology on a copy of the frame when enabled."""
    if not draw or not hands:
        return frame

    import mediapipe as mp

    output = frame.copy()
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    for hand in hands:
        landmark_list = _to_mediapipe_landmarks(hand.points, mp)
        mp_drawing.draw_landmarks(
            output,
            landmark_list,
            mp_hands.HAND_CONNECTIONS,
            mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=3),
            mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2),
        )
    return output


def create_hand_detector() -> HandLandmarkDetector:
    return MediaPipeHandDetector()


def _handedness_labels(results: Any) -> list[str]:
    if not results.multi_handedness:
        return []
    labels: list[str] = []
    for item in results.multi_handedness:
        labels.append(str(item.classification[0].label))
    return labels


def _to_mediapipe_landmarks(points: Sequence[LandmarkPoint], mp: Any) -> Any:
    landmark_list = mp.framework.formats.landmark_pb2.NormalizedLandmarkList()
    for x, y, z in points:
        landmark = landmark_list.landmark.add()
        landmark.x = x
        landmark.y = y
        landmark.z = z
    return landmark_list
