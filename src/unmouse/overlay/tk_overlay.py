"""Shared Tk fullscreen transparent overlay thread."""

from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from unmouse.overlay.indicator import TRANSPARENT_CHROMA, apply_click_through_styles

if TYPE_CHECKING:
    import tkinter as tk


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
