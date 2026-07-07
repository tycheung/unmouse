"""Unit tests for hand orientation click intent."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from unmouse.gestures.landmarks import NUM_HAND_LANDMARKS, HandLandmarks
from unmouse.gestures.orientation import (
    ClickIntent,
    compute_palm_normal,
    detect_click_intent,
    detect_right_click_orientation,
)


def _landmarks(points: npt.NDArray[np.float64]) -> HandLandmarks:
    tuples = tuple((float(x), float(y), float(z)) for x, y, z in points)
    return HandLandmarks(points=tuples, handedness="Right")


def _blank_hand() -> npt.NDArray[np.float64]:
    return np.zeros((NUM_HAND_LANDMARKS, 3), dtype=np.float64)


def _palm_facing_camera_points() -> npt.NDArray[np.float64]:
    points = _blank_hand()
    points[0] = (0.50, 0.80, 0.12)
    points[5] = (0.44, 0.72, 0.04)
    points[17] = (0.56, 0.72, 0.04)
    points[9] = (0.50, 0.72, 0.04)
    points[8] = (0.44, 0.45, 0.01)
    points[12] = (0.50, 0.45, 0.01)
    points[16] = (0.56, 0.48, 0.02)
    points[20] = (0.60, 0.50, 0.02)
    return points


def _dorsal_facing_camera_points() -> npt.NDArray[np.float64]:
    points = _blank_hand()
    points[0] = (0.50, 0.82, 0.10)
    points[5] = (0.44, 0.74, 0.02)
    points[17] = (0.56, 0.74, 0.02)
    points[9] = (0.50, 0.74, 0.02)
    for base, tip in ((9, 12), (13, 16), (17, 20)):
        points[base] = (points[base][0], points[base][1], 0.02)
        points[tip] = (points[base][0], points[base][1] + 0.05, 0.08)
        chain = range(base, tip + 1)
        for index in chain:
            t = (index - base) / max(tip - base, 1)
            points[index] = points[base] * (1.0 - t) + points[tip] * t
    return points


def _ambiguous_points() -> npt.NDArray[np.float64]:
    points = _blank_hand()
    z = 0.05
    points[0] = (0.50, 0.80, z)
    points[5] = (0.44, 0.72, z)
    points[17] = (0.56, 0.72, z)
    points[9] = (0.50, 0.72, z)
    for index in range(NUM_HAND_LANDMARKS):
        if index not in {0, 5, 9, 17}:
            points[index] = (0.50, 0.75, z)
    return points


def test_palm_facing_selects_right_click() -> None:
    hand = _landmarks(_palm_facing_camera_points())
    assert detect_click_intent(hand) == ClickIntent.RIGHT
    assert detect_right_click_orientation(hand) is True


def test_dorsal_facing_selects_left_click() -> None:
    hand = _landmarks(_dorsal_facing_camera_points())
    assert detect_click_intent(hand) == ClickIntent.LEFT
    assert detect_right_click_orientation(hand) is False


def test_ambiguous_orientation_defaults_to_left_click() -> None:
    hand = _landmarks(_ambiguous_points())
    assert detect_click_intent(hand) == ClickIntent.LEFT
    assert detect_right_click_orientation(hand) is False


def test_left_hand_mirrors_palm_normal() -> None:
    right = _landmarks(_palm_facing_camera_points())
    left_points = _palm_facing_camera_points().copy()
    left_points[:, 0] = 1.0 - left_points[:, 0]
    left = HandLandmarks(
        points=tuple((float(x), float(y), float(z)) for x, y, z in left_points),
        handedness="Left",
    )
    right_normal = compute_palm_normal(right)
    left_normal = compute_palm_normal(left)
    assert left_normal[0] == pytest.approx(-right_normal[0], abs=1e-6)
