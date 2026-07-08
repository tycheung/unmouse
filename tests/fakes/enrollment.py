from __future__ import annotations

from unmouse.config import Settings
from unmouse.launcher.calibration_wizards import ActionResult
from unmouse.launcher.enroll_ui import EnrollmentPreview


class FakeEnrollmentSession:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._index = 0
        self._done = False
        self._gestures = ("v_sign", "pinch_close", "thumbs_up")

    def open(self) -> None:
        return

    def close(self) -> None:
        return

    def get_state(self) -> dict[str, object]:
        gesture = self._gestures[self._index] if not self._done else None
        return {
            "active": True,
            "done": self._done,
            "gesture": gesture,
            "gesture_label": gesture or "",
            "gesture_index": self._index,
            "gesture_count": len(self._gestures),
            "instruction": "Hold the pose steady.",
            "message": "Mock enrollment session.",
        }

    def grab_preview(self) -> EnrollmentPreview:
        return EnrollmentPreview(
            preview_jpeg=None,
            hand_detected=True,
            message="Mock preview.",
        )

    def capture_current_gesture(self) -> ActionResult:
        if self._done:
            return ActionResult(True, "Enrollment complete.", done=True)
        gesture = self._gestures[self._index]
        self._index += 1
        done = self._index >= len(self._gestures)
        self._done = done
        return ActionResult(
            ok=True,
            message=f"Captured {gesture}.",
            gesture=gesture,
            sample_count=30,
            done=done,
        )
