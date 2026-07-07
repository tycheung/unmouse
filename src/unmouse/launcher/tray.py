"""System tray integration for the launcher."""

from __future__ import annotations

import importlib
import importlib.util
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

TrayAction = Callable[[], None]


class TrayBackend(Protocol):
    def ensure_running(self) -> None: ...

    def stop(self) -> None: ...


@dataclass
class FakeTrayBackend:
    """Records tray lifecycle for unit tests."""

    running: bool = False
    actions: list[str] = field(default_factory=list)
    on_show: TrayAction | None = None
    on_stop: TrayAction | None = None
    on_quit: TrayAction | None = None

    def ensure_running(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def trigger_show(self) -> None:
        self.actions.append("show")
        if self.on_show:
            self.on_show()

    def trigger_stop(self) -> None:
        self.actions.append("stop")
        if self.on_stop:
            self.on_stop()

    def trigger_quit(self) -> None:
        self.actions.append("quit")
        if self.on_quit:
            self.on_quit()


class TrayController:
    """Windows notification-area icon with Show, Stop, and Quit actions."""

    def __init__(
        self,
        *,
        on_show: TrayAction,
        on_stop: TrayAction,
        on_quit: TrayAction,
        title: str = "unmouse",
    ) -> None:
        self._on_show = on_show
        self._on_stop = on_stop
        self._on_quit = on_quit
        self._title = title
        self._icon: object | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def ensure_running(self) -> None:
        if self._running:
            return
        pystray: Any = importlib.import_module("pystray")

        menu = pystray.Menu(
            pystray.MenuItem("Show Panel", lambda _icon, _item: self._on_show()),
            pystray.MenuItem("Stop Tracking", lambda _icon, _item: self._on_stop()),
            pystray.MenuItem("Quit", lambda _icon, _item: self._on_quit()),
        )
        icon = pystray.Icon(self._title, create_tray_icon_image(), self._title, menu)
        self._icon = icon
        self._thread = threading.Thread(target=icon.run, name="unmouse-tray", daemon=True)
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        if self._icon is not None:
            stop = getattr(self._icon, "stop", None)
            if callable(stop):
                stop()
        self._icon = None
        self._thread = None
        self._running = False


def create_tray_backend(
    *,
    on_show: TrayAction,
    on_stop: TrayAction,
    on_quit: TrayAction,
    prefer_pystray: bool = True,
) -> TrayBackend:
    if prefer_pystray and importlib.util.find_spec("pystray") is not None:
        return TrayController(on_show=on_show, on_stop=on_stop, on_quit=on_quit)
    backend = FakeTrayBackend(on_show=on_show, on_stop=on_stop, on_quit=on_quit)
    return backend


def create_tray_icon_image(size: int = 64) -> object:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=(91, 155, 213, 255),
        outline=(122, 176, 224, 255),
        width=2,
    )
    return image
