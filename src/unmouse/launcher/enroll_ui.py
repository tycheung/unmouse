from __future__ import annotations

import base64
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

import cv2
import numpy as np
import numpy.typing as npt

from unmouse.broker.camera import open_camera
from unmouse.config import Settings
from unmouse.gestures.enrollment import (
    DEFAULT_CAPTURE_DURATION_S,
    DEFAULT_CAPTURE_FPS,
    DEFAULT_CAPTURE_WARMUP_S,
    DEFAULT_GESTURE_NAMES,
    collect_feature_samples,
    enroll_from_samples,
    profile_gestures_dir,
)
from unmouse.gestures.landmarks import (
    HandLandmarkDetector,
    create_hand_detector,
    draw_hand_skeleton,
)
from unmouse.launcher.calibration_wizards import ActionResult

GESTURE_LABELS: dict[str, str] = {
    "v_sign": "V-sign",
    "pinch_close": "Pinch close",
    "thumbs_up": "Thumbs up",
}

GESTURE_INSTRUCTIONS: dict[str, str] = {
    "v_sign": "Extend index and middle fingers in a V. Curl the others.",
    "pinch_close": "Touch your thumb tip to your index fingertip.",
    "thumbs_up": "Extend your thumb upward and curl the other fingers.",
}


@dataclass(frozen=True)
class EnrollmentPreview:
    preview_jpeg: str | None
    hand_detected: bool
    message: str = ""


@dataclass
class GestureEnrollmentState:
    active: bool
    done: bool
    gesture: str | None
    gesture_label: str
    gesture_index: int
    gesture_count: int
    completed: list[str] = field(default_factory=list)
    capturing: bool = False
    instruction: str = ""
    message: str = ""


def profile_has_gesture_templates(settings: Settings) -> bool:
    gestures_dir = profile_gestures_dir(settings.profile_dir)
    return gestures_dir.is_dir() and all(
        (gestures_dir / f"{name}.json").is_file() for name in DEFAULT_GESTURE_NAMES
    )


class GestureEnrollmentSession:
    def __init__(
        self,
        settings: Settings,
        *,
        detector: HandLandmarkDetector | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._detector = detector or create_hand_detector()
        self._clock = clock
        self._sleep = sleep
        self._capture: cv2.VideoCapture | None = None
        self._index = 0
        self._completed: list[str] = []
        self._capturing = False

    @property
    def done(self) -> bool:
        return self._index >= len(DEFAULT_GESTURE_NAMES)

    def open(self) -> None:
        if self._capture is not None:
            return
        capture = open_camera(self._settings.camera_index)
        self._capture = capture

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if hasattr(self._detector, "close"):
            self._detector.close()

    def get_state(self) -> dict[str, object]:
        return asdict(self._build_state())

    def grab_preview(self) -> EnrollmentPreview:
        if self._capture is None:
            return EnrollmentPreview(None, False, message="Camera is not open.")
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return EnrollmentPreview(None, False, message="Unable to read camera frame.")
        frame_u8 = np.asarray(frame, dtype=np.uint8)
        result = self._detector.detect(frame_u8)
        try:
            annotated = draw_hand_skeleton(frame_u8, result.hands)
        except (AttributeError, ImportError, RuntimeError):
            annotated = frame_u8
        jpeg = _frame_to_jpeg_b64(annotated)
        hand_detected = bool(result.hands)
        message = "Hand detected." if hand_detected else "Show your hand to the camera."
        return EnrollmentPreview(jpeg, hand_detected, message=message)

    def capture_current_gesture(self) -> ActionResult:
        if self.done:
            return ActionResult(True, "All gestures already enrolled.", done=True)
        gesture = DEFAULT_GESTURE_NAMES[self._index]
        if self._capture is None:
            return ActionResult(False, "Camera is not open.")
        self._capturing = True
        try:
            samples = collect_feature_samples(
                self._capture,
                self._detector,
                duration_s=DEFAULT_CAPTURE_DURATION_S,
                warmup_s=DEFAULT_CAPTURE_WARMUP_S,
                target_fps=DEFAULT_CAPTURE_FPS,
                clock=self._clock,
                sleep=self._sleep,
            )
        except RuntimeError as exc:
            return ActionResult(False, str(exc), gesture=gesture)
        finally:
            self._capturing = False

        output_dir = profile_gestures_dir(self._settings.profile_dir)
        path = enroll_from_samples(gesture, samples, output_dir)
        self._completed.append(gesture)
        self._index += 1
        finished = self.done
        label = GESTURE_LABELS[gesture]
        if finished:
            message = f"Saved {label}. All gesture templates enrolled."
        else:
            next_label = GESTURE_LABELS[DEFAULT_GESTURE_NAMES[self._index]]
            message = f"Saved {label} to {path.name}. Next: {next_label}."
        return ActionResult(
            ok=True,
            message=message,
            gesture=gesture,
            sample_count=int(samples.shape[0]),
            done=finished,
        )

    def _build_state(self) -> GestureEnrollmentState:
        if self.done:
            return GestureEnrollmentState(
                active=True,
                done=True,
                gesture=None,
                gesture_label="",
                gesture_index=len(DEFAULT_GESTURE_NAMES),
                gesture_count=len(DEFAULT_GESTURE_NAMES),
                completed=list(self._completed),
                capturing=self._capturing,
                instruction="",
                message="All required gestures are enrolled.",
            )
        gesture = DEFAULT_GESTURE_NAMES[self._index]
        return GestureEnrollmentState(
            active=True,
            done=False,
            gesture=gesture,
            gesture_label=GESTURE_LABELS[gesture],
            gesture_index=self._index,
            gesture_count=len(DEFAULT_GESTURE_NAMES),
            completed=list(self._completed),
            capturing=self._capturing,
            instruction=GESTURE_INSTRUCTIONS[gesture],
            message=f"Hold the {GESTURE_LABELS[gesture]} pose steady for 1 second, then capture.",
        )


def _frame_to_jpeg_b64(frame: npt.NDArray[np.uint8], *, quality: int = 72) -> str | None:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return None
    return base64.b64encode(buffer.tobytes()).decode("ascii")
