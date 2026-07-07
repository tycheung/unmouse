"""Unit tests for thread-safe system state."""

import threading

from unmouse.config import Settings
from unmouse.state import create_system_state


def test_create_system_state_centers_gaze() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    snap = state.get_gaze()
    assert snap.x == 400.0
    assert snap.y == 300.0
    assert snap.confidence == 1.0


def test_concurrent_gaze_updates() -> None:
    settings = Settings()
    state = create_system_state(settings)
    errors: list[str] = []

    def writer(n: int) -> None:
        try:
            for i in range(100):
                state.set_gaze(float(n * 1000 + i), float(i), 0.5)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert not errors
    snap = state.get_gaze()
    assert 0.0 <= snap.x <= 4000.0
    assert 0.0 <= snap.confidence <= 1.0


def test_stop_sets_running_false() -> None:
    state = create_system_state(Settings())
    assert state.is_running() is True
    state.stop()
    assert state.is_running() is False


def test_frame_queues_created() -> None:
    state = create_system_state(Settings(broker_queue_size=3))
    assert state.gaze_frame_queue is not None
    assert state.gesture_frame_queue is not None
    assert state.gaze_frame_queue.maxsize == 3
    assert state.gesture_frame_queue is not state.gaze_frame_queue
