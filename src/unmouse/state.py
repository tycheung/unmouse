from __future__ import annotations

import threading
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from typing import TypeVar

from unmouse.config import Settings
from unmouse.gestures.fsm import ClickEvent
from unmouse.gestures.scroll_fsm import ScrollTick

_T = TypeVar("_T")


@dataclass(frozen=True)
class GazeSnapshot:
    x: float
    y: float
    confidence: float


@dataclass
class SystemState:
    gaze_x: float
    gaze_y: float
    gaze_confidence: float = 1.0
    click_mode: bool = False
    right_click_intent: bool = False
    scroll_active: bool = False
    scroll_up: bool = True
    head_pose_ok: bool = True
    running: bool = True
    gaze_frame_queue: Queue[tuple[int, object]] | None = None
    gesture_frame_queue: Queue[tuple[int, object]] | None = None
    click_event_queue: Queue[ClickEvent] | None = None
    scroll_tick_queue: Queue[ScrollTick] | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def get_gaze(self) -> GazeSnapshot:
        with self._lock:
            return GazeSnapshot(self.gaze_x, self.gaze_y, self.gaze_confidence)

    def set_gaze(self, x: float, y: float, confidence: float) -> None:
        with self._lock:
            self.gaze_x = x
            self.gaze_y = y
            self.gaze_confidence = confidence

    def set_click_mode(self, active: bool, right_click: bool = False) -> None:
        with self._lock:
            self.click_mode = active
            if active:
                self.right_click_intent = right_click

    def set_scroll_active(self, active: bool, *, scroll_up: bool = True) -> None:
        with self._lock:
            self.scroll_active = active
            if active:
                self.scroll_up = scroll_up

    def enqueue_click_event(self, event: ClickEvent) -> None:
        with self._lock:
            _offer(self.click_event_queue, event)

    def enqueue_scroll_tick(self, tick: ScrollTick) -> None:
        with self._lock:
            _offer(self.scroll_tick_queue, tick)
            self.scroll_up = tick.delta > 0

    def set_head_pose_ok(self, ok: bool) -> None:
        with self._lock:
            self.head_pose_ok = ok

    def stop(self) -> None:
        with self._lock:
            self.running = False

    def is_running(self) -> bool:
        with self._lock:
            return self.running


def create_system_state(settings: Settings) -> SystemState:
    queue_size = settings.broker_queue_size
    return SystemState(
        gaze_x=settings.screen_width / 2,
        gaze_y=settings.screen_height / 2,
        gaze_frame_queue=Queue(maxsize=queue_size),
        gesture_frame_queue=Queue(maxsize=queue_size),
        click_event_queue=Queue(maxsize=queue_size),
        scroll_tick_queue=Queue(maxsize=queue_size),
    )


def _offer(queue: Queue[_T] | None, item: _T) -> None:
    if queue is None:
        return
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        try:
            queue.put_nowait(item)
        except Full:
            pass
