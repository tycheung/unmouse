from __future__ import annotations

import numpy as np
import pytest

from unmouse.config import Settings
from unmouse.gaze.calibration import calibration_path, fit_calibration, save_calibration
from unmouse.gaze.offset_profile import (
    NUM_SAMPLES,
    load_offset_profile,
    offset_profile_path,
)
from unmouse.launcher.calibration_wizards import (
    NUM_OFFSET_TARGETS,
    OffsetWizardOutcome,
    build_offset_targets,
    build_polynomial_targets,
    create_offset_stare_runner,
    offset_outcome_from_measurements,
    polynomial_prerequisite_message,
    run_offset_wizard,
)
from unmouse.launcher.wizard_common import GazeSample, NoopWizardOverlayBackend


def _save_identity_polynomial(settings: Settings) -> None:
    targets = build_polynomial_targets(settings.screen_width, settings.screen_height)
    pairs = [
        (
            target.x / settings.screen_width,
            target.y / settings.screen_height,
            target.x,
            target.y,
        )
        for target in targets
    ]
    save_calibration(calibration_path(settings), fit_calibration(pairs))


def test_build_offset_targets_returns_sixteen_points() -> None:
    targets = build_offset_targets(800.0, 600.0)
    assert len(targets) == NUM_OFFSET_TARGETS
    assert targets[0].x == 40.0
    assert targets[0].y == 30.0
    assert targets[4].index == 4


def test_polynomial_prerequisite_message_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600, profile_name="lab")
    assert polynomial_prerequisite_message(settings) is not None


def test_run_offset_wizard_requires_polynomial(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600, profile_name="lab")
    outcome = run_offset_wizard(
        settings,
        overlay=NoopWizardOverlayBackend(),
    )
    assert outcome.success is False
    assert "polynomial" in outcome.message.lower()


def test_runner_finish_from_measurements_saves_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600, profile_name="lab")
    _save_identity_polynomial(settings)
    from unmouse.gaze.calibration import load_calibration

    model = load_calibration(calibration_path(settings))
    assert model is not None
    targets = build_offset_targets(settings.screen_width, settings.screen_height)
    measurements = [(target.x, target.y) for target in targets]
    outcome = offset_outcome_from_measurements(
        settings,
        targets=targets,
        measurements=measurements,
    )
    assert outcome.success is True
    loaded = load_offset_profile(offset_profile_path(settings))
    assert loaded is not None
    assert loaded.screen_width == 800.0


def test_runner_collects_samples_over_point_duration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(
        screen_width=800,
        screen_height=600,
        profile_name="lab",
        calibration_point_duration_s=1.5,
        calibration_discard_s=0.0,
    )
    _save_identity_polynomial(settings)
    from unmouse.gaze.calibration import load_calibration

    model = load_calibration(calibration_path(settings))
    assert model is not None
    targets = build_offset_targets(settings.screen_width, settings.screen_height)
    runner = create_offset_stare_runner(settings, model)
    for index, target in enumerate(targets):
        runner.begin_point(float(index))
        for step in range(16):
            timestamp = float(index) + step * 0.1
            raw_x = target.x / settings.screen_width
            raw_y = target.y / settings.screen_height
            done = runner.add_sample(GazeSample(timestamp, raw_x, raw_y))
            assert done is (step == 15)
        if index < NUM_SAMPLES - 1:
            assert runner.current_index == index + 1
    outcome = runner.outcome
    assert outcome is not None
    assert outcome.success is True


def test_run_offset_wizard_completes_with_mocked_io(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(
        screen_width=800,
        screen_height=600,
        profile_name="lab",
        calibration_point_duration_s=0.2,
        calibration_discard_s=0.0,
    )
    _save_identity_polynomial(settings)
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

    from unmouse.gaze.tracker import NullGazeTracker

    outcome = run_offset_wizard(
        settings,
        tracker=NullGazeTracker(x=0.5, y=0.5, confidence=1.0),
        frame_source=FakeSource(),
        overlay=NoopWizardOverlayBackend(),
        sleep=fake_sleep,
        clock=fake_clock,
    )
    assert isinstance(outcome, OffsetWizardOutcome)
    assert outcome.success is True
    assert load_offset_profile(offset_profile_path(settings)) is not None


def test_runner_requires_begin_point(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600, profile_name="lab")
    _save_identity_polynomial(settings)
    from unmouse.gaze.calibration import load_calibration

    model = load_calibration(calibration_path(settings))
    assert model is not None
    runner = create_offset_stare_runner(settings, model)
    with pytest.raises(RuntimeError, match="begin_point"):
        runner.add_sample(GazeSample(0.0, 0.1, 0.2))
