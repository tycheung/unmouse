from __future__ import annotations

import time

import numpy as np

from tests.fakes.broker import MockFrameSource
from tests.fakes.landmarks import NullHandLandmarkDetector
from unmouse.broker.video_broker import VideoBroker
from unmouse.config import Settings
from unmouse.gestures.fsm import ClickFsm
from unmouse.gestures.scroll_fsm import ScrollFsm
from unmouse.gestures.thread import GestureWorker
from unmouse.state import create_system_state


def test_gesture_worker_increments_missed_hand_frames() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[]),
        library={},
    )
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    worker.process_frame(frame, timestamp_s=0.0)
    worker.process_frame(frame, timestamp_s=0.1)
    assert worker.missed_hand_frames == 2


def test_gesture_worker_resets_missed_frames_when_hand_present(open_palm_landmarks) -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[open_palm_landmarks]),
        library={},
    )
    worker.process_frame(np.zeros((24, 32, 3), dtype=np.uint8), timestamp_s=0.0)
    assert worker.missed_hand_frames == 0


def test_gesture_worker_updates_click_mode_from_fsm(open_palm_landmarks) -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[open_palm_landmarks]),
        library={},
        click_fsm=ClickFsm(v_sign_loss_debounce_s=0.3),
        scroll_fsm=ScrollFsm(activation_delay_s=0.0),
    )
    state.set_gaze(100.0, 200.0, 0.9)
    worker._apply_fsms(
        timestamp_s=0.0,
        gaze_x=100.0,
        gaze_y=200.0,
        v_sign_active=True,
        pinch_close=False,
        right_click=False,
        thumbs_up_active=False,
        thumb_angle_deg=0.0,
    )
    assert state.click_mode is True


def test_gesture_worker_consumes_broker_queue() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    broker = VideoBroker(state, settings, source=MockFrameSource([frame]))
    worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[]),
        library={},
    )
    broker.start()
    worker.start()
    time.sleep(0.2)
    state.stop()
    worker.join(timeout=2.0)
    broker.join(timeout=2.0)
    assert worker.missed_hand_frames >= 1
