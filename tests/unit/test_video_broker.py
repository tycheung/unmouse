import time

import numpy as np

from tests.fakes.broker import MockFrameSource
from unmouse.broker.video_broker import VideoBroker, drain_latest
from unmouse.config import Settings
from unmouse.state import create_system_state


def test_broker_publishes_to_both_queues() -> None:
    settings = Settings(broker_queue_size=2)
    state = create_system_state(settings)
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    source = MockFrameSource([frame, frame])
    broker = VideoBroker(state, settings, source=source)
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
    assert gaze_item[1].shape == (48, 64, 3)
    assert source.released is True


def test_drain_latest_returns_most_recent_only() -> None:
    settings = Settings()
    state = create_system_state(settings)
    queue = state.gaze_frame_queue
    assert queue is not None
    f1 = np.ones((2, 2, 3), dtype=np.uint8)
    f2 = np.zeros((2, 2, 3), dtype=np.uint8)
    queue.put((1, f1))
    queue.put((2, f2))
    latest = drain_latest(queue)
    assert latest is not None
    assert latest[0] == 2
    assert bool(latest[1].any()) is False
