"""Video capture broker fan-out to per-consumer frame queues."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Full, Queue
from typing import Protocol

import numpy as np
import numpy.typing as npt

from unmouse.config import Settings
from unmouse.state import SystemState


@dataclass(frozen=True)
class FramePacket:
    frame_id: int
    frame: npt.NDArray[np.uint8]


class FrameSource(Protocol):
    def read(self) -> tuple[bool, npt.NDArray[np.uint8] | None]: ...

    def release(self) -> None: ...


class VideoBroker:
    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        source: FrameSource | None = None,
        *,
        on_frame: Callable[[], None] | None = None,
    ) -> None:
        self._state = state
        self._settings = settings
        self._source = source
        self._on_frame = on_frame
        self._thread: threading.Thread | None = None
        self._frame_id = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="video-broker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        source = self._source or _OpenCVFrameSource(self._settings)
        try:
            while self._state.is_running():
                ok, frame = source.read()
                if not ok or frame is None:
                    time.sleep(0.01)
                    continue
                self._frame_id += 1
                packet = FramePacket(self._frame_id, frame.copy())
                self._publish(packet)
                if self._on_frame is not None:
                    self._on_frame()
        finally:
            source.release()

    def _publish(self, packet: FramePacket) -> None:
        for queue in (self._state.gaze_frame_queue, self._state.gesture_frame_queue):
            if queue is None:
                continue
            _offer_latest(queue, (packet.frame_id, packet.frame))


def _offer_latest(queue: Queue[tuple[int, object]], item: tuple[int, object]) -> None:
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


def drain_latest(
    queue: Queue[tuple[int, object]] | None,
) -> tuple[int, npt.NDArray[np.uint8]] | None:
    if queue is None:
        return None
    latest: tuple[int, object] | None = None
    while True:
        try:
            latest = queue.get_nowait()
        except Empty:
            break
    if latest is None:
        return None
    frame_id, frame = latest
    return frame_id, np.asarray(frame, dtype=np.uint8)


def create_frame_source(settings: Settings) -> FrameSource:
    return _OpenCVFrameSource(settings)


class _OpenCVFrameSource:
    def __init__(self, settings: Settings) -> None:
        import cv2

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(settings.camera_index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.camera_width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.camera_height)

    def read(self) -> tuple[bool, npt.NDArray[np.uint8] | None]:
        ok, frame = self._cap.read()
        if not ok:
            return False, None
        return True, np.asarray(frame, dtype=np.uint8)

    def release(self) -> None:
        self._cap.release()


class MockFrameSource:
    def __init__(self, frames: list[npt.NDArray[np.uint8]]) -> None:
        self._frames = frames
        self._index = 0
        self.released = False

    def read(self) -> tuple[bool, npt.NDArray[np.uint8] | None]:
        if self._index >= len(self._frames):
            return False, None
        frame = self._frames[self._index]
        self._index += 1
        return True, frame

    def release(self) -> None:
        self.released = True
