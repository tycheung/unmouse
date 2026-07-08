from __future__ import annotations

import time

import numpy as np

from tests.conftest import load_landmark_fixture
from tests.fakes.arbitrator import NoopActionDriver, StaticSnapProvider
from tests.fakes.broker import MockFrameSource
from tests.fakes.gaze import FakeGazeTracker
from unmouse.arbitrator.controller import ActionController
from unmouse.arbitrator.snap import SnapRect, SnapTarget
from unmouse.broker.video_broker import VideoBroker
from unmouse.config import Settings
from unmouse.gaze.thread import GazeWorker
from unmouse.gaze.tracker import GazeSample
from unmouse.gestures.fsm import ClickFsm
from unmouse.gestures.landmarks import HandLandmarks, LandmarkDetectionResult
from unmouse.gestures.scroll_fsm import ScrollFsm
from unmouse.gestures.thread import GestureWorker
from unmouse.state import create_system_state


class _SequenceDetector:
    def __init__(self, hands: list[HandLandmarks | None]) -> None:
        self._hands = hands
        self._index = 0

    def detect(self, frame: np.ndarray) -> LandmarkDetectionResult:
        _ = frame
        hand = self._hands[min(self._index, len(self._hands) - 1)]
        self._index += 1
        if hand is None:
            return LandmarkDetectionResult(hands=())
        return LandmarkDetectionResult(hands=(hand,))


def test_gaze_worker_feeds_controller_cursor_moves() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    broker = VideoBroker(state, settings, source=MockFrameSource([frame] * 10))
    gaze_worker = GazeWorker(
        state,
        settings,
        tracker=FakeGazeTracker(sample=GazeSample(x=450.0, y=275.0, fixation=0.92)),
    )
    driver = NoopActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )

    broker.start()
    gaze_worker.start()
    controller.start()

    deadline = time.time() + 2.0
    while time.time() < deadline:
        snap = state.get_gaze()
        if driver.moves and driver.moves[-1] == (int(round(snap.x)), int(round(snap.y))):
            if abs(snap.x - settings.screen_width / 2) > 1.0:
                break
        time.sleep(0.01)

    state.stop()
    controller.join(timeout=2.0)
    gaze_worker.join(timeout=2.0)
    broker.join(timeout=2.0)

    snap = state.get_gaze()
    assert driver.moves
    assert driver.moves[-1] == (int(round(snap.x)), int(round(snap.y)))
    assert snap.x == 450.0
    assert snap.y == 275.0


def test_gaze_to_action_snaps_cursor_to_target() -> None:
    settings = Settings(screen_width=800, screen_height=600, snap_radius_px=80.0)
    state = create_system_state(settings)
    state.set_gaze(103.0, 97.0, 0.95)
    driver = NoopActionDriver()
    snap_target = SnapTarget(
        target_id="save",
        bounds=SnapRect(x=90.0, y=90.0, width=20.0, height=20.0),
    )
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider((snap_target,)),
        enable_overlay=False,
    )
    controller.tick(timestamp_s=0.0)
    assert driver.moves[-1] == (100, 100)


def test_gaze_to_action_executes_gesture_click_at_gaze_point() -> None:
    settings = Settings(
        screen_width=800,
        screen_height=600,
        scroll_activation_delay_ms=0,
    )
    state = create_system_state(settings)
    state.set_gaze(610.0, 410.0, 0.93)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    from unmouse.gestures.enrollment import default_gestures_dir
    from unmouse.gestures.mle import load_gesture_library

    v_sign = load_landmark_fixture("v_sign")
    pinch_close = load_landmark_fixture("pinch_close")
    gesture_worker = GestureWorker(
        state,
        settings,
        detector=_SequenceDetector([v_sign, pinch_close]),
        library=load_gesture_library(default_gestures_dir()),
        click_fsm=ClickFsm(),
        scroll_fsm=ScrollFsm(activation_delay_s=0.0),
    )
    driver = NoopActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )
    controller.start()
    gesture_worker.process_frame(frame, timestamp_s=0.0)
    gesture_worker.process_frame(frame, timestamp_s=0.05)

    deadline = time.time() + 2.0
    while time.time() < deadline and not driver.clicks:
        time.sleep(0.01)

    controller.stop()
    controller.join(timeout=2.0)

    assert driver.clicks == [(610, 410, "left")]
