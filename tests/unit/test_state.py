import threading

from unmouse.config import Settings
from unmouse.gestures.fsm import ClickEvent
from unmouse.gestures.scroll_fsm import ScrollTick
from unmouse.state import SystemState, create_system_state


def test_create_system_state_centers_gaze() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    snap = state.get_gaze()
    assert snap.x == 400.0
    assert snap.y == 300.0
    assert snap.fixation == 0.0


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
    assert 0.0 <= snap.fixation <= 1.0


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


def test_click_queue_replaces_oldest_when_full() -> None:
    state = create_system_state(Settings(broker_queue_size=1))
    assert state.click_event_queue is not None
    state.enqueue_click_event(ClickEvent(button="left", x=1.0, y=2.0))
    state.enqueue_click_event(ClickEvent(button="right", x=3.0, y=4.0))
    event = state.click_event_queue.get_nowait()
    assert event.button == "right"


def test_enqueue_click_event_ignores_missing_queue() -> None:
    state = SystemState(gaze_x=0.0, gaze_y=0.0, click_event_queue=None)
    state.enqueue_click_event(ClickEvent(button="left", x=0.0, y=0.0))


def test_scroll_tick_updates_direction() -> None:
    state = create_system_state(Settings())
    state.enqueue_scroll_tick(ScrollTick(x=1.0, y=2.0, delta=-4.0))
    assert state.scroll_up is False
