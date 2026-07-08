"""System tray integration for the launcher."""

from __future__ import annotations

import importlib
import importlib.util
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

TrayAction = Callable[[], None]
TrayLabel = Callable[[], str]
TrayChecked = Callable[[], bool]


@dataclass(frozen=True)
class TrayHandlers:
    on_show: TrayAction
    on_stop: TrayAction
    on_quit: TrayAction
    on_pause_toggle: TrayAction | None = None
    on_gaze_toggle: TrayAction | None = None
    pause_label: TrayLabel | None = None
    gaze_checked: TrayChecked | None = None


class TrayBackend(Protocol):
    def ensure_running(self) -> None: ...

    def stop(self) -> None: ...

    def refresh_menu(self) -> None: ...

    def notify(self, message: str, *, title: str = "unmouse") -> None: ...


@dataclass
class NoopTrayBackend:
    handlers: TrayHandlers
    running: bool = False
    notifications: list[str] | None = None

    def ensure_running(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def refresh_menu(self) -> None:
        return None

    def notify(self, message: str, *, title: str = "unmouse") -> None:
        if self.notifications is None:
            self.notifications = []
        self.notifications.append(message)


class TrayController:
    def __init__(self, handlers: TrayHandlers, *, title: str = "unmouse") -> None:
        self._handlers = handlers
        self._title = title
        self._icon: Any | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def ensure_running(self) -> None:
        if self._running:
            return
        pystray: Any = importlib.import_module("pystray")
        icon = pystray.Icon(
            self._title,
            create_tray_icon_image(),
            self._title,
            self._build_menu(pystray),
        )
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

    def refresh_menu(self) -> None:
        if self._icon is not None:
            update = getattr(self._icon, "update_menu", None)
            if callable(update):
                update()

    def notify(self, message: str, *, title: str = "unmouse") -> None:
        if self._icon is None:
            return
        notify = getattr(self._icon, "notify", None)
        if callable(notify):
            notify(message, title)

    def _build_menu(self, pystray: Any) -> Any:
        items: list[Any] = [
            pystray.MenuItem("Show Panel", lambda _i, _m: self._handlers.on_show()),
        ]
        if self._handlers.on_pause_toggle is not None:
            label = self._handlers.pause_label or (lambda: "Pause Tracking")
            items.append(pystray.MenuItem(label, lambda _i, _m: self._handlers.on_pause_toggle()))
        if self._handlers.on_gaze_toggle is not None:
            checked = self._handlers.gaze_checked or (lambda: False)
            items.append(
                pystray.MenuItem(
                    "Gaze-only mode",
                    lambda _i, _m: self._handlers.on_gaze_toggle(),
                    checked=checked,
                ),
            )
        items.extend(
            [
                pystray.MenuItem("Stop Tracking", lambda _i, _m: self._handlers.on_stop()),
                pystray.MenuItem("Quit", lambda _i, _m: self._handlers.on_quit()),
            ],
        )
        return pystray.Menu(*items)


def create_tray_backend(handlers: TrayHandlers, *, prefer_pystray: bool = True) -> TrayBackend:
    if prefer_pystray and importlib.util.find_spec("pystray") is not None:
        return TrayController(handlers)
    return NoopTrayBackend(handlers)


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
