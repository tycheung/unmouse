"""Always-on-top click-through gaze indicator overlay."""

from __future__ import annotations

import queue
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from unmouse.state import SystemState

if TYPE_CHECKING:
    import tkinter as tk

MIN_INDICATOR_FPS = 30.0
DEFAULT_INDICATOR_DIAMETER = 20
DEFAULT_INDICATOR_COLOR = "#FFFFFF"
TRANSPARENT_CHROMA = "#FF00FF"
LUMINANCE_THRESHOLD = 0.55
DEFAULT_FALLBACK_LUMINANCE = 0.3
LIGHT_FILL = "#000000"
DARK_FILL = "#FFFFFF"
RIGHT_CLICK_FILL = "#FF0000"
THIN_STROKE = 2
BOLD_STROKE = 4
CLICK_MODE_SCALE = 1.2
LUMINANCE_PATCH_SIZE = 5

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
CLICK_THROUGH_STYLES = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW


@dataclass(frozen=True)
class IndicatorAppearance:
    click_mode: bool = False
    right_click: bool = False
    scroll_active: bool = False
    scroll_up: bool = True


@dataclass(frozen=True)
class IndicatorState:
    x: float
    y: float
    visible: bool = True
    fill_color: str = DEFAULT_INDICATOR_COLOR
    stroke_color: str = DEFAULT_INDICATOR_COLOR
    stroke_width: int = THIN_STROKE
    diameter: int = DEFAULT_INDICATOR_DIAMETER
    scroll_chevron: Literal["up", "down"] | None = None


class LuminanceSampler(Protocol):
    def sample(self, x: float, y: float) -> float: ...


@dataclass
class FakeLuminanceSampler:
    value: float = DEFAULT_FALLBACK_LUMINANCE

    def sample(self, x: float, y: float) -> float:
        return self.value


@dataclass
class MssLuminanceSampler:
    patch_size: int = LUMINANCE_PATCH_SIZE
    _sct: Any = field(default=None, init=False, repr=False)

    def sample(self, x: float, y: float) -> float:
        try:
            import mss
        except ImportError:
            return DEFAULT_FALLBACK_LUMINANCE

        if self._sct is None:
            self._sct = mss.mss()

        half = self.patch_size // 2
        left = int(round(x)) - half
        top = int(round(y)) - half
        region = {"left": left, "top": top, "width": self.patch_size, "height": self.patch_size}
        try:
            shot = self._sct.grab(region)
        except Exception:
            return DEFAULT_FALLBACK_LUMINANCE
        return average_luminance_from_bgra(shot.raw, shot.width, shot.height)


class IndicatorBackend(Protocol):
    def start(self) -> None: ...

    def update(self, state: IndicatorState) -> None: ...

    def stop(self) -> None: ...


@dataclass
class FakeIndicatorBackend:
    """Records indicator updates for tests."""

    updates: list[IndicatorState] = field(default_factory=list)
    active: bool = False

    def start(self) -> None:
        self.active = True

    def update(self, state: IndicatorState) -> None:
        self.updates.append(state)

    def stop(self) -> None:
        self.active = False


class GazeIndicatorOverlay:
    """Drive indicator rendering at a fixed minimum refresh rate."""

    def __init__(
        self,
        backend: IndicatorBackend | None = None,
        *,
        target_fps: float = MIN_INDICATOR_FPS,
        state_provider: Callable[[], IndicatorState] | None = None,
    ) -> None:
        if target_fps < MIN_INDICATOR_FPS:
            msg = f"target_fps must be at least {MIN_INDICATOR_FPS}"
            raise ValueError(msg)
        self._backend = backend or create_indicator_backend()
        self._interval_s = 1.0 / target_fps
        self._state_provider = state_provider or (lambda: IndicatorState(0.0, 0.0, visible=False))
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._backend.start()
        self._thread = threading.Thread(target=self._run, name="gaze-indicator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._backend.stop()

    def tick(self) -> None:
        self._backend.update(self._state_provider())

    def _run(self) -> None:
        while self._running:
            started = time.perf_counter()
            self.tick()
            elapsed = time.perf_counter() - started
            sleep_for = self._interval_s - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)


