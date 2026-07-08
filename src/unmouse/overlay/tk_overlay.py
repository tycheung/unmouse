"""Shared Tk transparent overlay thread and Win32 click-through helpers."""

from __future__ import annotations

import queue
import sys
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import tkinter as tk

    from unmouse.overlay.indicator import IndicatorState

TRANSPARENT_CHROMA = "#FF00FF"
MIN_OVERLAY_FPS = 30.0

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
CLICK_THROUGH_STYLES = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW


def apply_click_through_styles(hwnd: int) -> None:
    if sys.platform != "win32":
        return

    import ctypes

    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | CLICK_THROUGH_STYLES)


class TkFullscreenOverlay(ABC):
    def __init__(self, *, thread_name: str) -> None:
        self._commands: queue.Queue[Any | None] = queue.Queue()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_name = thread_name

    def send_command(self, command: object) -> None:
        self._ensure_thread()
        self._commands.put(command)

    def hide(self) -> None:
        if self._thread and self._thread.is_alive():
            self._commands.put(None)

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name=self._thread_name, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=2.0):
            msg = "overlay thread failed to start"
            raise RuntimeError(msg)

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=TRANSPARENT_CHROMA)
        root.attributes("-transparentcolor", TRANSPARENT_CHROMA)
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.geometry(f"{screen_w}x{screen_h}+0+0")

        canvas = tk.Canvas(
            root,
            width=screen_w,
            height=screen_h,
            highlightthickness=0,
            bg=TRANSPARENT_CHROMA,
        )
        canvas.pack()
        label = tk.Label(root, text="", fg="white", bg="black")
        label.place(relx=0.5, y=24, anchor="n")

        apply_click_through_styles(root.winfo_id())
        self._ready.set()
        self._poll(root, canvas, label)
        root.mainloop()

    def _poll(self, root: tk.Tk, canvas: tk.Canvas, label_widget: tk.Label) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                break
            if command is None:
                root.quit()
                return
            self._render(canvas, label_widget, command)
        root.after(50, lambda: self._poll(root, canvas, label_widget))

    @abstractmethod
    def _render(self, canvas: tk.Canvas, label_widget: tk.Label, command: object) -> None: ...


class TkWin32IndicatorBackend:
    def __init__(self, *, diameter: int = 20) -> None:
        self._diameter = diameter
        self._commands: queue.Queue[IndicatorState | None] = queue.Queue()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="indicator-ui", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=2.0):
            msg = "indicator UI thread failed to start"
            raise RuntimeError(msg)

    def update(self, state: IndicatorState) -> None:
        self._commands.put(state)

    def stop(self) -> None:
        self._commands.put(None)
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=TRANSPARENT_CHROMA)
        root.attributes("-transparentcolor", TRANSPARENT_CHROMA)

        canvas = tk.Canvas(
            root,
            width=self._diameter,
            height=self._diameter,
            highlightthickness=0,
            bg=TRANSPARENT_CHROMA,
        )
        canvas.pack()

        apply_click_through_styles(root.winfo_id())
        self._ready.set()
        self._schedule_poll(root, canvas)
        root.mainloop()

    def _schedule_poll(self, root: tk.Tk, canvas: tk.Canvas) -> None:
        self._drain_commands(root, canvas)
        root.after(int(1000 / MIN_OVERLAY_FPS), lambda: self._schedule_poll(root, canvas))

    def _drain_commands(self, root: tk.Tk, canvas: tk.Canvas) -> None:
        while True:
            try:
                state = self._commands.get_nowait()
            except queue.Empty:
                break
            if state is None:
                root.quit()
                return
            self._render(root, canvas, state)

    def _render(self, root: tk.Tk, canvas: tk.Canvas, state: IndicatorState) -> None:
        diameter = max(state.diameter, 8)
        root.geometry(f"{diameter}x{diameter}{_window_origin(state.x, state.y, diameter)}")
        canvas.config(width=diameter, height=diameter)
        canvas.delete("all")
        if not state.visible:
            return
        padding = max(state.stroke_width, 1)
        canvas.create_oval(
            padding,
            padding,
            diameter - padding,
            diameter - padding,
            outline=state.stroke_color,
            fill=state.fill_color,
            width=state.stroke_width,
        )
        if state.scroll_chevron is not None:
            _draw_scroll_chevron(canvas, diameter, state.scroll_chevron, state.fill_color)


def _window_origin(x: float, y: float, diameter: int) -> str:
    left = int(round(x - diameter / 2))
    top = int(round(y - diameter / 2))
    return f"+{left}+{top}"


def _draw_scroll_chevron(
    canvas: tk.Canvas,
    diameter: int,
    direction: Literal["up", "down"],
    color: str,
) -> None:
    center = diameter / 2
    span = diameter * 0.22
    if direction == "up":
        points = (
            center,
            center - span,
            center - span,
            center + span * 0.45,
            center + span,
            center + span * 0.45,
        )
    else:
        points = (
            center,
            center + span,
            center - span,
            center - span * 0.45,
            center + span,
            center - span * 0.45,
        )
    canvas.create_polygon(*points, fill=color, outline=color)
