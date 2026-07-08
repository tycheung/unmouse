from __future__ import annotations

import numpy as np
import numpy.typing as npt

from unmouse.gestures.landmarks import (
    INDEX_TIP,
    MIDDLE_MCP,
    THUMB_TIP,
    WRIST,
    HandLandmarks,
)

_EPSILON = 1e-8

# (base, tip) landmark indices for thumb, index, middle, ring, pinky.
FINGERS: tuple[tuple[int, int], ...] = ((1, 4), (5, 8), (9, 12), (13, 16), (17, 20))
FINGER_PAIRS: tuple[tuple[int, int], ...] = tuple(
    (left, right)
    for left in range(len(FINGERS))
    for right in range(left + 1, len(FINGERS))
)

# 5 finger direction angles + 5 finger lengths + 10 inter-finger angles + 1 pinch gap.
FEATURE_DIM = len(FINGERS) * 2 + len(FINGER_PAIRS) + 1


def landmarks_to_array(hand: HandLandmarks) -> npt.NDArray[np.float64]:
    return np.array(hand.points, dtype=np.float64)


def compute_feature_vector(hand: HandLandmarks) -> npt.NDArray[np.float64]:
    """Rigid-transform-invariant gesture features for one hand.

    Angles and palm-relative lengths are invariant to translation, rotation, and
    uniform scale, so no explicit hand normalization is required.
    """
    points = landmarks_to_array(hand)
    wrist = points[WRIST]
    palm_axis = _unit(points[MIDDLE_MCP] - wrist)
    palm_length = float(np.linalg.norm(points[MIDDLE_MCP] - wrist)) or 1.0

    raw_directions = [points[tip] - points[base] for base, tip in FINGERS]
    unit_directions = [_unit(vec) for vec in raw_directions]

    direction_angles = [_angle_between(direction, palm_axis) for direction in unit_directions]
    finger_lengths = [float(np.linalg.norm(vec)) / palm_length for vec in raw_directions]
    spread_angles = [
        _angle_between(unit_directions[left], unit_directions[right])
        for left, right in FINGER_PAIRS
    ]
    pinch_gap = float(np.linalg.norm(points[THUMB_TIP] - points[INDEX_TIP])) / palm_length

    return np.array(
        [*direction_angles, *finger_lengths, *spread_angles, pinch_gap],
        dtype=np.float64,
    )


def _unit(vec: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    norm = float(np.linalg.norm(vec))
    if norm < _EPSILON:
        return np.zeros(3, dtype=np.float64)
    return np.asarray(vec / norm, dtype=np.float64)


def _angle_between(
    unit_a: npt.NDArray[np.float64],
    unit_b: npt.NDArray[np.float64],
) -> float:
    cosine = float(np.clip(np.dot(unit_a, unit_b), -1.0, 1.0))
    return float(np.arccos(cosine))
