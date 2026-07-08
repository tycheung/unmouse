"""JavaScript ↔ Python bridge for the control panel."""

from __future__ import annotations

from collections.abc import Callable

from unmouse.config import Settings
from unmouse.launcher.api_helpers import action, last_calibration_label, update_payload
from unmouse.launcher.engine_runner import EngineRunner, EngineWatchdog, WatchdogEvent
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.services.engine_service import EngineService
from unmouse.launcher.services.enrollment_service import EnrollmentService
from unmouse.launcher.services.panel_state import PanelState, PanelStatus, PanelView
from unmouse.launcher.settings import (
    get_panel_settings,
    panel_activate_profile,
    panel_create_profile,
    panel_delete_profile,
    panel_rename_profile,
    panel_save_settings,
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
        self._enrollment_service = EnrollmentService(self._state, self._onboarding)
        if self._onboarding.should_show_on_startup():
            self._state.view = "onboarding"

    @property
    def view(self) -> PanelView:
        return self._state.view

    @property
    def _settings(self) -> Settings:
        return self._state.settings

    @property
    def _onboarding_ref(self) -> OnboardingController:
        return self._onboarding

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
            self._state.status = PanelStatus(message="Setup complete")
        return result

    def onboarding_skip(self, confirmed: bool = False) -> dict[str, object]:
        return self._onboarding.skip_current_step(confirmed=confirmed)

    def onboarding_check_camera(self) -> dict[str, object]:
        result = self._onboarding.check_camera()
        if result.get("ok"):
            self._state.status = PanelStatus(message=str(result.get("message", "Camera OK")))
        return result

    def onboarding_run_polynomial(self) -> dict[str, object]:
        result = self._onboarding.run_polynomial_step()
        if result.get("ok"):
            self._state.status = PanelStatus(
                message=str(result.get("message", "Calibration saved")),
            )
        return result

    def onboarding_run_offset(self) -> dict[str, object]:
        return self._onboarding.run_offset_step()

    def onboarding_run_gestures(self) -> dict[str, object]:
        return self._enrollment_service.open_gestures_from_onboarding()

    def onboarding_complete(self) -> dict[str, object]:
        result = self._onboarding.complete()
        self._state.view = "main"
        self._state.status = PanelStatus(message="Ready")
        return result

    def check_for_updates(self) -> dict[str, object]:
        self._state.update_status = check_updates()
        self._state.status = PanelStatus(
            message=self._state.update_status.message,
            fps=self._state.status.fps,
            confidence=self._state.status.confidence,
            tracking=self._state.status.tracking,
            paused=self._state.status.paused,
            gaze_mode=self._state.status.gaze_mode,
            last_calibrated=self._state.status.last_calibrated,
        )
        return update_payload(self._state.update_status)

    def apply_update(self) -> dict[str, object]:
        if self._state.update_status is None or not self._state.update_status.available:
            return action(False, "No update is available.")
        self._state.update_status = apply_update(self._state.update_status)
        self._state.status = PanelStatus(message=self._state.update_status.message)
        payload = action(not self._state.update_status.available, self._state.update_status.message)
        payload["update"] = update_payload(self._state.update_status)
        return payload

    def start_calibrate(self) -> dict[str, object]:
        from unmouse.gaze.calibration import calibration_path, load_calibration
        from unmouse.launcher.calibration_wizards import run_offset_wizard, run_polynomial_wizard

        if load_calibration(calibration_path(self._state.settings)) is None:
            poly = run_polynomial_wizard(self._state.settings)
            if not poly.success:
                return action(False, poly.message)
        outcome = run_offset_wizard(self._state.settings)
        self._state.status = PanelStatus(message=outcome.message)
        return action(outcome.success, outcome.message)

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
        self._enrollment_service.close()

    def show_settings(self) -> dict[str, str]:
        self._enrollment_service.close()
        self._state.view = "settings"
        return {"view": self._state.view}

    def get_settings_panel(self) -> dict[str, object]:
        return get_panel_settings(self._state.settings)

    def save_settings_panel(self, updates: dict[str, object]) -> dict[str, object]:
        result = panel_save_settings(self._state.settings, updates)
        self._state.settings = load_persisted_settings()
        self._state.status = PanelStatus(message="Settings saved")
        return result

    def create_profile(self, name: str) -> dict[str, object]:
        return panel_create_profile(self._state.settings, name)

    def rename_profile(self, old_name: str, new_name: str) -> dict[str, object]:
        result = panel_rename_profile(self._state.settings, old_name, new_name)
        if result.get("ok"):
            self._state.settings = load_persisted_settings()
        return result

    def delete_profile(self, name: str) -> dict[str, object]:
        return panel_delete_profile(self._state.settings, name)

    def activate_profile(self, name: str) -> dict[str, object]:
        result = panel_activate_profile(self._state.settings, name)
        if result.get("ok"):
            self._state.settings = load_persisted_settings()
        return result

    def show_onboarding(self) -> dict[str, str]:
        self._enrollment_service.close()
        self._state.view = "onboarding"
        return {"view": self._state.view}

    def show_enrollment(self, return_view: PanelView = "main") -> dict[str, object]:
        return self._enrollment_service.show(return_view=return_view)

    def get_enrollment_state(self) -> dict[str, object]:
        return self._enrollment_service.get_state()

    def get_enrollment_preview(self) -> dict[str, object]:
        return self._enrollment_service.get_preview()

    def enrollment_capture(self) -> dict[str, object]:
        return self._enrollment_service.capture()

    def leave_enrollment(self) -> dict[str, str]:
        return self._enrollment_service.leave()

    def show_main(self) -> dict[str, str]:
        self._enrollment_service.close()
        self._state.view = "main"
        return {"view": self._state.view}

    def set_status_message(self, message: str) -> dict[str, object]:
        return self._engine.set_status_message(message)

    def _handle_engine_crash(self, event: WatchdogEvent) -> None:
        self._engine._handle_engine_crash(event)
