"""Enrollment session handling for the control panel."""

from __future__ import annotations

from unmouse.launcher.api_helpers import action
from unmouse.launcher.enroll_ui import GestureEnrollmentSession, profile_has_gesture_templates
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.services.panel_state import PanelState, PanelStatus, PanelView


class EnrollmentService:
    def __init__(self, state: PanelState, onboarding: OnboardingController) -> None:
        self._state = state
        self._onboarding = onboarding

    def open_gestures_from_onboarding(self) -> dict[str, object]:
        if profile_has_gesture_templates(self._state.settings):
            self._onboarding.gestures_complete = True
            return {
                **action(True, "Gesture templates already saved."),
                "state": self._onboarding.get_state(),
            }
        opened = self.show(return_view="onboarding")
        if not opened.get("ok", True):
            return {**opened, "state": self._onboarding.get_state()}
        return {
            "ok": True,
            "message": "Hold each pose for 1 second while capturing.",
            "view": opened["view"],
            "enrollment": opened.get("enrollment"),
            "state": self._onboarding.get_state(),
        }

    def show(self, return_view: PanelView = "main") -> dict[str, object]:
        self.close()
        session = GestureEnrollmentSession(self._state.settings)
        try:
            session.open()
        except RuntimeError as exc:
            return action(False, str(exc))
        self._state.enrollment = session
        self._state.enrollment_return_view = return_view
        self._state.view = "enrollment"
        return {
            "ok": True,
            "view": self._state.view,
            "enrollment": session.get_state(),
        }

    def get_state(self) -> dict[str, object]:
        if self._state.enrollment is None:
            return {"active": False, "done": False, "message": "Enrollment is not active."}
        return self._state.enrollment.get_state()

    def get_preview(self) -> dict[str, object]:
        if self._state.enrollment is None:
            return {
                "preview_jpeg": None,
                "hand_detected": False,
                "message": "Enrollment is not active.",
            }
        preview = self._state.enrollment.grab_preview()
        return {
            "preview_jpeg": preview.preview_jpeg,
            "hand_detected": preview.hand_detected,
            "message": preview.message,
        }

    def capture(self) -> dict[str, object]:
        if self._state.enrollment is None:
            return action(False, "Enrollment is not active.")
        capture = self._state.enrollment.capture_current_gesture()
        if capture.ok and capture.done:
            self._onboarding.gestures_complete = True
        self._state.status = PanelStatus(message=capture.message)
        payload = capture.to_dict()
        payload["enrollment"] = self._state.enrollment.get_state()
        return payload

    def leave(self) -> dict[str, str]:
        return_view = self._state.enrollment_return_view
        self.close()
        self._state.view = return_view
        return {"view": self._state.view}

    def close(self) -> None:
        if self._state.enrollment is not None:
            self._state.enrollment.close()
            self._state.enrollment = None
