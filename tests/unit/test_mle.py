from __future__ import annotations

import numpy as np
import pytest

from unmouse.gestures.mle import (
    ClassificationResult,
    GestureTemplate,
    build_template,
    classify,
    load_gesture_library,
    load_template,
    log_likelihood,
    save_template,
)


def _samples(mean: list[float], spread: float, count: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, spread, size=(count, len(mean)))
    return np.asarray(mean, dtype=np.float64) + noise


def _library() -> dict[str, GestureTemplate]:
    v_sign = build_template("v_sign", _samples([0.0, 0.0, 0.0], 0.05, 40, 1))
    pinch = build_template("pinch_close", _samples([3.0, 0.5, -0.5], 0.05, 40, 2))
    return {"v_sign": v_sign, "pinch_close": pinch}


def test_classify_returns_best_matching_gesture() -> None:
    result = classify(
        np.array([0.05, -0.02, 0.01]),
        _library(),
        absolute_min=-50.0,
        margin_min=1.0,
    )
    assert result.gesture == "v_sign"
    assert result.margin > 1.0


def test_classify_rejects_low_margin() -> None:
    ambiguous = np.array([1.5, 0.25, -0.25])
    result = classify(ambiguous, _library(), absolute_min=-50.0, margin_min=5.0)
    assert result.gesture is None
    assert result.runner_up is not None


def test_classify_rejects_below_absolute_threshold() -> None:
    far = np.array([100.0, 100.0, 100.0])
    result = classify(far, _library(), absolute_min=-5.0, margin_min=0.0)
    assert result.gesture is None
    assert result.log_likelihood < -5.0


def test_log_likelihood_is_highest_at_template_mean() -> None:
    template = build_template("v_sign", _samples([1.0, 2.0], 0.1, 30, 3))
    at_mean = log_likelihood(template.mu, template)
    off_mean = log_likelihood(template.mu + np.array([1.0, 1.0]), template)
    assert at_mean > off_mean


def test_save_and_load_roundtrip(tmp_path) -> None:
    template = build_template("thumbs_up", _samples([2.0, -1.0, 0.5], 0.08, 25, 4))
    path = tmp_path / "thumbs_up.json"
    save_template(path, template)
    loaded = load_template(path)
    assert loaded is not None
    assert loaded.name == "thumbs_up"
    assert loaded.dim == template.dim
    assert np.allclose(loaded.mu, template.mu)
    assert classify(
        template.mu,
        {loaded.name: loaded},
        absolute_min=-100.0,
        margin_min=0.0,
    ) == ClassificationResult(
        gesture="thumbs_up",
        log_likelihood=log_likelihood(template.mu, loaded),
        margin=np.inf,
        runner_up=None,
    )


def test_save_template_compact_is_smaller(tmp_path) -> None:
    template = build_template("v_sign", _samples([0.0] * 21, 0.05, 40, 5))
    indented = tmp_path / "indented.json"
    compact = tmp_path / "compact.json"
    save_template(indented, template)
    save_template(compact, template, compact=True)
    assert compact.stat().st_size < indented.stat().st_size


def test_load_gesture_library_reads_directory(tmp_path) -> None:
    for name, template in _library().items():
        save_template(tmp_path / f"{name}.json", template)
    loaded = load_gesture_library(tmp_path)
    assert set(loaded) == {"v_sign", "pinch_close"}
    assert classify(
        np.array([0.0, 0.0, 0.0]),
        loaded,
        absolute_min=-50.0,
        margin_min=1.0,
    ).gesture == "v_sign"


def test_build_template_rejects_invalid_samples() -> None:
    with pytest.raises(ValueError, match="2D array"):
        build_template("bad", np.array([1.0, 2.0]))
    with pytest.raises(ValueError, match="at least one feature"):
        build_template("bad", np.zeros((3, 0)))


def test_gesture_template_validation_error() -> None:
    with pytest.raises(ValueError, match="inv_variances"):
        GestureTemplate(
            name="bad",
            mu=np.zeros(4, dtype=np.float64),
            inv_variances=np.zeros(3, dtype=np.float64),
            log_det=0.0,
        )


def test_load_template_invalid_json(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="object"):
        load_template(path)


def test_classify_rejects_mismatched_feature_size() -> None:
    template = build_template("a", np.random.default_rng(0).normal(size=(8, 4)))
    result = classify(np.zeros(8), {"a": template}, absolute_min=-1000.0, margin_min=0.0)
    assert result.gesture is None
