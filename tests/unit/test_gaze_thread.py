import time

import numpy as np

from tests.fakes.broker import MockFrameSource
from tests.fakes.gaze import FakeGazeTracker
from unmouse.broker.video_broker import VideoBroker, drain_latest
from unmouse.config import Settings
from unmouse.gaze.thread import GazeWorker
from unmouse.gaze.tracker import GazeSample
from unmouse.state import create_system_state


def test_gaze_worker_updates_state_from_queue() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    broker = VideoBroker(state, settings, source=MockFrameSource([frame, frame]))
    tracker = FakeGazeTracker(sample=GazeSample(x=321.0, y=210.0, fixation=0.88))
    worker = GazeWorker(state, settings, tracker=tracker)
    broker.start()
    worker.start()

    deadline = time.time() + 2.0
    snap = state.get_gaze()
    while time.time() < deadline and snap.x != 321.0:
        snap = state.get_gaze()
        time.sleep(0.01)

    state.stop()
    worker.join(timeout=2.0)
    broker.join(timeout=2.0)

    assert snap.x == 321.0
    assert snap.y == 210.0
    assert snap.fixation == 0.88
    assert drain_latest(state.gesture_frame_queue) is not None
