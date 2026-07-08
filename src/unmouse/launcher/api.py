from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from unmouse.config import GazeMode, Settings
from unmouse.diagnostics import load_diagnostics_snapshot
from unmouse.launcher.api_helpers import action, last_calibration_label, update_payload
from unmouse.launcher.engine_runner import EngineRunner, EngineWatchdog, WatchdogEvent
from unmouse.launcher.enroll_ui import GestureEnrollmentSession, profile_has_gesture_templates
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.settings import (
    activate_profile,
    create_profile,
    delete_profile,
    get_panel_settings,
    rename_profile,
    toggle_gaze_mode,
    update_panel_settings,
)
from unmouse.launcher.tray import TrayBackend, TrayHandlers, create_tray_backend
from unmouse.launcher.update import UpdateStatus, apply_update, check_updates
from unmouse.persistence import load_persisted_settings
from unmouse.runtime import RuntimeState, load_runtime, set_paused, toggle_paused

PanelView = Literal["main", "settings", "onboarding", "enrollment"]

__all__ = ["PanelApi", "PanelStatus", "PanelView", "last_calibration_label"]


@dataclass
class PanelStatus:
    message: str
    fps: float | None = None
    fixation: float | None = None
    tracking: bool = False
    paused: bool = False
    gaze_mode: str = "cursor_follow"
    last_calibrated: str | None = None


