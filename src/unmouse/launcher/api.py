from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace

from unmouse.config import Settings
from unmouse.launcher.api_helpers import action, last_calibration_label, update_payload
from unmouse.launcher.engine_runner import EngineRunner, EngineWatchdog
from unmouse.launcher.enroll_ui import GestureEnrollmentSession, profile_has_gesture_templates
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.services.engine_service import (
    EngineService,
    PanelState,
    PanelStatus,
    PanelView,
)
from unmouse.launcher.settings import (
    activate_profile,
    create_profile,
    delete_profile,
    get_panel_settings,
    rename_profile,
    update_panel_settings,
)
from unmouse.launcher.tray import TrayBackend
from unmouse.launcher.update import apply_update, check_updates
from unmouse.persistence import load_persisted_settings

__all__ = ["PanelApi", "PanelStatus", "PanelView", "last_calibration_label"]


class PanelApi:
    def __init__(
        self,
        settings: Settings | None = None,
        onboarding: OnboardingController | None = None,
        *,
        engine_runner: EngineRunner | None = None,
        tray: TrayBackend | None = None,
        watchdog: EngineWatchdog | None = None,
    ) -> None:
        resolved_settings = settings or load_persisted_settings()
        self._state = PanelState(settings=resolved_settings)
        self._onboarding = onboarding or OnboardingController.create(resolved_settings)
        self._engine = EngineService(
            self._state,
            engine_runner or EngineRunner(),
            tray=tray,
            watchdog=watchdog,
        )
        if self._onboarding.should_show_on_startup():
            self._state.view = "onboarding"

    @property
    def view(self) -> PanelView:
        return self._state.view

    @property
    def _settings(self) -> Settings:
        return self._state.settings

    def _set_status_message(self, message: str) -> None:
        self._engine.note_status(message)

    def _forward_with_status(
        self,
        result: dict[str, object],
        default_message: str,
    ) -> dict[str, object]:
        if result.get("ok"):
            self._set_status_message(str(result.get("message", default_message)))
        return result

    def _show_view(self, view: PanelView) -> dict[str, str]:
        self._close_enrollment()
        self._state.view = view
        return {"view": self._state.view}

    def get_status(self) -> dict[str, object]:
        return self._engine.get_status()

    def toggle_pause(self) -> dict[str, object]:
        return self._engine.toggle_pause()

    def toggle_gaze_mode(self) -> dict[str, object]:
        return self._engine.toggle_gaze_mode()

    def get_view(self) -> dict[str, str]:
        return {"view": self._state.view}

    def get_onboarding_state(self) -> dict[str, object]:
        return self._onboarding.get_state()

    def onboarding_advance(self) -> dict[str, object]:
        result = self._onboarding.advance()
        if result.get("ok") and self._onboarding.current_step.id == "ready":
            self._set_status_message("Setup complete")
        return result

    def onboarding_skip(self, confirmed: bool = False) -> dict[str, object]:
        return self._onboarding.skip_current_step(confirmed=confirmed)

    def onboarding_check_camera(self) -> dict[str, object]:
        return self._forward_with_status(self._onboarding.check_camera(), "Camera OK")

    def onboarding_run_calibration(self) -> dict[str, object]:
        return self._forward_with_status(
            self._onboarding.run_calibration_step(),
            "Calibration saved",
        )

    def onboarding_run_gestures(self) -> dict[str, object]:
        if profile_has_gesture_templates(self._state.settings):
            self._onboarding.gestures_complete = True
            return self._with_onboarding_state(action(True, "Gesture templates already saved."))
        opened = self._open_enrollment(return_view="onboarding")
        if not opened.get("ok", True):
            return self._with_onboarding_state(opened)
        return self._with_onboarding_state(
            {
                "ok": True,
                "message": "Hold each pose for 1 second while capturing.",
                "view": opened["view"],
                "enrollment": opened.get("enrollment"),
            }
        )

    def _with_onboarding_state(self, payload: dict[str, object]) -> dict[str, object]:
        return {**payload, "state": self._onboarding.get_state()}

    def onboarding_complete(self) -> dict[str, object]:
        result = self._onboarding.complete()
        self._state.view = "main"
        self._set_status_message("Ready")
        return result

    def check_for_updates(self) -> dict[str, object]:
        self._state.update_status = check_updates()
        self._state.status = replace(
            self._state.status,
            message=self._state.update_status.message,
        )
        return update_payload(self._state.update_status)

    def apply_update(self) -> dict[str, object]:
        if self._state.update_status is None or not self._state.update_status.available:
            return action(False, "No update is available.")
        self._state.update_status = apply_update(self._state.update_status)
        self._set_status_message(self._state.update_status.message)
        return action(
            not self._state.update_status.available,
            self._state.update_status.message,
            update=update_payload(self._state.update_status),
        )

    def start_calibrate(self) -> dict[str, object]:
        from unmouse.launcher.calibration_wizards import run_calibration_wizard

        outcome = run_calibration_wizard(self._state.settings)
        self._set_status_message(outcome.message)
        return action(outcome.ok, outcome.message)

    def configure_launcher_shell(
        self,
        *,
        on_show_panel: Callable[[], None] | None = None,
        on_minimize_panel: Callable[[], None] | None = None,
        on_quit_app: Callable[[], None] | None = None,
    ) -> None:
        self._engine.configure_shell(
            on_show_panel=on_show_panel,
            on_minimize_panel=on_minimize_panel,
            on_quit_app=on_quit_app,
        )

    def start_launch(self) -> dict[str, object]:
        return self._engine.start_launch()

    def stop_engine(self) -> dict[str, object]:
        return self._engine.stop_engine()

    def shutdown(self) -> None:
        self._engine.shutdown()
        self._close_enrollment()

    def show_settings(self) -> dict[str, str]:
        return self._show_view("settings")

    def get_settings_panel(self) -> dict[str, object]:
        return get_panel_settings(self._state.settings)

    def save_settings_panel(self, updates: dict[str, object]) -> dict[str, object]:
        snapshot = update_panel_settings(self._state.settings, updates)
        self._state.settings = load_persisted_settings()
        restarted = self._engine.reload_if_running()
        message = "Settings saved. Restarting tracking." if restarted else "Settings saved."
        self._set_status_message(message)
        return {"ok": True, "message": message, "settings": snapshot, "restarted": restarted}

    def _profile_action(
        self,
        func: Callable[..., dict[str, object]],
        *args: str,
        reload_on_ok: bool = False,
    ) -> dict[str, object]:
        try:
            result = func(self._state.settings, *args)
        except ValueError as exc:
            return action(False, str(exc))
        if reload_on_ok and result.get("ok"):
            self._state.settings = load_persisted_settings()
        return result

    def create_profile(self, name: str) -> dict[str, object]:
        return self._profile_action(create_profile, name)

    def rename_profile(self, old_name: str, new_name: str) -> dict[str, object]:
        return self._profile_action(rename_profile, old_name, new_name, reload_on_ok=True)

    def delete_profile(self, name: str) -> dict[str, object]:
        return self._profile_action(delete_profile, name)

    def activate_profile(self, name: str) -> dict[str, object]:
        return self._profile_action(activate_profile, name, reload_on_ok=True)

    def show_enrollment(self, return_view: PanelView = "main") -> dict[str, object]:
        return self._open_enrollment(return_view=return_view)

    def get_enrollment_preview(self) -> dict[str, object]:
        if self._state.enrollment is None:
            return {
                "preview_jpeg": None,
                "hand_detected": False,
                "message": "Enrollment is not active.",
            }
        return asdict(self._state.enrollment.grab_preview())

    def enrollment_capture(self) -> dict[str, object]:
        if self._state.enrollment is None:
            return action(False, "Enrollment is not active.")
        capture = self._state.enrollment.capture_current_gesture()
        if capture.ok and capture.done:
            self._onboarding.gestures_complete = True
        self._set_status_message(capture.message)
        payload = capture.to_dict()
        payload["enrollment"] = self._state.enrollment.get_state()
        return payload

    def leave_enrollment(self) -> dict[str, str]:
        return_view = self._state.enrollment_return_view
        self._close_enrollment()
        self._state.view = return_view
        return {"view": self._state.view}

    def _open_enrollment(self, *, return_view: PanelView) -> dict[str, object]:
        self._close_enrollment()
        session = GestureEnrollmentSession(self._state.settings)
        try:
            session.open()
        except RuntimeError as exc:
            return action(False, str(exc))
        self._state.enrollment = session
        self._state.enrollment_return_view = return_view
        self._state.view = "enrollment"
        return {"ok": True, "view": self._state.view, "enrollment": session.get_state()}

    def _close_enrollment(self) -> None:
        if self._state.enrollment is not None:
            self._state.enrollment.close()
            self._state.enrollment = None

    def show_main(self) -> dict[str, str]:
        return self._show_view("main")
