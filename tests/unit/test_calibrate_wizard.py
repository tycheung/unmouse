from __future__ import annotations

import numpy as np

from tests.fakes.gaze import FakeGazeTracker
from unmouse.config import Settings
from unmouse.gaze.tracker import gaze_model_path, load_gaze_model
from unmouse.launcher.calibration_wizards import run_calibration_wizard
from unmouse.launcher.wizard_common import NoopWizardOverlayBackend

_TARGETS = ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (0.25, 0.75))


class _FrameSource:
    def __init__(self) -> None:
        self.released = False
        self._frame = np.zeros((8, 8, 3), dtype=np.uint8)

    def read(self) -> tuple[bool, np.ndarray]:
        return True, self._frame

    def release(self) -> None:
        self.released = True


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return Settings(
        screen_width=800,
        screen_height=600,
        profile_name="lab",
        gaze_calibration_points=len(_TARGETS),
    )


def test_run_calibration_wizard_saves_model(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    source = _FrameSource()
    overlay = NoopWizardOverlayBackend()
    outcome = run_calibration_wizard(
        settings,
        tracker=FakeGazeTracker(targets=_TARGETS),
        frame_source=source,
        overlay=overlay,
        sleep=lambda _s: None,
    )
    assert outcome.success is True
    assert load_gaze_model(settings) == b"model-bytes"
    assert source.released is True
    assert overlay.shown == []


def test_run_calibration_wizard_shows_each_target(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    shown: list[tuple[float, float, str]] = []

    class RecordingOverlay(NoopWizardOverlayBackend):
        def show_target(self, x: float, y: float, *, label: str) -> None:
            shown.append((x, y, label))

    run_calibration_wizard(
        settings,
        tracker=FakeGazeTracker(targets=_TARGETS),
        frame_source=_FrameSource(),
        overlay=RecordingOverlay(),
        sleep=lambda _s: None,
    )
    assert len(shown) == len(_TARGETS)
    assert "1/4" in shown[0][2]


def test_run_calibration_wizard_reports_incomplete(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    outcome = run_calibration_wizard(
        settings,
        tracker=FakeGazeTracker(targets=_TARGETS[:2]),
        frame_source=_FrameSource(),
        overlay=NoopWizardOverlayBackend(),
        sleep=lambda _s: None,
    )
    assert outcome.success is False
    assert "before all points" in outcome.message
    assert not gaze_model_path(settings).is_file()
