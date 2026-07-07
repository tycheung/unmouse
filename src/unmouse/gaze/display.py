"""Multi-monitor virtual desktop mapping and coordinate clipping."""

from __future__ import annotations

from dataclasses import dataclass

from unmouse.config import Settings


@dataclass(frozen=True)
class MonitorInfo:
    x: int
    y: int
    width: int
    height: int
    dpi_scale: float = 1.0

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class VirtualDesktop:
    monitors: tuple[MonitorInfo, ...]
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_settings(cls, settings: Settings) -> VirtualDesktop:
        monitor = MonitorInfo(
            x=0,
            y=0,
            width=settings.screen_width,
            height=settings.screen_height,
            dpi_scale=1.0,
        )
        return cls(
            monitors=(monitor,),
            left=0,
            top=0,
            width=settings.screen_width,
            height=settings.screen_height,
        )


def probe_virtual_desktop(settings: Settings) -> VirtualDesktop:
    try:
        import mss
    except ImportError:
        return VirtualDesktop.from_settings(settings)

    with mss.mss() as sct:
        monitors = sct.monitors
        if len(monitors) <= 1:
            return VirtualDesktop.from_settings(settings)
        parsed = tuple(
            MonitorInfo(
                x=int(mon["left"]),
                y=int(mon["top"]),
                width=int(mon["width"]),
                height=int(mon["height"]),
                dpi_scale=_estimate_dpi_scale(int(mon["width"]), settings),
            )
            for mon in monitors[1:]
        )
        bounds = monitors[0]
        return VirtualDesktop(
            monitors=parsed,
            left=int(bounds["left"]),
            top=int(bounds["top"]),
            width=int(bounds["width"]),
            height=int(bounds["height"]),
        )


def _estimate_dpi_scale(monitor_width: int, settings: Settings) -> float:
    if monitor_width <= 0 or settings.screen_width <= 0:
        return 1.0
    return max(1.0, settings.screen_width / monitor_width)


class DisplayMapper:
    def __init__(self, desktop: VirtualDesktop) -> None:
        self._desktop = desktop

    @property
    def desktop(self) -> VirtualDesktop:
        return self._desktop

    def clip(self, x: float, y: float) -> tuple[float, float]:
        min_x = float(self._desktop.left)
        min_y = float(self._desktop.top)
        max_x = float(self._desktop.left + self._desktop.width - 1)
        max_y = float(self._desktop.top + self._desktop.height - 1)
        return max(min_x, min(x, max_x)), max(min_y, min(y, max_y))

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        clipped_x, clipped_y = self.clip(x, y)
        monitor = self._monitor_for(clipped_x, clipped_y)
        if monitor is None or monitor.dpi_scale == 1.0:
            return clipped_x, clipped_y
        origin_x = float(monitor.x)
        origin_y = float(monitor.y)
        local_x = (clipped_x - origin_x) * monitor.dpi_scale
        local_y = (clipped_y - origin_y) * monitor.dpi_scale
        return origin_x + local_x, origin_y + local_y

    def _monitor_for(self, x: float, y: float) -> MonitorInfo | None:
        for monitor in self._desktop.monitors:
            if monitor.x <= x < monitor.right and monitor.y <= y < monitor.bottom:
                return monitor
        return self._desktop.monitors[0] if self._desktop.monitors else None
