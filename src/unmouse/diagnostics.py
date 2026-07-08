from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from unmouse.config import Settings
from unmouse.state import SystemState

DIAGNOSTICS_FILENAME = "diagnostics.json"
LOGGER = logging.getLogger("unmouse.diagnostics")


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    broker_fps: float
    gaze_confidence: float
    gaze_queue_depth: int
    gesture_queue_depth: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "broker_fps": self.broker_fps,
            "gaze_confidence": self.gaze_confidence,
            "gaze_queue_depth": self.gaze_queue_depth,
            "gesture_queue_depth": self.gesture_queue_depth,
        }


def diagnostics_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / DIAGNOSTICS_FILENAME


def load_diagnostics_snapshot(settings: Settings) -> DiagnosticsSnapshot | None:
    path = diagnostics_file_path(settings)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return DiagnosticsSnapshot(
        broker_fps=float(data.get("broker_fps", 0.0)),
        gaze_confidence=float(data.get("gaze_confidence", 0.0)),
        gaze_queue_depth=int(data.get("gaze_queue_depth", 0)),
        gesture_queue_depth=int(data.get("gesture_queue_depth", 0)),
    )


def collect_snapshot(state: SystemState, *, broker_fps: float) -> DiagnosticsSnapshot:
    gaze = state.get_gaze()
    return DiagnosticsSnapshot(
        broker_fps=broker_fps,
        gaze_confidence=gaze.confidence,
        gaze_queue_depth=_queue_depth(state.gaze_frame_queue),
        gesture_queue_depth=_queue_depth(state.gesture_frame_queue),
    )


def save_diagnostics_snapshot(settings: Settings, snapshot: DiagnosticsSnapshot) -> Path:
    path = diagnostics_file_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
    return path


class DiagnosticsService:
    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        *,
        sleep: Callable[[float], None] = time.sleep,
        overlay: DiagnosticsOverlayBackend | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._state = state
        self._settings = settings
        self._sleep = sleep
        self._overlay = overlay
        self._logger = logger or LOGGER
        self._broker_frames = 0
        self._thread: threading.Thread | None = None
        self._running = False

    def record_broker_frame(self) -> None:
        self._broker_frames += 1

    def start(self) -> None:
        if not self._settings.debug or (self._thread and self._thread.is_alive()):
            return
        self._running = True
        if self._overlay is not None:
            self._overlay.show()
        self._thread = threading.Thread(target=self._run, name="diagnostics", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._overlay is not None:
            self._overlay.hide()

    def _run(self) -> None:
        window_start = time.perf_counter()
        while self._running and self._state.is_running():
            self._sleep(1.0)
            now = time.perf_counter()
            elapsed = now - window_start
            frames = self._broker_frames
            self._broker_frames = 0
            window_start = now
            broker_fps = frames / max(elapsed, 1e-6)
            snapshot = collect_snapshot(self._state, broker_fps=broker_fps)
            save_diagnostics_snapshot(self._settings, snapshot)
            text = format_snapshot(snapshot)
            self._logger.debug(text.replace("\n", " | "))
            if self._overlay is not None:
                self._overlay.render(text)


def format_snapshot(snapshot: DiagnosticsSnapshot) -> str:
    return (
        f"FPS {snapshot.broker_fps:.1f}\n"
        f"Conf {snapshot.gaze_confidence:.2f}\n"
        f"Q gaze {snapshot.gaze_queue_depth} gesture {snapshot.gesture_queue_depth}"
    )


class DiagnosticsOverlayBackend:
    def show(self) -> None: ...

    def hide(self) -> None: ...

    def render(self, text: str) -> None: ...


@dataclass
class NoopDiagnosticsOverlay:
    lines: list[str] | None = None
    visible: bool = False

    def show(self) -> None:
        self.visible = True
        self.lines = []

    def hide(self) -> None:
        self.visible = False

    def render(self, text: str) -> None:
        if self.lines is not None:
            self.lines.append(text)


def _queue_depth(queue: object | None) -> int:
    if queue is None:
        return 0
    qsize = getattr(queue, "qsize", None)
    if callable(qsize):
        return int(qsize())
    return 0
