"""Unit tests for gesture enrollment panel session."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from unmouse.config import Settings
from unmouse.gestures.enrollment import (
    DEFAULT_GESTURE_NAMES,
    enroll_from_samples,
    generate_default_templates,
    profile_gestures_dir,
    samples_from_landmarks,
    synthetic_landmarks,
)
from unmouse.gestures.landmarks import MockHandLandmarkDetector
from unmouse.launcher.enroll_ui import (
    GestureEnrollmentSession,
    profile_has_gesture_templates,
)


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return Settings(screen_width=800, screen_height=600, profile_name="lab")


class FakeCapture:
    def __init__(self, frame: np.ndarray) -> None:
        self._frame = frame
        self.released = False

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, np.ndarray]:
        return True, self._frame.copy()

    def release(self) -> None:
        self.released = True


def test_profile_has_gesture_templates(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    assert profile_has_gesture_templates(settings) is False
    generate_default_templates(profile_gestures_dir(settings.profile_dir))
    assert profile_has_gesture_templates(settings) is True


def test_enrollment_session_state_and_capture(tmp_path, monkeypatch, open_palm_landmarks) -> None:
    settings = _settings(tmp_path, monkeypatch)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    detector = MockHandLandmarkDetector((open_palm_landmarks,))
    clock = {"now": 0.0}

    def fake_clock() -> float:
        return clock["now"]

    def fake_sleep(seconds: float) -> None:
        clock["now"] += seconds

    session = GestureEnrollmentSession(
        settings,
        detector=detector,
        clock=fake_clock,
        sleep=fake_sleep,
    )
    session._capture = FakeCapture(frame)
    state = session.get_state()
    assert state["gesture"] == DEFAULT_GESTURE_NAMES[0]
    assert state["gesture_count"] == 3

    result = session.capture_current_gesture()
    assert result.ok is True
    assert result.gesture == "v_sign"
    assert profile_has_gesture_templates(settings) is False

    for expected in DEFAULT_GESTURE_NAMES[1:]:
        result = session.capture_current_gesture()
        assert result.ok is True
        assert result.gesture == expected
    assert session.done is True
    assert profile_has_gesture_templates(settings) is True


def test_enrollment_preview_encodes_jpeg(tmp_path, monkeypatch, open_palm_landmarks) -> None:
    settings = _settings(tmp_path, monkeypatch)
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    detector = MockHandLandmarkDetector((open_palm_landmarks,))
    session = GestureEnrollmentSession(settings, detector=detector)
    session._capture = FakeCapture(frame)
    preview = session.grab_preview()
    assert preview.preview_jpeg is not None
    assert preview.hand_detected is True


def test_enrollment_capture_requires_hand_samples(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    detector = MockHandLandmarkDetector(())
    clock = {"now": 0.0}
    session = GestureEnrollmentSession(
        settings,
        detector=detector,
        clock=lambda: clock["now"],
        sleep=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )
    session._capture = FakeCapture(frame)
    result = session.capture_current_gesture()
    assert result.ok is False
    assert "No hand samples" in result.message


def test_enrollment_open_raises_when_camera_unavailable(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    capture = MagicMock()
    capture.isOpened.return_value = False
    monkeypatch.setattr("unmouse.launcher.enroll_ui.cv2.VideoCapture", lambda _i: capture)
    session = GestureEnrollmentSession(settings, detector=MockHandLandmarkDetector())
    with pytest.raises(RuntimeError, match="Unable to open camera"):
        session.open()


def test_enroll_from_samples_still_used_by_session(tmp_path) -> None:
    hand = synthetic_landmarks("thumbs_up")
    samples = samples_from_landmarks(hand, count=20, seed=1)
    path = enroll_from_samples("thumbs_up", samples, tmp_path)
    assert path.name == "thumbs_up.json"
