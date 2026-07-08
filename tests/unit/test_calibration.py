import numpy as np

from unmouse.gaze.calibration import (
    apply_calibration,
    fit_calibration,
    load_calibration,
    mean_residual_error,
    save_calibration,
)


def _synthetic_points() -> list[tuple[float, float, float, float]]:
    rng = np.random.default_rng(0)
    points: list[tuple[float, float, float, float]] = []
    for _ in range(9):
        raw_x = float(rng.uniform(0.0, 1.0))
        raw_y = float(rng.uniform(0.0, 1.0))
        screen_x = 100 + 800 * raw_x + 20 * raw_y**2
        screen_y = 50 + 600 * raw_y + 15 * raw_x * raw_y
        points.append((raw_x, raw_y, screen_x, screen_y))
    return points


def test_fit_recovers_synthetic_mapping() -> None:
    points = _synthetic_points()
    model = fit_calibration(points)
    error = mean_residual_error(points, model)
    assert error < 1.0


def test_apply_passthrough_without_model() -> None:
    assert apply_calibration(10.0, 20.0, None) == (10.0, 20.0)


def test_save_and_load_roundtrip(tmp_path) -> None:
    points = _synthetic_points()
    model = fit_calibration(points)
    path = tmp_path / "calibration.json"
    save_calibration(path, model)
    loaded = load_calibration(path)
    assert loaded is not None
    assert loaded.x_coeffs == model.x_coeffs
    assert loaded.y_coeffs == model.y_coeffs
