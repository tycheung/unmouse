from __future__ import annotations

from dataclasses import dataclass, field

from unmouse.arbitrator.actions import ClickButton
from unmouse.arbitrator.snap import SnapTarget


@dataclass
class NoopActionDriver:
    moves: list[tuple[int, int]] = field(default_factory=list)
    clicks: list[tuple[int, int, ClickButton]] = field(default_factory=list)
    scrolls: list[tuple[int, int, int]] = field(default_factory=list)

    def move_to(self, x: float, y: float) -> None:
        self.moves.append((int(round(x)), int(round(y))))

    def click(self, x: float, y: float, button: ClickButton = "left") -> None:
        self.clicks.append((int(round(x)), int(round(y)), button))

    def scroll(self, x: float, y: float, delta: float) -> None:
        clicks = int(round(delta))
        if clicks == 0:
            return
        self.scrolls.append((int(round(x)), int(round(y)), clicks))

    def clear(self) -> None:
        self.moves.clear()
        self.clicks.clear()
        self.scrolls.clear()


@dataclass
class StaticSnapProvider:
    targets: tuple[SnapTarget, ...]

    def list_targets(self) -> tuple[SnapTarget, ...]:
        return self.targets
