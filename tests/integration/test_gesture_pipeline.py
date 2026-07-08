from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

from tests.conftest import load_landmark_fixture
from unmouse.config import Settings
from unmouse.gestures.angles import compute_feature_vector
from unmouse.gestures.enrollment import default_gestures_dir, synthetic_landmarks
from unmouse.gestures.fsm import ClickFsm
from unmouse.gestures.landmarks import (
    HandLandmarks,
    LandmarkDetectionResult,
    NullHandLandmarkDetector,
)
from unmouse.gestures.mle import classify, load_gesture_library
from unmouse.gestures.scroll_fsm import ScrollFsm
from unmouse.gestures.thread import GestureWorker
from unmouse.state import create_system_state


class SequenceHandDetector:
    def __init__(self, hands: Sequence[HandLandmarks | None]) -> None:
        self._hands = tuple(hands)
        self._index = 0

    def detect(self, frame: np.ndarray) -> LandmarkDetectionResult:
        _ = frame
        if self._index >= len(self._hands):
            hand = self._hands[-1]
        else:
            hand = self._hands[self._index]
        self._index += 1
        if hand is None:
            return LandmarkDetectionResult(hands=())
        return LandmarkDetectionResult(hands=(hand,))


@pytest.fixture
def settings() -> Settings:
    return Settings(
        screen_width=1920,
        screen_height=1080,
        scroll_activation_delay_ms=0,
    )


@pytest.fixture
def gesture_library():
    return load_gesture_library(default_gestures_dir())


@pytest.mark.parametrize("gesture", ["v_sign", "pinch_close", "thumbs_up"])
def test_landmark_fixtures_match_synthetic_poses(gesture: str) -> None:
    fixture = load_landmark_fixture(gesture)
    synthetic = synthetic_landmarks(gesture)
    assert fixture.points == synthetic.points
    assert fixture.handedness == synthetic.handedness


@pytest.mark.parametrize("gesture", ["v_sign", "pinch_close", "thumbs_up"])
def test_landmark_fixtures_classify_with_bundled_templates(
    gesture: str,
    gesture_library,
    settings: Settings,
) -> None:
    hand = load_landmark_fixture(gesture)
    theta = compute_feature_vector(hand)
    result = classify(
        theta,
        gesture_library,
        absolute_min=settings.mle_absolute_min,
        margin_min=settings.mle_margin_min,
    )
    assert result.gesture == gesture


def test_pipeline_v_sign_arms_click_mode(settings: Settings, gesture_library) -> None:
    state = create_system_state(settings)
    state.set_gaze(640.0, 360.0, 0.95)
    worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[load_landmark_fixture("v_sign")]),
        library=gesture_library,
        click_fsm=ClickFsm(),
        scroll_fsm=ScrollFsm(activation_delay_s=0.0),
    )
    worker.process_frame(np.zeros((24, 32, 3), dtype=np.uint8), timestamp_s=0.0)
    assert state.click_mode is True
    assert state.scroll_active is False


def test_pipeline_pinch_emits_click_event(settings: Settings, gesture_library) -> None:
    state = create_system_state(settings)
    state.set_gaze(700.0, 420.0, 0.95)
    worker = GestureWorker(
        state,
        settings,
        detector=SequenceHandDetector(
            [load_landmark_fixture("v_sign"), load_landmark_fixture("pinch_close")],
        ),
        library=gesture_library,
        click_fsm=ClickFsm(),
        scroll_fsm=ScrollFsm(activation_delay_s=0.0),
    )
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    worker.process_frame(frame, timestamp_s=0.0)
    worker.process_frame(frame, timestamp_s=0.05)
    assert state.click_mode is False
    assert state.click_event_queue is not None
    event = state.click_event_queue.get_nowait()
    assert event.x == 700.0
    assert event.y == 420.0
    assert event.button == "left"


def test_pipeline_thumbs_up_emits_scroll_tick(settings: Settings, gesture_library) -> None:
    state = create_system_state(settings)
    state.set_gaze(500.0, 400.0, 0.95)
    worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[load_landmark_fixture("thumbs_up")]),
        library=gesture_library,
        click_fsm=ClickFsm(),
        scroll_fsm=ScrollFsm(activation_delay_s=0.0),
    )
    worker.process_frame(np.zeros((24, 32, 3), dtype=np.uint8), timestamp_s=0.0)
    worker.process_frame(np.zeros((24, 32, 3), dtype=np.uint8), timestamp_s=0.01)
    assert state.scroll_active is True
    assert state.scroll_tick_queue is not None
    tick = state.scroll_tick_queue.get_nowait()
    assert tick.x == 500.0
    assert tick.y == 400.0
    assert tick.delta != 0.0


def test_pipeline_no_hand_increments_missed_frames(settings: Settings, gesture_library) -> None:
    state = create_system_state(settings)
    worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[]),
        library=gesture_library,
    )
    worker.process_frame(np.zeros((24, 32, 3), dtype=np.uint8), timestamp_s=0.0)
    assert worker.missed_hand_frames == 1
    assert state.click_mode is False
    assert state.scroll_active is False
