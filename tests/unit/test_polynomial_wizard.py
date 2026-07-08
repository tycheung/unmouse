"""Unit tests for the nine-point polynomial calibration wizard."""

from __future__ import annotations

import pytest

from unmouse.config import Settings
from unmouse.gaze.calibration import calibration_path, load_calibration, save_calibration
from unmouse.launcher.calibration_overlay import create_calibration_overlay
from unmouse.launcher.calibration_wizards import (
    NUM_POLY_TARGETS,
    PolynomialWizardRunner,
    build_polynomial_targets,
)
from unmouse.launcher.wizard_common import (
    NoopWizardOverlayBackend,
    GazeSample,
    filter_samples_for_point,
    geometric_mean_gaze,
)


def test_build_polynomial_targets_returns_nine_grid_points() -> None:
    targets = build_polynomial_targets(800.0, 600.0, inset=0.05)
    assert len(targets) == NUM_POLY_TARGETS
    assert targets[0].x == 40.0
    assert targets[0].y == 30.0
    assert targets[4].x == 400.0
    assert targets[4].y == 300.0
    assert targets[8].x == 760.0
    assert targets[8].y == 570.0


def test_filter_samples_discards_initial_window() -> None:
    samples = [
        GazeSample(0.0, 0.1, 0.1),
        GazeSample(0.4, 0.2, 0.2),
        GazeSample(0.6, 0.9, 0.9),
        GazeSample(1.4, 1.0, 1.0),
        GazeSample(1.6, 0.0, 0.0),
    ]
    filtered = filter_samples_for_point(
        samples,
        point_started_s=0.0,
        discard_s=0.5,
        point_duration_s=1.5,
    )
    assert len(filtered) == 2
    assert filtered[0].x == 0.9


def test_geometric_mean_gaze_weights_by_confidence() -> None:
    samples = [
        GazeSample(0.0, 0.0, 0.0, confidence=1.0),
        GazeSample(0.0, 10.0, 0.0, confidence=3.0),
    ]
    mean_x, mean_y = geometric_mean_gaze(samples)
    assert mean_x == 7.5
    assert mean_y == 0.0


def _ideal_pairs(settings: Settings) -> list[tuple[float, float, float, float]]:
    targets = build_polynomial_targets(settings.screen_width, settings.screen_height)
    return [
        (
            target.x / settings.screen_width,
            target.y / settings.screen_height,
            target.x,
            target.y,
        )
        for target in targets
    ]


def test_runner_accepts_ideal_pairs_with_low_residual() -> None:
    settings = Settings(screen_width=800, screen_height=600, calibration_max_residual_px=75.0)
    runner = PolynomialWizardRunner(settings)
    outcome = runner.finish_from_pairs(_ideal_pairs(settings))
    assert outcome.success is True
    assert outcome.model is not None
    assert outcome.residual_px < 1.0
    assert outcome.retry_recommended is False


def test_runner_rejects_high_residual() -> None:
    settings = Settings(screen_width=800, screen_height=600, calibration_max_residual_px=10.0)
    pairs = _ideal_pairs(settings)
    pairs[0] = (0.0, 0.0, 999.0, 999.0)
    runner = PolynomialWizardRunner(settings)
    outcome = runner.finish_from_pairs(pairs)
    assert outcome.success is False
    assert outcome.retry_recommended is True
    assert "retry" in outcome.message.lower()


def test_runner_collects_samples_over_point_duration() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    runner = PolynomialWizardRunner(settings)
    targets = build_polynomial_targets(settings.screen_width, settings.screen_height)
    for index, target in enumerate(targets):
        runner.begin_point(float(index))
        for step in range(16):
            timestamp = float(index) + step * 0.1
            raw_x = target.x / settings.screen_width
            raw_y = target.y / settings.screen_height
            done = runner.add_sample(GazeSample(timestamp, raw_x, raw_y))
            assert done is (step == 15)
        if index < NUM_POLY_TARGETS - 1:
            assert runner.current_index == index + 1
    outcome = runner.outcome
    assert outcome is not None
    assert outcome.success is True


def test_wizard_save_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600, profile_name="lab")
    runner = PolynomialWizardRunner(settings)
    outcome = runner.finish_from_pairs(_ideal_pairs(settings))
    assert outcome.success is True
    assert outcome.model is not None
    save_calibration(calibration_path(settings), outcome.model)
    loaded = load_calibration(calibration_path(settings))
    assert loaded is not None
    assert loaded.x_coeffs == outcome.model.x_coeffs


def test_create_calibration_overlay_uses_fake_off_windows(monkeypatch) -> None:
    monkeypatch.setattr("unmouse.launcher.calibration_overlay.is_windows", lambda: False)
    overlay = create_calibration_overlay(prefer_win32=True)
    assert isinstance(overlay, NoopWizardOverlayBackend)


def test_polynomial_wizard_runner_requires_begin_point(settings: Settings) -> None:
    runner = PolynomialWizardRunner(settings)
    with pytest.raises(RuntimeError, match="begin_point"):
        runner.add_sample(GazeSample(0.0, 0.1, 0.2))


def test_geometric_mean_gaze_requires_samples() -> None:
    with pytest.raises(ValueError, match="at least one"):
        geometric_mean_gaze([])


def test_run_polynomial_wizard_completes_with_mocked_io(tmp_path, monkeypatch) -> None:
    import numpy as np

    from unmouse.gaze.tracker import NullGazeTracker
    from unmouse.launcher.calibration_wizards import run_polynomial_wizard

    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(
        screen_width=800,
        screen_height=600,
        profile_name="lab",
        calibration_point_duration_s=0.2,
        calibration_discard_s=0.0,
    )
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    clock = {"now": 0.0}

    class FakeSource:
        released = False

        def read(self) -> tuple[bool, np.ndarray]:
            return True, frame

        def release(self) -> None:
            self.released = True

    def fake_clock() -> float:
        return clock["now"]

    def fake_sleep(_seconds: float) -> None:
        clock["now"] += 0.05

    outcome = run_polynomial_wizard(
        settings,
        tracker=NullGazeTracker(x=0.5, y=0.5, confidence=1.0),
        frame_source=FakeSource(),
        overlay=NoopWizardOverlayBackend(),
        sleep=fake_sleep,
        clock=fake_clock,
        max_residual_px=500.0,
    )
    assert outcome.success is True
    assert outcome.model is not None
