"""Gap-filling unit tests to raise coverage across core modules."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from unmouse.config import Settings
from unmouse.gestures.enrollment import capture_angle_samples
from unmouse.gestures.fsm import ClickEvent
from unmouse.gestures.landmarks import MockHandLandmarkDetector, draw_hand_skeleton
from unmouse.gestures.mle import (
    GestureTemplate,
    build_template,
    classify,
    fit_gaussian,
    load_template,
)
from unmouse.gestures.scroll_fsm import ScrollTick
from unmouse.launcher.polynomial_wizard import (
    FakeWizardOverlayBackend,
    GazeSample,
    PolynomialWizardRunner,
    geometric_mean_gaze,
    run_polynomial_wizard,
)
from unmouse.main import run, run_engine
from unmouse.overlay.indicator import FakeIndicatorBackend, GazeIndicatorOverlay, IndicatorState
from unmouse.state import create_system_state


def test_state_offer_replaces_oldest_item_on_full_queue() -> None:
    state = create_system_state(Settings(broker_queue_size=1))
    assert state.click_event_queue is not None
    state.enqueue_click_event(ClickEvent(button="left", x=1.0, y=2.0))
    state.enqueue_click_event(ClickEvent(button="right", x=3.0, y=4.0))
    event = state.click_event_queue.get_nowait()
    assert event.button == "right"


def test_state_offer_handles_none_queue() -> None:
    from unmouse.state import SystemState

    state = SystemState(gaze_x=0.0, gaze_y=0.0, click_event_queue=None)
    state.enqueue_click_event(ClickEvent(button="left", x=0.0, y=0.0))


def test_state_scroll_tick_updates_direction() -> None:
    state = create_system_state(Settings())
    state.enqueue_scroll_tick(ScrollTick(x=1.0, y=2.0, delta=-4.0))
    assert state.scroll_up is False


def test_run_engine_handles_keyboard_interrupt(settings: Settings) -> None:
    state = create_system_state(settings)
    with patch("unmouse.main.time.sleep", side_effect=KeyboardInterrupt):
        run_engine(settings, state)
    assert state.is_running() is False


def test_run_opens_control_panel() -> None:
    with patch("unmouse.launcher.panel.run") as panel_run:
        run()
    panel_run.assert_called_once()


def test_fit_gaussian_rejects_invalid_samples() -> None:
    with pytest.raises(ValueError, match="2D array"):
        fit_gaussian(np.array([1.0, 2.0]))
    with pytest.raises(ValueError, match="at least one feature"):
        fit_gaussian(np.zeros((3, 0)))


def test_gesture_template_validation_errors() -> None:
    mu = np.zeros(4, dtype=np.float64)
    with pytest.raises(ValueError, match="inv_variances"):
        GestureTemplate(name="bad", mu=mu, log_det=0.0, diagonal=True, inv_variances=None)
    with pytest.raises(ValueError, match="precision"):
        GestureTemplate(name="bad", mu=mu, log_det=0.0, diagonal=False, precision=None)


def test_load_template_invalid_json(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="object"):
        load_template(path)


def test_classify_rejects_mismatched_feature_size() -> None:
    samples = np.random.default_rng(0).normal(size=(8, 4))
    template = build_template("a", samples, force_diagonal=True)
    result = classify(np.zeros(8), {"a": template}, absolute_min=-1000.0, margin_min=0.0)
    assert result.gesture is None


def test_capture_angle_samples_with_mock_camera(open_palm_landmarks) -> None:
    frames = [np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(4)]

    class FakeCapture:
        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, np.ndarray]:
            if frames:
                return True, frames.pop(0)
            return False, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self) -> None:
            return None

    class FakeDetector:
        def detect(self, frame: np.ndarray) -> object:
            from unmouse.gestures.landmarks import LandmarkDetectionResult

            _ = frame
            return LandmarkDetectionResult(hands=(open_palm_landmarks,))

        def close(self) -> None:
            return None

    with patch("cv2.VideoCapture", return_value=FakeCapture()):
        with patch(
            "unmouse.gestures.landmarks.MediaPipeHandDetector",
            return_value=FakeDetector(),
        ):
            samples = capture_angle_samples(
                duration_s=0.05,
                warmup_s=0.0,
                target_fps=100.0,
            )
    assert samples.shape[0] >= 1


def test_capture_angle_samples_requires_open_camera() -> None:
    capture = MagicMock()
    capture.isOpened.return_value = False
    detector = MagicMock()
    with patch("cv2.VideoCapture", return_value=capture):
        with patch(
            "unmouse.gestures.landmarks.MediaPipeHandDetector",
            return_value=detector,
        ):
            with pytest.raises(RuntimeError, match="unable to open camera"):
                capture_angle_samples(duration_s=0.01, warmup_s=0.0, target_fps=30.0)
    detector.close.assert_called_once()


def test_draw_hand_skeleton_returns_copy(test_frame, open_palm_landmarks) -> None:
    mock_drawing = MagicMock()
    mock_drawing.DrawingSpec = MagicMock()
    mock_hands = MagicMock()
    mock_hands.HAND_CONNECTIONS = object()
    fake_mp = MagicMock()
    fake_mp.solutions.hands = mock_hands
    fake_mp.solutions.drawing_utils = mock_drawing
    fake_mp.framework.formats.landmark_pb2.NormalizedLandmarkList.return_value = MagicMock(
        landmark=MagicMock(add=MagicMock(return_value=MagicMock()))
    )
    with patch.dict("sys.modules", {"mediapipe": fake_mp}):
        output = draw_hand_skeleton(test_frame, (open_palm_landmarks,))
    assert output.shape == test_frame.shape
    assert output is not test_frame


def test_create_hand_detector_falls_back_without_mediapipe(monkeypatch) -> None:
    monkeypatch.setattr(
        "unmouse.gestures.landmarks.MediaPipeHandDetector",
        MagicMock(side_effect=ImportError("missing")),
    )
    from unmouse.gestures.landmarks import create_hand_detector

    detector = create_hand_detector(prefer_mediapipe=True)
    assert isinstance(detector, MockHandLandmarkDetector)


def test_polynomial_wizard_runner_requires_begin_point(settings: Settings) -> None:
    runner = PolynomialWizardRunner(settings)
    with pytest.raises(RuntimeError, match="begin_point"):
        runner.add_sample(GazeSample(0.0, 0.1, 0.2))


def test_geometric_mean_gaze_requires_samples() -> None:
    with pytest.raises(ValueError, match="at least one"):
        geometric_mean_gaze([])


def test_run_polynomial_wizard_completes_with_mocked_io(tmp_path, monkeypatch) -> None:
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

    from unmouse.gaze.tracker import MockGazeTracker

    outcome = run_polynomial_wizard(
        settings,
        tracker=MockGazeTracker(x=0.5, y=0.5, confidence=1.0),
        frame_source=FakeSource(),
        overlay=FakeWizardOverlayBackend(),
        sleep=fake_sleep,
        clock=fake_clock,
        max_residual_px=500.0,
    )
    assert outcome.success is True
    assert outcome.model is not None


def test_gaze_indicator_overlay_background_loop() -> None:
    backend = FakeIndicatorBackend()
    overlay = GazeIndicatorOverlay(
        backend=backend,
        target_fps=30.0,
        state_provider=lambda: IndicatorState(x=1.0, y=2.0),
    )
    overlay.start()
    deadline = time.time() + 1.0
    while time.time() < deadline and not backend.updates:
        time.sleep(0.01)
    overlay.stop()
    assert backend.updates
