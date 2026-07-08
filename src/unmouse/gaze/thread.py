from __future__ import annotations

import threading
import time

from unmouse.broker.video_broker import drain_latest
from unmouse.config import Settings
from unmouse.gaze.display import VirtualDesktop
from unmouse.gaze.tracker import GazeTracker, create_gaze_tracker, load_gaze_model
from unmouse.state import SystemState


class GazeWorker:
    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        tracker: GazeTracker | None = None,
        desktop: VirtualDesktop | None = None,
    ) -> None:
        self._state = state
        self._settings = settings
        self._tracker = tracker or create_gaze_tracker(
            settings, model=load_gaze_model(settings)
        )
        self._desktop = desktop or VirtualDesktop.from_settings(settings)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="gaze-worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while self._state.is_running():
            latest = drain_latest(self._state.gaze_frame_queue)
            if latest is None:
                time.sleep(0.005)
                continue
            _frame_id, frame = latest
            sample, _target = self._tracker.step(frame, calibrate=False)
            if sample is not None:
                x, y = self._desktop.clip(sample.x, sample.y)
                self._state.set_gaze(x, y, sample.fixation)
            time.sleep(0.001)
