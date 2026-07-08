from __future__ import annotations

from dataclasses import dataclass

from unmouse.config import Settings


@dataclass(frozen=True)
class VirtualDesktop:
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_settings(cls, settings: Settings) -> VirtualDesktop:
        detected = detect_primary_monitor_size()
        if detected is not None:
            width, height = detected
        else:
            width, height = settings.screen_width, settings.screen_height
        return cls(left=0, top=0, width=width, height=height)

    def clip(self, x: float, y: float) -> tuple[float, float]:
        max_x = float(self.left + self.width - 1)
        max_y = float(self.top + self.height - 1)
        return (
            max(float(self.left), min(x, max_x)),
            max(float(self.top), min(y, max_y)),
        )


def detect_primary_monitor_size() -> tuple[int, int] | None:
    try:
        import pyautogui  # type: ignore[import-untyped]

        size = pyautogui.size()
        return int(size.width), int(size.height)
    except Exception:
        return None
