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
        return cls(left=0, top=0, width=settings.screen_width, height=settings.screen_height)

    def clip(self, x: float, y: float) -> tuple[float, float]:
        max_x = float(self.left + self.width - 1)
        max_y = float(self.top + self.height - 1)
        return (
            max(float(self.left), min(x, max_x)),
            max(float(self.top), min(y, max_y)),
        )