@dataclass
class PanelState:
    settings: Settings
    view: PanelView = "main"
    status: PanelStatus = field(default_factory=lambda: PanelStatus(message="Ready"))
    enrollment: GestureEnrollmentSession | None = None
    enrollment_return_view: PanelView = "main"
    update_status: UpdateStatus | None = None


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
        self._engine_runner = engine_runner or EngineRunner()
        self._tray = tray
        self._watchdog = watchdog
        self._on_show_panel: Callable[[], None] | None = None
        self._on_minimize_panel: Callable[[], None] | None = None
        self._on_quit_app: Callable[[], None] | None = None
        if self._onboarding.should_show_on_startup():
            self._state.view = "onboarding"

    @property
    def view(self) -> PanelView:
        return self._state.view

    @property
    def tray(self) -> TrayBackend | None:
        return self._tray

    @property
    def _settings(self) -> Settings:
        return self._state.settings

    def set_status(
        self,
        message: str,
        *,
        settings: Settings | None = None,
        runtime: RuntimeState | None = None,
    ) -> None:
        self._state.status = self._build_status(message, settings=settings, runtime=runtime)

    def get_status(self) -> dict[str, object]:
        tracking, paused = self._tracking_and_paused()
        diagnostics = load_diagnostics_snapshot(self._state.settings) if tracking else None
        return asdict(
            PanelStatus(
                message=self._state.status.message,
                fps=diagnostics.broker_fps if diagnostics else self._state.status.fps,
                fixation=diagnostics.gaze_fixation
                if diagnostics
                else self._state.status.fixation,
                tracking=tracking,
                paused=paused,
                gaze_mode=self._state.settings.gaze_mode.value,
                last_calibrated=last_calibration_label(self._state.settings),
            ),
        )

    def toggle_pause(self) -> dict[str, object]:
        if not self._engine_runner.is_running():
            return action(False, "Start tracking before pausing.")
        runtime = toggle_paused(self._state.settings)
        self._refresh_tray_menu()
        message = "Tracking paused." if runtime.paused else "Tracking resumed."
        self.set_status(message, runtime=runtime)
        return action(True, message, paused=runtime.paused)

    def toggle_gaze_mode(self) -> dict[str, object]:
        mode = toggle_gaze_mode(self._state.settings)
        self._state.settings.gaze_mode = mode
        self._refresh_tray_menu()
        label = (
            "Gaze-only mode enabled."
            if mode is GazeMode.GAZE_ONLY
            else "Cursor follow enabled."
        )
        self.set_status(label)
        return action(True, label, gaze_mode=mode.value)

    def get_view(self) -> dict[str, str]:
        return {"view": self._state.view}

    def get_onboarding_state(self) -> dict[str, object]:
        return self._onboarding.get_state()

    def onboarding_advance(self) -> dict[str, object]:
        result = self._onboarding.advance()
        if result.get("ok") and self._onboarding.current_step.id == "ready":
            self.set_status("Setup complete")
        return result

    def onboarding_skip(self, confirmed: bool = False) -> dict[str, object]:
        return self._onboarding.skip_current_step(confirmed=confirmed)

    def onboarding_check_camera(self) -> dict[str, object]:
        with self._release_camera():
            return self._forward_with_status(self._onboarding.check_camera(), "Camera OK")

    def onboarding_run_calibration(self) -> dict[str, object]:
        with self._release_camera():
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

    def onboarding_complete(self) -> dict[str, object]:
        result = self._onboarding.complete()
        self._state.view = "main"
        self.set_status("Ready")
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
        self.set_status(self._state.update_status.message)
        return action(
            not self._state.update_status.available,
            self._state.update_status.message,
            update=update_payload(self._state.update_status),
        )

    def start_calibrate(self) -> dict[str, object]:
        from unmouse.launcher.calibration_wizards import run_calibration_wizard

        with self._release_camera():
            outcome = run_calibration_wizard(self._state.settings)
        self.set_status(outcome.message)
        return action(outcome.ok, outcome.message)

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
            return action(True, "Engine already running.", tracking=True)
        status = self._engine_runner.start()
        if not status.ok or not status.running:
            return action(False, status.message)
        runtime = set_paused(self._state.settings, False)
        self._ensure_tray()
        self._start_watchdog()
        if self._on_minimize_panel is not None:
            self._on_minimize_panel()
        self.set_status(status.message, runtime=runtime)
        return action(True, status.message, tracking=True, minimize=True, pid=status.pid)

    def stop_engine(self) -> dict[str, object]:
        self._stop_watchdog()
        status = self._engine_runner.stop()
        self.set_status(status.message)
        return action(status.ok, status.message)

    def shutdown(self) -> None:
        self._stop_watchdog()
        self._engine_runner.stop()
        if self._tray is not None:
            self._tray.stop()
        self._close_enrollment()

    def show_settings(self) -> dict[str, str]:
        return self._show_view("settings")

    def get_settings_panel(self) -> dict[str, object]:
        return get_panel_settings(self._state.settings)

    def save_settings_panel(self, updates: dict[str, object]) -> dict[str, object]:
        snapshot = update_panel_settings(self._state.settings, updates)
        self._state.settings = load_persisted_settings()
        restarted = self._reload_if_running()
        message = "Settings saved. Restarting tracking." if restarted else "Settings saved."
        self.set_status(message)
        return {"ok": True, "message": message, "settings": snapshot, "restarted": restarted}

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
        self.set_status(capture.message)
        payload = capture.to_dict()
        payload["enrollment"] = self._state.enrollment.get_state()
        return payload

    def leave_enrollment(self) -> dict[str, str]:
        return_view = self._state.enrollment_return_view
        self._close_enrollment()
        self._state.view = return_view
        return {"view": self._state.view}

    def show_main(self) -> dict[str, str]:
        return self._show_view("main")

    def _forward_with_status(
        self,
        result: dict[str, object],
        default_message: str,
    ) -> dict[str, object]:
        if result.get("ok"):
            self.set_status(str(result.get("message", default_message)))
        return result

    def _with_onboarding_state(self, payload: dict[str, object]) -> dict[str, object]:
        return {**payload, "state": self._onboarding.get_state()}

    def _show_view(self, view: PanelView) -> dict[str, str]:
        self._close_enrollment()
        self._state.view = view
        return {"view": self._state.view}

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

    def _open_enrollment(self, *, return_view: PanelView) -> dict[str, object]:
        self._close_enrollment()
        session = GestureEnrollmentSession(self._state.settings)
        try:
            with self._release_camera():
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

    @contextmanager
    def _release_camera(self) -> Iterator[None]:
        was_running = self._engine_runner.is_running()
        if was_running:
            self._stop_watchdog()
            self._engine_runner.stop()
        try:
            yield
        finally:
            if was_running:
                status = self._engine_runner.start()
                if status.ok and status.running:
                    set_paused(self._state.settings, False)
                    self._start_watchdog()
                    self.set_status(status.message)

    def _reload_if_running(self) -> bool:
        if not self._engine_runner.is_running():
            return False
        self._stop_watchdog()
        self._engine_runner.stop()
        status = self._engine_runner.start()
        if status.ok and status.running:
            set_paused(self._state.settings, False)
            self._start_watchdog()
        self.set_status(status.message)
        return status.ok and status.running

    def _build_status(
        self,
        message: str,
        *,
        settings: Settings | None = None,
        runtime: RuntimeState | None = None,
    ) -> PanelStatus:
        resolved_settings = settings or self._state.settings
        self._state.settings = resolved_settings
        tracking, paused = self._tracking_and_paused(runtime=runtime)
        return replace(
            self._state.status,
            message=message,
            tracking=tracking,
            paused=paused,
            gaze_mode=resolved_settings.gaze_mode.value,
            last_calibrated=last_calibration_label(resolved_settings),
        )

    def _tracking_and_paused(self, *, runtime: RuntimeState | None = None) -> tuple[bool, bool]:
        if not self._engine_runner.is_running():
            return False, False
        resolved = runtime or load_runtime(self._state.settings)
        return True, resolved.paused

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
        runtime = load_runtime(self._state.settings)
        return "Resume Tracking" if runtime.paused else "Pause Tracking"

    def _gaze_only_checked(self) -> bool:
        return self._state.settings.gaze_mode is GazeMode.GAZE_ONLY

    def _refresh_tray_menu(self) -> None:
        if self._tray is not None:
            self._tray.refresh_menu()

    def _ensure_tray(self) -> None:
        if self._tray is None:
            self._tray = create_tray_backend(self._tray_handlers(), prefer_pystray=False)
        self._tray.ensure_running()

    def _handle_tray_show(self) -> None:
        if self._on_show_panel is not None:
            self._on_show_panel()
        self.set_status("Panel restored.")

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
        self.set_status(event.message)
