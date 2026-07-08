"""Engine lifecycle and tray integration for the control panel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from unmouse.config import GazeMode
from unmouse.diagnostics import load_diagnostics_snapshot
from unmouse.launcher.api_helpers import action, last_calibration_label
from unmouse.launcher.engine_runner import EngineRunner, EngineWatchdog, WatchdogEvent
from unmouse.launcher.services.panel_state import PanelState, PanelStatus
from unmouse.launcher.settings import toggle_gaze_mode
from unmouse.launcher.tray import TrayBackend, TrayHandlers, create_tray_backend
from unmouse.persistence import load_persisted_settings
from unmouse.runtime import load_runtime, set_paused, toggle_paused


class EngineService:
    def __init__(
        self,
        state: PanelState,
        engine_runner: EngineRunner,
        *,
        tray: TrayBackend | None = None,
        watchdog: EngineWatchdog | None = None,
        on_show_panel: Callable[[], None] | None = None,
        on_minimize_panel: Callable[[], None] | None = None,
        on_quit_app: Callable[[], None] | None = None,
    ) -> None:
        self._state = state
        self._engine_runner = engine_runner
        self._tray = tray
        self._watchdog = watchdog
        self._on_show_panel = on_show_panel
        self._on_minimize_panel = on_minimize_panel
        self._on_quit_app = on_quit_app

    @property
    def tray(self) -> TrayBackend | None:
        return self._tray

    def configure_shell(
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

    def get_status(self) -> dict[str, object]:
        self._state.settings = load_persisted_settings()
        runtime = load_runtime(self._state.settings)
        diagnostics = (
            load_diagnostics_snapshot(self._state.settings)
            if self._engine_runner.is_running()
            else None
        )
        return asdict(
            PanelStatus(
                message=self._state.status.message,
                fps=diagnostics.broker_fps if diagnostics else self._state.status.fps,
                confidence=diagnostics.gaze_confidence
                if diagnostics
                else self._state.status.confidence,
                tracking=self._engine_runner.is_running(),
                paused=runtime.paused if self._engine_runner.is_running() else False,
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
        self._state.status = self._runtime_panel_status(message)
        payload = action(True, message)
        payload["paused"] = runtime.paused
        return payload

    def toggle_gaze_mode(self) -> dict[str, object]:
        mode = toggle_gaze_mode(self._state.settings)
        self._state.settings = load_persisted_settings()
        self._refresh_tray_menu()
        label = (
            "Gaze-only mode enabled."
            if mode is GazeMode.GAZE_ONLY
            else "Cursor follow enabled."
        )
        self._state.status = self._runtime_panel_status(label)
        payload = action(True, label)
        payload["gaze_mode"] = mode.value
        return payload

    def start_launch(self) -> dict[str, object]:
        if self._engine_runner.is_running():
            self._ensure_tray()
            payload = action(True, "Engine already running.")
            payload["tracking"] = True
            return payload
        status = self._engine_runner.start()
        if not status.ok or not status.running:
            return action(False, status.message)
        set_paused(self._state.settings, False)
        self._ensure_tray()
        self._start_watchdog()
        if self._on_minimize_panel is not None:
            self._on_minimize_panel()
        self._state.status = self._runtime_panel_status(status.message)
        payload = action(True, status.message)
        payload["tracking"] = True
        payload["minimize"] = True
        payload["pid"] = status.pid
        return payload

    def stop_engine(self) -> dict[str, object]:
        self._stop_watchdog()
        status = self._engine_runner.stop()
        self._state.status = self._runtime_panel_status(status.message)
        return action(status.ok, status.message)

    def shutdown(self) -> None:
        self._stop_watchdog()
        self._engine_runner.stop()
        if self._tray is not None:
            self._tray.stop()

    def set_status_message(self, message: str) -> dict[str, object]:
        self._state.status = self._runtime_panel_status(message)
        return asdict(self._state.status)

    def _runtime_panel_status(self, message: str) -> PanelStatus:
        self._state.settings = load_persisted_settings()
        runtime = load_runtime(self._state.settings)
        return PanelStatus(
            message=message,
            fps=self._state.status.fps,
            confidence=self._state.status.confidence,
            tracking=self._engine_runner.is_running(),
            paused=runtime.paused if self._engine_runner.is_running() else False,
            gaze_mode=self._state.settings.gaze_mode.value,
            last_calibrated=last_calibration_label(self._state.settings),
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
        runtime = load_runtime(self._state.settings)
        return "Resume Tracking" if runtime.paused else "Pause Tracking"

    def _gaze_only_checked(self) -> bool:
        self._state.settings = load_persisted_settings()
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
        self._state.status = self._runtime_panel_status("Panel restored.")

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
        self._state.status = self._runtime_panel_status(event.message)
