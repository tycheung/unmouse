from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from unmouse.config import Settings
from unmouse.state import SystemState
from unmouse.utils.coerce import as_float, as_int
from unmouse.utils.json_io import read_json_object_or_none, write_json_object

DIAGNOSTICS_FILENAME = "diagnostics.json"
LOGGER = logging.getLogger("unmouse.diagnostics")


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    broker_fps: float
    gaze_confidence: float
    gaze_queue_depth: int
    gesture_queue_depth: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def diagnostics_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / DIAGNOSTICS_FILENAME


def load_diagnostics_snapshot(settings: Settings) -> DiagnosticsSnapshot | None:
    data = read_json_object_or_none(
        diagnostics_file_path(settings),
        error_message="diagnostics JSON must be an object",
    )
    if data is None:
        return None
    return DiagnosticsSnapshot(
        broker_fps=as_float(data.get("broker_fps", 0.0)),
        gaze_confidence=as_float(data.get("gaze_confidence", 0.0)),
        gaze_queue_depth=as_int(data.get("gaze_queue_depth", 0)),
        gesture_queue_depth=as_int(data.get("gesture_queue_depth", 0)),
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
    write_json_object(path, snapshot.to_dict())
    return path


class DiagnosticsService:
    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        *,
        sleep: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        self._state = state
        self._settings = settings
        self._sleep = sleep
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
        self._thread = threading.Thread(target=self._run, name="diagnostics", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

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
            self._logger.debug(format_snapshot(snapshot).replace("\n", " | "))


def format_snapshot(snapshot: DiagnosticsSnapshot) -> str:
    return (
        f"FPS {snapshot.broker_fps:.1f}\n"
        f"Conf {snapshot.gaze_confidence:.2f}\n"
        f"Q gaze {snapshot.gaze_queue_depth} gesture {snapshot.gesture_queue_depth}"
    )


def _queue_depth(queue: object | None) -> int:
    if queue is None:
        return 0
    qsize = getattr(queue, "qsize", None)
    if callable(qsize):
        return int(qsize())
    return 0
