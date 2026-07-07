"""Unit tests for gesture enrollment helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from unmouse.gestures.angles import FEATURE_DIM, compute_joint_angle_vector
from unmouse.gestures.enrollment import (
    DEFAULT_GESTURE_NAMES,
    build_default_template,
    enroll_from_samples,
    generate_default_templates,
    samples_from_landmarks,
    synthetic_landmarks,
)
from unmouse.gestures.mle import classify, load_gesture_library


def test_synthetic_landmarks_yield_distinct_angle_vectors() -> None:
    vectors = {
        gesture: compute_joint_angle_vector(synthetic_landmarks(gesture))
        for gesture in DEFAULT_GESTURE_NAMES
    }
    assert vectors["v_sign"].shape == (FEATURE_DIM,)
    assert not np.allclose(vectors["v_sign"], vectors["pinch_close"])
    assert not np.allclose(vectors["pinch_close"], vectors["thumbs_up"])


def test_build_default_template_uses_diagonal_covariance() -> None:
    template = build_default_template("v_sign")
    assert template.diagonal is True
    assert template.dim == FEATURE_DIM


def test_enroll_from_samples_writes_profile_template(tmp_path: Path) -> None:
    hand = synthetic_landmarks("pinch_close")
    samples = samples_from_landmarks(hand, count=24, seed=7)
    path = enroll_from_samples("pinch_close", samples, tmp_path)
    assert path.is_file()
    library = load_gesture_library(tmp_path)
    result = classify(
        compute_joint_angle_vector(hand),
        library,
        absolute_min=-1000.0,
        margin_min=0.0,
    )
    assert result.gesture == "pinch_close"


def test_generate_default_templates_writes_all_gestures(tmp_path: Path) -> None:
    paths = generate_default_templates(tmp_path)
    assert len(paths) == 3
    library = load_gesture_library(tmp_path)
    assert set(library) == set(DEFAULT_GESTURE_NAMES)
    for gesture in DEFAULT_GESTURE_NAMES:
        vector = compute_joint_angle_vector(synthetic_landmarks(gesture))
        result = classify(vector, library, absolute_min=-1000.0, margin_min=1.0)
        assert result.gesture == gesture