class TkWin32IndicatorBackend:
    def __init__(self, *, diameter: int = DEFAULT_INDICATOR_DIAMETER) -> None:
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

    def _schedule_poll(self, root: object, canvas: object) -> None:
        import tkinter as tk

        assert isinstance(root, tk.Tk)
        assert isinstance(canvas, tk.Canvas)
        self._drain_commands(root, canvas)
        root.after(int(1000 / MIN_INDICATOR_FPS), lambda: self._schedule_poll(root, canvas))

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


def relative_luminance(r: int, g: int, b: int) -> float:
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def average_luminance_from_bgra(raw: bytes, width: int, height: int) -> float:
    if not raw or width <= 0 or height <= 0:
        return DEFAULT_FALLBACK_LUMINANCE
    pixel_count = width * height
    total = 0.0
    for index in range(0, len(raw), 4):
        total += relative_luminance(raw[index + 2], raw[index + 1], raw[index])
    return total / pixel_count


def adaptive_fill_color(luminance: float, *, click_mode: bool, right_click: bool) -> str:
    if click_mode and right_click:
        return RIGHT_CLICK_FILL
    return LIGHT_FILL if luminance > LUMINANCE_THRESHOLD else DARK_FILL


def resolve_stroke_width(*, click_mode: bool, scroll_active: bool) -> int:
    if scroll_active:
        return THIN_STROKE
    return BOLD_STROKE if click_mode else THIN_STROKE


def resolve_diameter(base: int, *, click_mode: bool, scroll_active: bool) -> int:
    if click_mode and not scroll_active:
        return int(round(base * CLICK_MODE_SCALE))
    return base


def compose_indicator_state(
    x: float,
    y: float,
    *,
    appearance: IndicatorAppearance | None = None,
    sampler: LuminanceSampler | None = None,
    visible: bool = True,
    base_diameter: int = DEFAULT_INDICATOR_DIAMETER,
) -> IndicatorState:
    app = appearance or IndicatorAppearance()
    luminance = sampler.sample(x, y) if sampler is not None else DEFAULT_FALLBACK_LUMINANCE
    fill = adaptive_fill_color(luminance, click_mode=app.click_mode, right_click=app.right_click)
    stroke_width = resolve_stroke_width(
        click_mode=app.click_mode,
        scroll_active=app.scroll_active,
    )
    diameter = resolve_diameter(
        base_diameter,
        click_mode=app.click_mode,
        scroll_active=app.scroll_active,
    )
    chevron: Literal["up", "down"] | None = None
    if app.scroll_active:
        chevron = "up" if app.scroll_up else "down"
    return IndicatorState(
        x=x,
        y=y,
        visible=visible,
        fill_color=fill,
        stroke_color=fill,
        stroke_width=stroke_width,
        diameter=diameter,
        scroll_chevron=chevron,
    )


def indicator_state_from_system(
    system: SystemState,
    *,
    sampler: LuminanceSampler | None = None,
    scroll_up: bool | None = None,
    visible: bool = True,
) -> IndicatorState:
    gaze = system.get_gaze()
    direction_up = system.scroll_up if scroll_up is None else scroll_up
    return compose_indicator_state(
        gaze.x,
        gaze.y,
        appearance=IndicatorAppearance(
            click_mode=system.click_mode,
            right_click=system.right_click_intent,
            scroll_active=system.scroll_active,
            scroll_up=direction_up,
        ),
        sampler=sampler,
        visible=visible,
    )


def apply_click_through_styles(hwnd: int) -> None:
    if sys.platform != "win32":
        return

    import ctypes

    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | CLICK_THROUGH_STYLES)


def create_indicator_backend(*, prefer_win32: bool = True) -> IndicatorBackend:
    if prefer_win32 and sys.platform == "win32":
        return TkWin32IndicatorBackend()
    return FakeIndicatorBackend()


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
