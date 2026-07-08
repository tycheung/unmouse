from __future__ import annotations

import time

import numpy as np

from tests.fakes.broker import MockFrameSource
from unmouse.broker.video_broker import VideoBroker, drain_latest
from unmouse.config import Settings
from unmouse.gaze.pipeline import GazePipeline
from unmouse.gaze.thread import GazeWorker
from unmouse.gaze.tracker import NullGazeTracker
from unmouse.gestures.landmarks import NullHandLandmarkDetector
from unmouse.gestures.thread import GestureWorker
from unmouse.state import create_system_state


def test_broker_publishes_matching_frame_ids_to_both_queues() -> None:
    settings = Settings(broker_queue_size=2, screen_width=800, screen_height=600)
    state = create_system_state(settings)
    frames = [np.full((12, 12, 3), index, dtype=np.uint8) for index in range(8)]
    broker = VideoBroker(state, settings, source=MockFrameSource(frames))
    broker.start()

    deadline = time.time() + 2.0
    gaze_item = gesture_item = None
    while time.time() < deadline and (gaze_item is None or gesture_item is None):
        gaze_item = drain_latest(state.gaze_frame_queue)
        gesture_item = drain_latest(state.gesture_frame_queue)
        time.sleep(0.01)

    state.stop()
    broker.join(timeout=2.0)

    assert gaze_item is not None
    assert gesture_item is not None
    assert gaze_item[0] == gesture_item[0]
    assert np.array_equal(gaze_item[1], gesture_item[1])


def test_broker_consumers_run_without_races() -> None:
    settings = Settings(broker_queue_size=2, screen_width=800, screen_height=600)
    state = create_system_state(settings)
    frames = [np.zeros((16, 16, 3), dtype=np.uint8) for _ in range(12)]
    broker = VideoBroker(state, settings, source=MockFrameSource(frames))
    gaze_worker = GazeWorker(
        state,
        settings,
        tracker=NullGazeTracker(x=222.0, y=333.0, confidence=0.87),
        pipeline=GazePipeline(settings),
    )
    gesture_worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[]),
        library={},
    )
    broker.start()
    gaze_worker.start()
    gesture_worker.start()

    deadline = time.time() + 2.0
    snap = state.get_gaze()
    while time.time() < deadline and snap.x != 222.0:
        snap = state.get_gaze()
        time.sleep(0.01)

    state.stop()
    broker.join(timeout=2.0)
    gaze_worker.join(timeout=2.0)
    gesture_worker.join(timeout=2.0)

    assert snap.x == 222.0
    assert snap.y == 333.0
    assert gesture_worker.missed_hand_frames >= 1


def test_broker_copies_frames_before_fanout() -> None:
    settings = Settings(broker_queue_size=2)
    state = create_system_state(settings)
    frame = np.zeros((6, 6, 3), dtype=np.uint8)
    frame[0, 0, 0] = 7
    broker = VideoBroker(state, settings, source=MockFrameSource([frame]))
    broker.start()

    deadline = time.time() + 2.0
    drained = None
    while time.time() < deadline and drained is None:
        drained = drain_latest(state.gaze_frame_queue)
        time.sleep(0.01)

    frame[0, 0, 0] = 99
    state.stop()
    broker.join(timeout=2.0)

    assert drained is not None
    assert int(drained[1][0, 0, 0]) == 7


def test_broker_shutdown_joins_all_workers() -> None:
    settings = Settings(broker_queue_size=2, screen_width=800, screen_height=600)
    state = create_system_state(settings)
    frames = [np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(6)]
    broker = VideoBroker(state, settings, source=MockFrameSource(frames))
    gaze_worker = GazeWorker(
        state,
        settings,
        tracker=NullGazeTracker(x=100.0, y=100.0),
        pipeline=GazePipeline(settings),
    )
    gesture_worker = GestureWorker(
        state,
        settings,
        detector=NullHandLandmarkDetector(hands=[]),
        library={},
    )

    broker.start()
    gaze_worker.start()
    gesture_worker.start()
    time.sleep(0.2)
    state.stop()

    broker.join(timeout=2.0)
    gaze_worker.join(timeout=2.0)
    gesture_worker.join(timeout=2.0)

    assert not state.is_running()
