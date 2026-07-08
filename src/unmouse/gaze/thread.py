from __future__ import annotations

import threading
import time

from unmouse.broker.video_broker import drain_latest
from unmouse.config import Settings
from unmouse.gaze.calibration import load_calibration
from unmouse.gaze.display import DisplayMapper, probe_virtual_desktop
from unmouse.gaze.offset_profile import load_offset_profile_for_settings
from unmouse.gaze.pipeline import GazePipeline
from unmouse.gaze.tracker import GazeTracker, create_gaze_tracker
from unmouse.state import SystemState


class GazeWorker:
    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        tracker: GazeTracker | None = None,
        pipeline: GazePipeline | None = None,
    ) -> None:
        self._state = state
        self._settings = settings
        self._tracker = tracker or create_gaze_tracker(prefer_eyegestures=False)
        if pipeline is None:
            calibration = load_calibration(settings.profile_dir / "calibration.json")
            desktop = probe_virtual_desktop(settings)
            pipeline = GazePipeline(
                settings,
                calibration=calibration,
                display=DisplayMapper(desktop),
                offset_profile=load_offset_profile_for_settings(settings),
            )
        self._pipeline = pipeline
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
            result = self._tracker.predict(frame)
            output = self._pipeline.process(result)
            self._state.set_gaze(output.x, output.y, output.confidence)
            self._state.set_head_pose_ok(output.head_pose_ok)
            time.sleep(0.001)
