from __future__ import annotations

from unmouse.config import Settings
from unmouse.gaze.offset_profile import (
    GRID_COLS,
    GRID_ROWS,
    NUM_SAMPLES,
    OffsetProfile,
    apply_offset_profile,
    build_calibration_targets,
    build_profile,
    build_profile_from_measurements,
    interpolate_offset_delta,
    load_offset_profile,
    load_offset_profile_for_settings,
    offset_profile_path,
    sample_from_measurement,
    save_offset_profile,
    vertex_delta_grid,
)


def _uniform_profile(
    dx: float,
    dy: float,
    *,
    width: float = 800.0,
    height: float = 600.0,
) -> OffsetProfile:
    targets = build_calibration_targets(width, height)
    samples = tuple(
        sample_from_measurement(tx, ty, tx - dx, ty - dy) for tx, ty in targets
    )
    return build_profile(width, height, samples)


def test_build_calibration_targets_returns_sixteen_points() -> None:
    targets = build_calibration_targets(800.0, 600.0, corner_inset=0.05)
    assert len(targets) == NUM_SAMPLES
    assert targets[0] == (40.0, 30.0)
    assert targets[1] == (760.0, 30.0)
    assert targets[4] == (100.0, 100.0)


def test_uniform_offset_profile_applies_constant_delta() -> None:
    profile = _uniform_profile(12.0, -8.0)
    x, y = apply_offset_profile(400.0, 300.0, profile)
    assert x == 412.0
    assert y == 292.0


def test_apply_passthrough_without_profile() -> None:
    assert apply_offset_profile(10.0, 20.0, None) == (10.0, 20.0)


def test_bilinear_interpolation_between_cell_centers() -> None:
    profile = _uniform_profile(0.0, 0.0)
    corner_samples = list(profile.corners)
    cell_samples = list(profile.cells)
    cell_samples[0] = sample_from_measurement(
        cell_samples[0].target_x,
        cell_samples[0].target_y,
        cell_samples[0].target_x - 20.0,
        cell_samples[0].target_y,
    )
    cell_samples[1] = sample_from_measurement(
        cell_samples[1].target_x,
        cell_samples[1].target_y,
        cell_samples[1].target_x + 20.0,
        cell_samples[1].target_y,
    )
    custom = build_profile(800.0, 600.0, corner_samples + cell_samples)
    left = interpolate_offset_delta(150.0, 100.0, custom)
    right = interpolate_offset_delta(250.0, 100.0, custom)
    assert left[0] != right[0]


def test_vertex_grid_shape() -> None:
    grid = vertex_delta_grid(_uniform_profile(1.0, 2.0))
    assert grid.shape == (GRID_ROWS + 1, GRID_COLS + 1, 2)


def test_build_profile_from_measurements() -> None:
    targets = build_calibration_targets(640.0, 480.0)
    measurements = tuple((tx + 5.0, ty - 3.0) for tx, ty in targets)
    profile = build_profile_from_measurements(640.0, 480.0, measurements)
    assert profile.screen_width == 640.0
    assert profile.corners[0].delta_x == -5.0
    assert profile.corners[0].delta_y == 3.0


def test_save_and_load_roundtrip(tmp_path) -> None:
    profile = _uniform_profile(4.0, -2.0, width=1024.0, height=768.0)
    path = tmp_path / "offset_profile.json"
    save_offset_profile(path, profile)
    loaded = load_offset_profile(path)
    assert loaded is not None
    assert loaded.screen_width == profile.screen_width
    assert loaded.corners[2].delta_y == profile.corners[2].delta_y
    assert apply_offset_profile(100.0, 100.0, loaded) == apply_offset_profile(100.0, 100.0, profile)


def test_offset_profile_path_uses_settings_profile_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(profile_name="lab")
    assert offset_profile_path(settings) == (
        tmp_path / "unmouse" / "profiles" / "lab" / "offset_profile.json"
    )
    assert load_offset_profile_for_settings(settings) is None
