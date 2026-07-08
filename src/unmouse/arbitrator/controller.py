from __future__ import annotations

import threading
import time
from dataclasses import replace

from unmouse.arbitrator.actions import ActionDriver, create_action_driver
from unmouse.arbitrator.snap import (
    CompositeSnapOrchestrator,
    SnapEngine,
    SnapProvider,
    create_snap_orchestrator,
)
from unmouse.arbitrator.window_chrome import create_window_chrome_provider
from unmouse.config import GazeMode, Settings
from unmouse.overlay.indicator import (
    GazeIndicatorOverlay,
    IndicatorState,
    LuminanceSampler,
    create_indicator_backend,
    indicator_state_from_system,
)
from unmouse.state import SystemState
from unmouse.utils.queues import drain_all
from unmouse.utils.timing import run_at_interval

CONTROLLER_TARGET_HZ = 30.0


class ActionController:
    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        driver: ActionDriver | None = None,
        snap_engine: SnapEngine | None = None,
        snap_orchestrator: SnapProvider | None = None,
        overlay: GazeIndicatorOverlay | None = None,
        luminance_sampler: LuminanceSampler | None = None,
        *,
        target_hz: float = CONTROLLER_TARGET_HZ,
        enable_overlay: bool = True,
        prefer_win32: bool = True,
    ) -> None:
        self._state = state
        self._settings = settings
        self._driver = driver or create_action_driver(failsafe=settings.pyautogui_failsafe)
        self._snap_engine = snap_engine or SnapEngine(snap_radius_px=settings.snap_radius_px)
        self._snap_orchestrator = snap_orchestrator or _default_snap_orchestrator(prefer_win32)
        self._sampler = luminance_sampler
        self._interval_s = 1.0 / target_hz
        self._overlay = overlay
        if enable_overlay and overlay is None:
            self._overlay = GazeIndicatorOverlay(
                backend=create_indicator_backend(prefer_win32=prefer_win32),
                target_fps=target_hz,
                state_provider=self._indicator_state,
            )
        self._thread: threading.Thread | None = None
        self._last_x = settings.screen_width / 2
        self._last_y = settings.screen_height / 2

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self._overlay is not None:
            self._overlay.start()
        self._thread = threading.Thread(target=self._run, name="action-controller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._overlay is not None:
            self._overlay.stop()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def tick(self, *, timestamp_s: float | None = None) -> tuple[float, float]:
        now = timestamp_s if timestamp_s is not None else time.perf_counter()
        gaze = self._state.get_gaze()
        targets = self._snap_orchestrator.list_targets()
        snapped = self._snap_engine.snap(gaze.x, gaze.y, targets, timestamp_s=now)
        self._last_x = snapped.x
        self._last_y = snapped.y

        if not self._settings.paused and gaze.valid:
            self._apply_pointer_actions(snapped.x, snapped.y)
        return snapped.x, snapped.y

    def _apply_pointer_actions(self, x: float, y: float) -> None:
        if self._should_move_cursor():
            self._driver.move_to(x, y)
        for event in drain_all(self._state.click_event_queue):
            self._driver.click(event.x, event.y, button=event.button)
        for tick in drain_all(self._state.scroll_tick_queue):
            self._driver.scroll(tick.x, tick.y, tick.delta)

    def _should_move_cursor(self) -> bool:
        if self._settings.gaze_mode == GazeMode.GAZE_ONLY:
            return self._state.click_mode
        return True

    def _indicator_state(self) -> IndicatorState:
        gaze = self._state.get_gaze()
        styled = indicator_state_from_system(
            self._state, sampler=self._sampler, visible=gaze.valid
        )
        return replace(styled, x=self._last_x, y=self._last_y)

    def _run(self) -> None:
        run_at_interval(self._state.is_running, self.tick, self._interval_s)


def _default_snap_orchestrator(prefer_win32: bool) -> CompositeSnapOrchestrator:
    from unmouse.arbitrator.uia_provider import create_uia_snap_provider

    return create_snap_orchestrator(
        chrome_provider=create_window_chrome_provider(prefer_win32=prefer_win32),
        extra_providers=(create_uia_snap_provider(prefer_uia=prefer_win32),),
    )
