"""Thread-safe shared runtime state for broker, gaze, and gesture threads."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from queue import Queue

from unmouse.config import Settings


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
    head_pose_ok: bool = True
    running: bool = True
    gaze_frame_queue: Queue[tuple[int, object]] | None = None
    gesture_frame_queue: Queue[tuple[int, object]] | None = None
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

    def set_scroll_active(self, active: bool) -> None:
        with self._lock:
            self.scroll_active = active

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
    return SystemState(
        gaze_x=settings.screen_width / 2,
        gaze_y=settings.screen_height / 2,
        gaze_frame_queue=Queue(maxsize=settings.broker_queue_size),
        gesture_frame_queue=Queue(maxsize=settings.broker_queue_size),
    )
