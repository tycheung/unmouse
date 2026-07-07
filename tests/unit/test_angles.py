"""Unit tests for joint-angle feature extraction."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pytest

from unmouse.gestures.angles import (
    FEATURE_DIM,
    TRIPLET_INDICES,
    compute_joint_angle_vector,
    compute_joint_angles,
    joint_angle,
    normalize_palm,
)
from unmouse.gestures.landmarks import HandLandmarks


def _as_landmarks(points: npt.NDArray[np.float64]) -> HandLandmarks:
    tuples = tuple((float(x), float(y), float(z)) for x, y, z in points)
    return HandLandmarks(points=tuples, handedness="Right")


def test_triplet_index_count_matches_feature_dimension() -> None:
    assert len(TRIPLET_INDICES) == 21 * 20 * 19
    assert FEATURE_DIM == len(TRIPLET_INDICES) + 10


def test_joint_angle_right_angle_at_pivot(
    right_angle_points: npt.NDArray[np.float64],
) -> None:
    angle = joint_angle(1, 0, 5, right_angle_points)
    assert angle == pytest.approx(math.pi / 2, abs=1e-6)


def test_normalize_palm_is_translation_and_scale_invariant(
    open_palm_points: npt.NDArray[np.float64],
) -> None:
    base = compute_joint_angles(normalize_palm(open_palm_points))
    shifted = open_palm_points + np.array([0.25, -0.15, 0.05])
    scaled = (shifted - shifted[0]) * 2.5 + shifted[0]
    transformed = compute_joint_angles(normalize_palm(scaled))
    assert base == pytest.approx(transformed, abs=1e-5)


def test_compute_joint_angle_vector_matches_manual_concat(
    open_palm_landmarks: HandLandmarks,
) -> None:
    vector = compute_joint_angle_vector(open_palm_landmarks)
    assert vector.shape == (FEATURE_DIM,)
    assert np.all(vector >= 0.0)
    assert np.all(vector <= math.pi)


def test_normalization_stabilizes_rotated_copy(
    open_palm_points: npt.NDArray[np.float64],
) -> None:
    reference = compute_joint_angle_vector(_as_landmarks(open_palm_points))
    rotation = np.array(
        [
            [0.0, -1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    rotated = ((rotation @ (open_palm_points - open_palm_points[0]).T).T) + open_palm_points[0]
    candidate = compute_joint_angle_vector(_as_landmarks(rotated))
    assert reference == pytest.approx(candidate, abs=1e-4)


def test_normalize_palm_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="expected shape"):
        normalize_palm(np.zeros((5, 3), dtype=np.float64))
