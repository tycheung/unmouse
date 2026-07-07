"""Main action loop: snap gaze, drive cursor, clicks, scroll, and indicator."""

from __future__ import annotations

import threading
import time
from queue import Empty

from unmouse.arbitrator.actions import ActionDriver, create_action_driver
from unmouse.arbitrator.snap import SnapEngine, SnapOrchestrator
from unmouse.arbitrator.window_chrome import create_snap_orchestrator, create_window_chrome_provider
from unmouse.config import GazeMode, Settings
from unmouse.overlay.indicator import (
    GazeIndicatorOverlay,
    IndicatorState,
    LuminanceSampler,
    create_indicator_backend,
    indicator_state_from_system,
)
from unmouse.state import SystemState

CONTROLLER_TARGET_HZ = 30.0


class ActionController:
    """Apply snapping and OS actions from shared runtime state."""

    def __init__(
        self,
        state: SystemState,
        settings: Settings,
        driver: ActionDriver | None = None,
        snap_engine: SnapEngine | None = None,
        snap_orchestrator: SnapOrchestrator | None = None,
        overlay: GazeIndicatorOverlay | None = None,
        luminance_sampler: LuminanceSampler | None = None,
        *,
        target_hz: float = CONTROLLER_TARGET_HZ,
        enable_overlay: bool = True,
        prefer_win32: bool = True,
    ) -> None:
        self._state = state
        self._settings = settings
        self._driver = driver or create_action_driver(
            failsafe=settings.pyautogui_failsafe,
            prefer_pyautogui=False,
        )
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
        """Run one controller iteration and return post-snap gaze coordinates."""
        now = timestamp_s if timestamp_s is not None else time.perf_counter()
        gaze = self._state.get_gaze()
        targets = self._snap_orchestrator.list_targets()
        snapped = self._snap_engine.snap(gaze.x, gaze.y, targets, timestamp_s=now)
        self._last_x = snapped.x
        self._last_y = snapped.y

        if not self._settings.paused:
            self._apply_pointer_actions(snapped.x, snapped.y, now)
        return snapped.x, snapped.y

    def _apply_pointer_actions(self, x: float, y: float, timestamp_s: float) -> None:
        del timestamp_s
        if self._should_move_cursor():
            self._driver.move_to(x, y)
        click_queue = self._state.click_event_queue
        if click_queue is not None:
            while True:
                try:
                    event = click_queue.get_nowait()
                except Empty:
                    break
                self._driver.click(event.x, event.y, button=event.button)
        scroll_queue = self._state.scroll_tick_queue
        if scroll_queue is not None:
            while True:
                try:
                    tick = scroll_queue.get_nowait()
                except Empty:
                    break
                self._driver.scroll(tick.x, tick.y, tick.delta)

    def _should_move_cursor(self) -> bool:
        if self._settings.gaze_mode == GazeMode.GAZE_ONLY:
            return self._state.click_mode
        return True

    def _indicator_state(self) -> IndicatorState:
        styled = indicator_state_from_system(self._state, sampler=self._sampler)
        return IndicatorState(
            x=self._last_x,
            y=self._last_y,
            visible=styled.visible,
            fill_color=styled.fill_color,
            stroke_color=styled.stroke_color,
            stroke_width=styled.stroke_width,
            diameter=styled.diameter,
            scroll_chevron=styled.scroll_chevron,
        )

    def _run(self) -> None:
        while self._state.is_running():
            started = time.perf_counter()
            self.tick()
            elapsed = time.perf_counter() - started
            sleep_for = self._interval_s - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)


def _default_snap_orchestrator(prefer_win32: bool) -> SnapOrchestrator:
    from unmouse.arbitrator.uia_provider import create_uia_snap_provider

    return create_snap_orchestrator(
        chrome_provider=create_window_chrome_provider(prefer_win32=prefer_win32),
        extra_providers=(create_uia_snap_provider(prefer_uia=prefer_win32),),
    )
