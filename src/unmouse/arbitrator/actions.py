from __future__ import annotations

from typing import Literal, Protocol

ClickButton = Literal["left", "right", "middle"]


class ActionDriver(Protocol):
    def move_to(self, x: float, y: float) -> None: ...

    def click(self, x: float, y: float, button: ClickButton = "left") -> None: ...

    def scroll(self, x: float, y: float, delta: float) -> None: ...


class PyAutoGUIActionDriver:
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


def create_action_driver(*, failsafe: bool = False) -> ActionDriver:
    return PyAutoGUIActionDriver(failsafe=failsafe)


def _to_point(x: float, y: float) -> tuple[int, int]:
    return int(round(x)), int(round(y))
