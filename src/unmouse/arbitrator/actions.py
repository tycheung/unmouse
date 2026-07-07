"""Mockable OS action drivers for cursor movement and clicks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

ClickButton = Literal["left", "right", "middle"]


class ActionDriver(Protocol):
    def move_to(self, x: float, y: float) -> None: ...

    def click(self, x: float, y: float, button: ClickButton = "left") -> None: ...

    def scroll(self, x: float, y: float, delta: float) -> None: ...


@dataclass
class FakeActionDriver:
    """In-memory action driver for tests and offline development."""

    moves: list[tuple[int, int]] = field(default_factory=list)
    clicks: list[tuple[int, int, ClickButton]] = field(default_factory=list)
    scrolls: list[tuple[int, int, int]] = field(default_factory=list)

    def move_to(self, x: float, y: float) -> None:
        self.moves.append(_to_point(x, y))

    def click(self, x: float, y: float, button: ClickButton = "left") -> None:
        self.clicks.append((*_to_point(x, y), button))

    def scroll(self, x: float, y: float, delta: float) -> None:
        clicks = int(round(delta))
        if clicks == 0:
            return
        self.scrolls.append((*_to_point(x, y), clicks))

    def clear(self) -> None:
        self.moves.clear()
        self.clicks.clear()
        self.scrolls.clear()


class PyAutoGUIActionDriver:
    """PyAutoGUI-backed driver with failsafe disabled by default."""

    def __init__(self, *, failsafe: bool = False, pause: float = 0.0) -> None:
        import pyautogui  # type: ignore[import-untyped]

        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = pause
        self._pyautogui = pyautogui

    def move_to(self, x: float, y: float) -> None:
        self._pyautogui.moveTo(*_to_point(x, y))

    def click(self, x: float, y: float, button: ClickButton = "left") -> None:
        px, py = _to_point(x, y)
        self._pyautogui.click(x=px, y=py, button=button)

    def scroll(self, x: float, y: float, delta: float) -> None:
        clicks = int(round(delta))
        if clicks == 0:
            return
        px, py = _to_point(x, y)
        self._pyautogui.scroll(clicks, x=px, y=py)


def create_action_driver(*, failsafe: bool = False, prefer_pyautogui: bool = True) -> ActionDriver:
    if prefer_pyautogui:
        try:
            return PyAutoGUIActionDriver(failsafe=failsafe)
        except ImportError:
            pass
    return FakeActionDriver()


def _to_point(x: float, y: float) -> tuple[int, int]:
    return int(round(x)), int(round(y))
