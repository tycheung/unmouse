from __future__ import annotations

import threading
import time

import numpy as np
import numpy.typing as npt

from unmouse.broker.video_broker import drain_latest
from unmouse.config import Settings
from unmouse.gestures.angles import compute_joint_angle_vector, landmarks_to_array
from unmouse.gestures.enrollment import default_gestures_dir, profile_gestures_dir
from unmouse.gestures.fsm import ClickFrameInput, ClickFsm
from unmouse.gestures.landmarks import HandLandmarkDetector, HandLandmarks, create_hand_detector
from unmouse.gestures.mle import GestureLibrary, classify, load_gesture_library
from unmouse.gestures.orientation import detect_right_click_orientation
from unmouse.gestures.scroll_fsm import ScrollFrameInput, ScrollFsm
from unmouse.gestures.scroll_zones import thumb_elevation_angle
from unmouse.state import SystemState

GESTURE_ACTIVE_HZ = 25.0
GESTURE_IDLE_HZ = 5.0
IDLE_FRAMES_BEFORE_SLOWDOWN = 10
THUMB_TIP = 4
INDEX_TIP = 8


class GestureWorker:
    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        detector: HandLandmarkDetector | None = None,
        library: GestureLibrary | None = None,
        click_fsm: ClickFsm | None = None,
        scroll_fsm: ScrollFsm | None = None,
        *,
        idle_frames_before_slowdown: int = IDLE_FRAMES_BEFORE_SLOWDOWN,
    ) -> None:
        self._state = state
        self._settings = settings
        self._detector = detector or create_hand_detector(prefer_mediapipe=False)
        self._library = library if library is not None else load_runtime_gesture_library(settings)
        self._click_fsm = click_fsm or ClickFsm.from_settings(settings)
        self._scroll_fsm = scroll_fsm or ScrollFsm.from_settings(settings)
        self._idle_threshold = idle_frames_before_slowdown
        self._missed_hand_frames = 0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="gesture-worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def process_frame(
        self,
        frame: npt.NDArray[np.uint8],
        *,
        timestamp_s: float | None = None,
    ) -> None:
        now = timestamp_s if timestamp_s is not None else time.perf_counter()
        self._process_detection(self._detector.detect(frame), timestamp_s=now)

    @property
    def missed_hand_frames(self) -> int:
        return self._missed_hand_frames

    def _run(self) -> None:
        try:
            while self._state.is_running():
                started = time.perf_counter()
                latest = drain_latest(self._state.gesture_frame_queue)
                if latest is None:
                    time.sleep(0.005)
                    continue
                _frame_id, frame = latest
                self.process_frame(np.asarray(frame))
                elapsed = time.perf_counter() - started
                target_hz = (
                    GESTURE_IDLE_HZ
                    if self._missed_hand_frames >= self._idle_threshold
                    else GESTURE_ACTIVE_HZ
                )
                sleep_for = (1.0 / target_hz) - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            close = getattr(self._detector, "close", None)
            if callable(close):
                close()

    def _process_detection(self, detection: object, *, timestamp_s: float) -> None:
        from unmouse.gestures.landmarks import LandmarkDetectionResult

        if not isinstance(detection, LandmarkDetectionResult):
            msg = "detector must return LandmarkDetectionResult"
            raise TypeError(msg)

        gaze = self._state.get_gaze()
        if not detection.hands:
            self._missed_hand_frames += 1
            self._apply_fsms(
                timestamp_s=timestamp_s,
                gaze_x=gaze.x,
                gaze_y=gaze.y,
                v_sign_active=False,
                pinch_close=False,
                right_click=False,
                thumbs_up_active=False,
                thumb_angle_deg=0.0,
            )
            return

        self._missed_hand_frames = 0
        hand = detection.hands[0]
        theta = compute_joint_angle_vector(hand)
        result = classify(
            theta,
            self._library,
            absolute_min=self._settings.mle_absolute_min,
            margin_min=self._settings.mle_margin_min,
        )
        gesture = result.gesture
        pinch_close = (
            _is_pinch_close(hand, self._settings.pinch_threshold) or gesture == "pinch_close"
        )
        self._apply_fsms(
            timestamp_s=timestamp_s,
            gaze_x=gaze.x,
            gaze_y=gaze.y,
            v_sign_active=gesture == "v_sign",
            pinch_close=pinch_close,
            right_click=detect_right_click_orientation(hand),
            thumbs_up_active=gesture == "thumbs_up",
            thumb_angle_deg=thumb_elevation_angle(hand),
        )

    def _apply_fsms(
        self,
        *,
        timestamp_s: float,
        gaze_x: float,
        gaze_y: float,
        v_sign_active: bool,
        pinch_close: bool,
        right_click: bool,
        thumbs_up_active: bool,
        thumb_angle_deg: float,
    ) -> None:
        click_out = self._click_fsm.process(
            ClickFrameInput(
                timestamp_s=timestamp_s,
                v_sign_active=v_sign_active,
                pinch_close=pinch_close,
                right_click=right_click,
                gaze_x=gaze_x,
                gaze_y=gaze_y,
            ),
        )
        scroll_out = self._scroll_fsm.process(
            ScrollFrameInput(
                timestamp_s=timestamp_s,
                thumbs_up_active=thumbs_up_active,
                thumb_angle_deg=thumb_angle_deg,
                gaze_x=gaze_x,
                gaze_y=gaze_y,
            ),
        )
        self._state.set_click_mode(click_out.click_mode, right_click=click_out.right_click_intent)
        self._state.set_scroll_active(scroll_out.scroll_active)
        if click_out.click_event is not None:
            self._state.enqueue_click_event(click_out.click_event)
        if scroll_out.scroll_tick is not None:
            self._state.enqueue_scroll_tick(scroll_out.scroll_tick)


def load_runtime_gesture_library(settings: Settings) -> GestureLibrary:
    library = load_gesture_library(default_gestures_dir())
    library.update(load_gesture_library(profile_gestures_dir(settings.profile_dir)))
    return library


def _is_pinch_close(hand: HandLandmarks, threshold: float) -> bool:
    points = landmarks_to_array(hand)
    thumb = points[THUMB_TIP, :2]
    index = points[INDEX_TIP, :2]
    return float(np.linalg.norm(thumb - index)) <= threshold
