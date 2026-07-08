from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol

from unmouse.arbitrator.snap import (
    CachedSnapProvider,
    CompositeSnapOrchestrator,
    SnapProvider,
    SnapRect,
    SnapTarget,
)
from unmouse.platform import is_windows

DEFAULT_CHROME_CACHE_INTERVAL_S = 0.5
DEFAULT_CHROME_BUTTON_WIDTH = 46.0
DEFAULT_TITLE_BAR_HEIGHT = 32.0
CHROME_SNAP_PRIORITY = 10


@dataclass(frozen=True)
class WindowRect:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class ChromeButton:
    role: str
    bounds: SnapRect


class WindowChromeReader(Protocol):
    def read_buttons(self) -> tuple[ChromeButton, ...]: ...


@dataclass
class NullWindowChromeReader:
    buttons: tuple[ChromeButton, ...]
    calls: int = 0

    def read_buttons(self) -> tuple[ChromeButton, ...]:
        self.calls += 1
        return self.buttons


class Win32WindowChromeReader:
    def __init__(
        self,
        *,
        button_width: float = DEFAULT_CHROME_BUTTON_WIDTH,
        title_bar_height: float = DEFAULT_TITLE_BAR_HEIGHT,
    ) -> None:
        self._button_width = button_width
        self._title_bar_height = title_bar_height

    def read_buttons(self) -> tuple[ChromeButton, ...]:
        window = read_foreground_window_rect()
        if window is None:
            return ()
        return build_heuristic_chrome_buttons(
            window,
            button_width=self._button_width,
            title_bar_height=self._title_bar_height,
        )


def create_window_chrome_provider(
    *,
    cache_interval_s: float = DEFAULT_CHROME_CACHE_INTERVAL_S,
    prefer_win32: bool = True,
    reader: WindowChromeReader | None = None,
    priority: int = CHROME_SNAP_PRIORITY,
) -> SnapProvider:
    resolved_reader: WindowChromeReader = reader or (
        Win32WindowChromeReader()
        if prefer_win32 and is_windows()
        else NullWindowChromeReader(buttons=())
    )

    def loader() -> tuple[SnapTarget, ...]:
        return chrome_buttons_to_snap_targets(resolved_reader.read_buttons(), priority=priority)

    return CachedSnapProvider(loader=loader, cache_interval_s=cache_interval_s)


def build_heuristic_chrome_buttons(
    window: WindowRect,
    *,
    button_width: float = DEFAULT_CHROME_BUTTON_WIDTH,
    title_bar_height: float = DEFAULT_TITLE_BAR_HEIGHT,
) -> tuple[ChromeButton, ...]:
    buttons: list[ChromeButton] = []
    for index, role in enumerate(("close", "maximize", "minimize")):
        x = window.right - (index + 1) * button_width
        bounds = SnapRect(x=x, y=window.top, width=button_width, height=title_bar_height)
        buttons.append(ChromeButton(role=role, bounds=bounds))
    return tuple(buttons)


def chrome_buttons_to_snap_targets(
    buttons: tuple[ChromeButton, ...],
    *,
    priority: int = CHROME_SNAP_PRIORITY,
) -> tuple[SnapTarget, ...]:
    return tuple(
        SnapTarget(
            target_id=f"chrome:{button.role}",
            bounds=button.bounds,
            priority=priority,
        )
        for button in buttons
    )


def read_foreground_window_rect() -> WindowRect | None:
    if not is_windows():
        return None

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None

    return WindowRect(
        left=float(rect.left),
        top=float(rect.top),
        right=float(rect.right),
        bottom=float(rect.bottom),
    )


def create_snap_orchestrator(
    *,
    chrome_provider: SnapProvider | None = None,
    extra_providers: tuple[SnapProvider, ...] = (),
) -> CompositeSnapOrchestrator:
    providers: list[SnapProvider] = []
    if chrome_provider is not None:
        providers.append(chrome_provider)
    providers.extend(extra_providers)
    return CompositeSnapOrchestrator(providers)
