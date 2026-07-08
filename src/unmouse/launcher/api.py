"""JavaScript ↔ Python bridge for the control panel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from unmouse.config import GazeMode, Settings
from unmouse.diagnostics import load_diagnostics_snapshot
from unmouse.launcher.engine_runner import EngineRunner, EngineWatchdog, WatchdogEvent
from unmouse.launcher.enroll_ui import GestureEnrollmentSession, profile_has_gesture_templates
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.results import ActionResult
from unmouse.launcher.settings import (
    activate_profile,
    create_profile,
    delete_profile,
    get_panel_settings,
    load_persisted_settings,
    rename_profile,
    toggle_gaze_mode,
    update_panel_settings,
)
from unmouse.launcher.tray import TrayBackend, TrayHandlers, create_tray_backend
from unmouse.launcher.update import UpdateStatus, apply_update, check_updates
from unmouse.runtime import load_runtime, set_paused, toggle_paused

PanelView = Literal["main", "settings", "onboarding", "enrollment"]


@dataclass(frozen=True)
class PanelStatus:
    message: str
    fps: float | None = None
    confidence: float | None = None
    tracking: bool = False
    paused: bool = False
    gaze_mode: str = "cursor_follow"
    last_calibrated: str | None = None


def _update_payload(status: UpdateStatus) -> dict[str, object]:
    payload = status.to_dict()
    payload["version"] = status.latest_version
    return payload


def _action(ok: bool, message: str, **extra: object) -> dict[str, object]:
    payload = ActionResult(ok, message).to_dict()
    payload.update(extra)
    return payload


class PanelApi:
    """Methods exposed to Alpine.js through pywebview's js_api."""

    def __init__(
        self,
        settings: Settings | None = None,
        onboarding: OnboardingController | None = None,
        *,
        engine_runner: EngineRunner | None = None,
        tray: TrayBackend | None = None,
        watchdog: EngineWatchdog | None = None,
    ) -> None:
        self._settings = settings or load_persisted_settings()
        self._onboarding = onboarding or OnboardingController.create(self._settings)
        self._engine_runner = engine_runner or EngineRunner()
        self._tray = tray
        self._watchdog = watchdog
        self._on_show_panel: Callable[[], None] | None = None
        self._on_minimize_panel: Callable[[], None] | None = None
        self._on_quit_app: Callable[[], None] | None = None
        self._view: PanelView = "main"
        self._status = PanelStatus(message="Ready")
        self._update_status: UpdateStatus | None = None
        self._enrollment: GestureEnrollmentSession | None = None
        self._enrollment_return_view: PanelView = "main"
        if self._onboarding.should_show_on_startup():
            self._view = "onboarding"

    @property
    def view(self) -> PanelView:
        return self._view

    def get_status(self) -> dict[str, object]:
        self._settings = load_persisted_settings()
        runtime = load_runtime(self._settings)
        diagnostics = (
            load_diagnostics_snapshot(self._settings)
            if self._engine_runner.is_running()
            else None
        )
        return asdict(
            PanelStatus(
                message=self._status.message,
                fps=diagnostics.broker_fps if diagnostics else self._status.fps,
                confidence=diagnostics.gaze_confidence if diagnostics else self._status.confidence,
                tracking=self._engine_runner.is_running(),
                paused=runtime.paused if self._engine_runner.is_running() else False,
                gaze_mode=self._settings.gaze_mode.value,
                last_calibrated=last_calibration_label(self._settings),
            ),
        )

    def toggle_pause(self) -> dict[str, object]:
        if not self._engine_runner.is_running():
            return _action(False, "Start tracking before pausing.")
        runtime = toggle_paused(self._settings)
        self._refresh_tray_menu()
        message = "Tracking paused." if runtime.paused else "Tracking resumed."
        self._status = self._runtime_panel_status(message)
        payload = _action(True, message)
        payload["paused"] = runtime.paused
        return payload

    def toggle_gaze_mode(self) -> dict[str, object]:
        mode = toggle_gaze_mode(self._settings)
        self._settings = load_persisted_settings()
        self._refresh_tray_menu()
        label = (
            "Gaze-only mode enabled."
            if mode is GazeMode.GAZE_ONLY
            else "Cursor follow enabled."
        )
        self._status = self._runtime_panel_status(label)
        payload = _action(True, label)
        payload["gaze_mode"] = mode.value
        return payload

    def get_view(self) -> dict[str, str]:
        return {"view": self._view}

    def get_onboarding_state(self) -> dict[str, object]:
        return self._onboarding.get_state()

    def onboarding_advance(self) -> dict[str, object]:
        result = self._onboarding.advance()
        if result.get("ok") and self._onboarding.current_step.id == "ready":
            self._status = PanelStatus(message="Setup complete")
        return result

    def onboarding_skip(self, confirmed: bool = False) -> dict[str, object]:
        return self._onboarding.skip_current_step(confirmed=confirmed)

    def onboarding_check_camera(self) -> dict[str, object]:
        result = self._onboarding.check_camera()
        if result.get("ok"):
            self._status = PanelStatus(message=str(result.get("message", "Camera OK")))
        return result

    def onboarding_run_polynomial(self) -> dict[str, object]:
        result = self._onboarding.run_polynomial_step()
        if result.get("ok"):
            self._status = PanelStatus(message=str(result.get("message", "Calibration saved")))
        return result

    def onboarding_run_offset(self) -> dict[str, object]:
        return self._onboarding.run_offset_step()

    def onboarding_run_gestures(self) -> dict[str, object]:
        if profile_has_gesture_templates(self._settings):
            self._onboarding.gestures_complete = True
            return {
                **_action(True, "Gesture templates already saved."),
                "state": self._onboarding.get_state(),
            }
        opened = self.show_enrollment(return_view="onboarding")
        if not opened.get("ok", True):
            return {**opened, "state": self._onboarding.get_state()}
        return {
            "ok": True,
            "message": "Hold each pose for 1 second while capturing.",
            "view": opened["view"],
            "enrollment": opened.get("enrollment"),
            "state": self._onboarding.get_state(),
        }

    def onboarding_complete(self) -> dict[str, object]:
        result = self._onboarding.complete()
        self._view = "main"
        self._status = PanelStatus(message="Ready")
        return result

    def check_for_updates(self) -> dict[str, object]:
        self._update_status = check_updates()
        return _update_payload(self._update_status)

    def apply_update(self) -> dict[str, object]:
        if self._update_status is None or not self._update_status.available:
            return _action(False, "No update is available.")
        self._update_status = apply_update(self._update_status)
        self._status = PanelStatus(message=self._update_status.message)
        payload = _action(not self._update_status.available, self._update_status.message)
        payload["update"] = _update_payload(self._update_status)
        return payload

    def start_calibrate(self) -> dict[str, object]:
        from unmouse.gaze.calibration import calibration_path, load_calibration
        from unmouse.launcher.calibrate_wizard import run_offset_wizard
        from unmouse.launcher.polynomial_wizard import run_polynomial_wizard

        if load_calibration(calibration_path(self._settings)) is None:
            poly = run_polynomial_wizard(self._settings)
            if not poly.success:
                return _action(False, poly.message)
        outcome = run_offset_wizard(self._settings)
        self._status = PanelStatus(message=outcome.message)
        return _action(outcome.success, outcome.message)

    def configure_launcher_shell(
        self,
        *,
        on_show_panel: Callable[[], None] | None = None,
        on_minimize_panel: Callable[[], None] | None = None,
        on_quit_app: Callable[[], None] | None = None,
    ) -> None:
        self._on_show_panel = on_show_panel
        self._on_minimize_panel = on_minimize_panel
        self._on_quit_app = on_quit_app
        if self._tray is None:
            self._tray = create_tray_backend(self._tray_handlers(), prefer_pystray=True)

    def start_launch(self) -> dict[str, object]:
        if self._engine_runner.is_running():
            self._ensure_tray()
            payload = _action(True, "Engine already running.")
            payload["tracking"] = True
            return payload
        status = self._engine_runner.start()
        if not status.ok or not status.running:
            return _action(False, status.message)
        set_paused(self._settings, False)
        self._ensure_tray()
        self._start_watchdog()
        if self._on_minimize_panel is not None:
            self._on_minimize_panel()
        self._status = self._runtime_panel_status(status.message)
        payload = _action(True, status.message)
        payload["tracking"] = True
        payload["minimize"] = True
        payload["pid"] = status.pid
        return payload

    def stop_engine(self) -> dict[str, object]:
        self._stop_watchdog()
        status = self._engine_runner.stop()
        self._status = self._runtime_panel_status(status.message)
        return _action(status.ok, status.message)

    def shutdown(self) -> None:
        self._stop_watchdog()
        self._engine_runner.stop()
        if self._tray is not None:
            self._tray.stop()
        self._close_enrollment()

    def show_settings(self) -> dict[str, str]:
        self._close_enrollment()
        self._view = "settings"
        return {"view": self._view}

    def get_settings_panel(self) -> dict[str, object]:
        return get_panel_settings(self._settings)

    def save_settings_panel(self, updates: dict[str, object]) -> dict[str, object]:
        snapshot = update_panel_settings(self._settings, updates)
        self._settings = load_persisted_settings()
        self._status = PanelStatus(message="Settings saved")
        return {"ok": True, "message": "Settings saved.", "settings": snapshot}

    def create_profile(self, name: str) -> dict[str, object]:
        try:
            return create_profile(self._settings, name)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def rename_profile(self, old_name: str, new_name: str) -> dict[str, object]:
        try:
            result = rename_profile(self._settings, old_name, new_name)
            if result.get("ok"):
                self._settings = load_persisted_settings()
            return result
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def delete_profile(self, name: str) -> dict[str, object]:
        try:
            return delete_profile(self._settings, name)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def activate_profile(self, name: str) -> dict[str, object]:
        try:
            result = activate_profile(self._settings, name)
            if result.get("ok"):
                self._settings = load_persisted_settings()
            return result
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def show_onboarding(self) -> dict[str, str]:
        self._close_enrollment()
        self._view = "onboarding"
        return {"view": self._view}

    def show_enrollment(self, return_view: PanelView = "main") -> dict[str, object]:
        self._close_enrollment()
        session = GestureEnrollmentSession(self._settings)
        try:
            session.open()
        except RuntimeError as exc:
            return _action(False, str(exc))
        self._enrollment = session
        self._enrollment_return_view = return_view
        self._view = "enrollment"
        return {
            "ok": True,
            "view": self._view,
            "enrollment": session.get_state(),
        }

    def get_enrollment_state(self) -> dict[str, object]:
        if self._enrollment is None:
            return {"active": False, "done": False, "message": "Enrollment is not active."}
        return self._enrollment.get_state()

    def get_enrollment_preview(self) -> dict[str, object]:
        if self._enrollment is None:
            return {
                "preview_jpeg": None,
                "hand_detected": False,
                "message": "Enrollment is not active.",
            }
        preview = self._enrollment.grab_preview()
        return {
            "preview_jpeg": preview.preview_jpeg,
            "hand_detected": preview.hand_detected,
            "message": preview.message,
        }

    def enrollment_capture(self) -> dict[str, object]:
        if self._enrollment is None:
            return _action(False, "Enrollment is not active.")
        capture = self._enrollment.capture_current_gesture()
        if capture.ok and capture.done:
            self._onboarding.gestures_complete = True
        self._status = PanelStatus(message=capture.message)
        payload = capture.to_dict()
        payload["enrollment"] = self._enrollment.get_state()
        return payload

    def leave_enrollment(self) -> dict[str, str]:
        return_view = self._enrollment_return_view
        self._close_enrollment()
        self._view = return_view
        return {"view": self._view}

    def show_main(self) -> dict[str, str]:
        self._close_enrollment()
        self._view = "main"
        return {"view": self._view}

    def set_status_message(self, message: str) -> dict[str, object]:
        self._status = self._runtime_panel_status(message)
        return asdict(self._status)

    def _runtime_panel_status(self, message: str) -> PanelStatus:
        self._settings = load_persisted_settings()
        runtime = load_runtime(self._settings)
        return PanelStatus(
            message=message,
            fps=self._status.fps,
            confidence=self._status.confidence,
            tracking=self._engine_runner.is_running(),
            paused=runtime.paused if self._engine_runner.is_running() else False,
            gaze_mode=self._settings.gaze_mode.value,
            last_calibrated=last_calibration_label(self._settings),
        )

    def _tray_handlers(self) -> TrayHandlers:
        return TrayHandlers(
            on_show=self._handle_tray_show,
            on_stop=self._handle_tray_stop,
            on_quit=self._handle_tray_quit,
            on_pause_toggle=self._handle_tray_pause_toggle,
            on_gaze_toggle=self._handle_tray_gaze_toggle,
            pause_label=self._pause_menu_label,
            gaze_checked=self._gaze_only_checked,
        )

    def _pause_menu_label(self) -> str:
        runtime = load_runtime(self._settings)
        return "Resume Tracking" if runtime.paused else "Pause Tracking"

    def _gaze_only_checked(self) -> bool:
        self._settings = load_persisted_settings()
        return self._settings.gaze_mode is GazeMode.GAZE_ONLY

    def _refresh_tray_menu(self) -> None:
        if self._tray is not None:
            self._tray.refresh_menu()

    def _close_enrollment(self) -> None:
        if self._enrollment is not None:
            self._enrollment.close()
            self._enrollment = None

    def _ensure_tray(self) -> None:
        if self._tray is None:
            self._tray = create_tray_backend(self._tray_handlers(), prefer_pystray=False)
        self._tray.ensure_running()

    def _handle_tray_show(self) -> None:
        if self._on_show_panel is not None:
            self._on_show_panel()
        self._status = self._runtime_panel_status("Panel restored.")

    def _handle_tray_stop(self) -> None:
        self.stop_engine()

    def _handle_tray_pause_toggle(self) -> None:
        self.toggle_pause()

    def _handle_tray_gaze_toggle(self) -> None:
        self.toggle_gaze_mode()

    def _handle_tray_quit(self) -> None:
        self.shutdown()
        if self._on_quit_app is not None:
            self._on_quit_app()

    def _start_watchdog(self) -> None:
        if self._watchdog is None:
            self._watchdog = EngineWatchdog(
                self._engine_runner,
                on_crash=self._handle_engine_crash,
            )
        self._watchdog.start()

    def _stop_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.stop()

    def _handle_engine_crash(self, event: WatchdogEvent) -> None:
        if self._tray is not None:
            self._tray.notify(event.message)
        self._status = self._runtime_panel_status(event.message)


def last_calibration_label(settings: Settings) -> str | None:
    """Return the most recent calibration file date for the active profile."""
    from unmouse.gaze.calibration import calibration_path, load_calibration
    from unmouse.gaze.offset_profile import load_offset_profile, offset_profile_path

    candidates: list[float] = []
    cal_path = calibration_path(settings)
    if load_calibration(cal_path) is not None and cal_path.is_file():
        candidates.append(cal_path.stat().st_mtime)
    off_path = offset_profile_path(settings)
    if load_offset_profile(off_path) is not None and off_path.is_file():
        candidates.append(off_path.stat().st_mtime)
    if not candidates:
        return None
    return datetime.fromtimestamp(max(candidates)).strftime("%Y-%m-%d")
