from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Callable
from typing import Any

from unmouse.config import Settings
from unmouse.runtime import sync_engine_controls, toggle_paused

HotkeyCallback = Callable[[], None]


class PauseHotkeyListener:
    def __init__(
        self,
        hotkey: str,
        on_toggle: HotkeyCallback,
        *,
        keyboard_module: Any | None = None,
    ) -> None:
        self._hotkey = hotkey
        self._on_toggle = on_toggle
        self._keyboard = keyboard_module
        self._handle: object | None = None
        self._lock = threading.RLock()

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def start(self) -> None:
        with self._lock:
            keyboard = self._keyboard or importlib.import_module("keyboard")
            self._keyboard = keyboard
            self.stop()
            self._handle = keyboard.add_hotkey(self._hotkey, self._on_toggle, suppress=False)

    def stop(self) -> None:
        with self._lock:
            if self._handle is None or self._keyboard is None:
                self._handle = None
                return
            remove = getattr(self._keyboard, "remove_hotkey", None)
            if callable(remove):
                remove(self._handle)
            self._handle = None

    def update_hotkey(self, hotkey: str) -> None:
        with self._lock:
            if hotkey == self._hotkey and self._handle is not None:
                return
            self._hotkey = hotkey
            if self._keyboard is not None:
                self.start()


class NoopHotkeyListener:
    def __init__(self, hotkey: str, on_toggle: HotkeyCallback) -> None:
        self._hotkey = hotkey
        self._on_toggle = on_toggle
        self.started = False

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def update_hotkey(self, hotkey: str) -> None:
        self._hotkey = hotkey

    def trigger(self) -> None:
        self._on_toggle()


class EngineRuntimeController:
    def __init__(
        self,
        settings: Settings,
        *,
        poll_interval_s: float = 0.2,
        sleep: Callable[[float], None] = time.sleep,
        hotkey_listener: PauseHotkeyListener | NoopHotkeyListener | None = None,
    ) -> None:
        self._settings = settings
        self._poll_interval_s = poll_interval_s
        self._sleep = sleep
        self._hotkey = hotkey_listener or PauseHotkeyListener(
            settings.pause_hotkey,
            self._handle_hotkey_toggle,
        )
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_hotkey = settings.pause_hotkey

    def start(self) -> None:
        sync_engine_controls(self._settings)
        self._hotkey.start()
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="engine-runtime-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._hotkey.stop()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _handle_hotkey_toggle(self) -> None:
        toggle_paused(self._settings)
        sync_engine_controls(self._settings)

    def _run(self) -> None:
        while self._running:
            sync_engine_controls(self._settings)
            if self._settings.pause_hotkey != self._last_hotkey:
                self._hotkey.update_hotkey(self._settings.pause_hotkey)
                self._last_hotkey = self._settings.pause_hotkey
            self._sleep(self._poll_interval_s)
