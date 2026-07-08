from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pytest

from unmouse.gestures.angles import FEATURE_DIM, compute_feature_vector
from unmouse.gestures.landmarks import HandLandmarks


def _as_landmarks(points: npt.NDArray[np.float64]) -> HandLandmarks:
    tuples = tuple((float(x), float(y), float(z)) for x, y, z in points)
    return HandLandmarks(points=tuples, handedness="Right")


def test_feature_vector_has_expected_shape_and_range(
    open_palm_landmarks: HandLandmarks,
) -> None:
    vector = compute_feature_vector(open_palm_landmarks)
    assert vector.shape == (FEATURE_DIM,)
    assert FEATURE_DIM == 21
    assert np.all(np.isfinite(vector))


def test_feature_vector_is_invariant_to_translation_rotation_and_scale(
    open_palm_points: npt.NDArray[np.float64],
) -> None:
    reference = compute_feature_vector(_as_landmarks(open_palm_points))
    rotation = np.array(
        [
            [math.cos(0.7), -math.sin(0.7), 0.0],
            [math.sin(0.7), math.cos(0.7), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    transformed = (rotation @ open_palm_points.T).T * 2.5 + np.array([0.25, -0.15, 0.05])
    candidate = compute_feature_vector(_as_landmarks(transformed))
    assert reference == pytest.approx(candidate, abs=1e-6)


def test_distinct_poses_yield_distinct_features(
    open_palm_landmarks: HandLandmarks,
    right_angle_landmarks: HandLandmarks,
) -> None:
    open_palm = compute_feature_vector(open_palm_landmarks)
    right_angle = compute_feature_vector(right_angle_landmarks)
    assert not np.allclose(open_palm, right_angle)


def test_degenerate_hand_produces_finite_features() -> None:
    flat = _as_landmarks(np.zeros((21, 3), dtype=np.float64))
    vector = compute_feature_vector(flat)
    assert np.all(np.isfinite(vector))
