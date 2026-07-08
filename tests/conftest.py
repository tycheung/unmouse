from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from unmouse.config import Settings
from unmouse.gestures.enrollment import default_gestures_dir
from unmouse.gestures.landmarks import NUM_HAND_LANDMARKS, HandLandmarks
from unmouse.gestures.mle import GestureLibrary, load_gesture_library
from unmouse.state import SystemState, create_system_state

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "gestures"


def _as_landmark_points(points: npt.NDArray[np.float64]) -> tuple[tuple[float, float, float], ...]:
    return tuple((float(x), float(y), float(z)) for x, y, z in points)


def _blank_hand() -> npt.NDArray[np.float64]:
    return np.zeros((NUM_HAND_LANDMARKS, 3), dtype=np.float64)


def load_landmark_fixture(name: str) -> HandLandmarks:
    path = FIXTURES_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    points = tuple(tuple(float(value) for value in point) for point in data["points"])
    handedness = str(data.get("handedness", "Right"))
    return HandLandmarks(points=points, handedness=handedness)


@pytest.fixture
def settings() -> Settings:
    return Settings(screen_width=800, screen_height=600, broker_queue_size=2)


@pytest.fixture
def system_state(settings: Settings) -> SystemState:
    return create_system_state(settings)


@pytest.fixture
def test_frame() -> npt.NDArray[np.uint8]:
    return np.zeros((24, 32, 3), dtype=np.uint8)


@pytest.fixture
def gesture_library() -> GestureLibrary:
    return load_gesture_library(default_gestures_dir())


@pytest.fixture
def open_palm_points() -> npt.NDArray[np.float64]:
    points = _blank_hand()
    points[0] = (0.50, 0.85, 0.0)
    finger_starts = [1, 5, 9, 13, 17]
    finger_tips = [4, 8, 12, 16, 20]
    offsets = [-0.12, -0.06, 0.0, 0.06, 0.12]
    for start, tip, offset in zip(finger_starts, finger_tips, offsets, strict=True):
        points[start] = (0.50 + offset, 0.72, 0.0)
        points[tip] = (0.50 + offset, 0.45, 0.0)
        chain = range(start, tip + 1)
        for index in chain:
            t = (index - start) / max(tip - start, 1)
            points[index] = points[start] * (1.0 - t) + points[tip] * t
    return points


@pytest.fixture
def open_palm_landmarks(open_palm_points: npt.NDArray[np.float64]) -> HandLandmarks:
    return HandLandmarks(points=_as_landmark_points(open_palm_points), handedness="Right")


@pytest.fixture
def right_angle_points() -> npt.NDArray[np.float64]:
    points = _blank_hand()
    points[0] = (0.0, 0.0, 0.0)
    points[1] = (1.0, 0.0, 0.0)
    points[5] = (0.0, 1.0, 0.0)
    points[9] = (0.0, 0.5, 0.0)
    for index in range(NUM_HAND_LANDMARKS):
        if index not in {0, 1, 5, 9}:
            points[index] = points[0]
    return points


@pytest.fixture
def right_angle_landmarks(right_angle_points: npt.NDArray[np.float64]) -> HandLandmarks:
    return HandLandmarks(points=_as_landmark_points(right_angle_points), handedness="Right")
