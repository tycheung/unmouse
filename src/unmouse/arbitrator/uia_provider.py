from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from unmouse.arbitrator.snap import CachedSnapProvider, SnapProvider, SnapRect, SnapTarget
from unmouse.platform import is_windows
from unmouse.utils.backend_selection import prefer_or_fallback

DEFAULT_UIA_CACHE_INTERVAL_S = 0.5
FOCUSABLE_CONTROL_TYPES = frozenset(
    {
        "ButtonControl",
        "CheckBoxControl",
        "ComboBoxControl",
        "EditControl",
        "HyperlinkControl",
        "ListItemControl",
        "MenuItemControl",
        "RadioButtonControl",
        "SplitButtonControl",
        "TabItemControl",
    }
)


@dataclass(frozen=True)
class UiaControlRect:
    automation_id: str
    name: str
    control_type: str
    x: float
    y: float
    width: float
    height: float


class UiaTreeReader(Protocol):
    def enumerate_focusable(self) -> tuple[UiaControlRect, ...]: ...


@dataclass
class NullUiaTreeReader:
    controls: tuple[UiaControlRect, ...] = ()
    calls: int = field(default=0, init=False)

    def enumerate_focusable(self) -> tuple[UiaControlRect, ...]:
        self.calls += 1
        return self.controls


class UiaAutomationTreeReader:
    def __init__(self, *, max_depth: int = 8) -> None:
        self._max_depth = max_depth

    def enumerate_focusable(self) -> tuple[UiaControlRect, ...]:
        if not is_windows():
            return ()

        import uiautomation as auto

        window = auto.GetForegroundControl()
        if window is None:
            return ()

        controls: list[UiaControlRect] = []
        for control, _depth in auto.WalkControl(window, includeTop=False, maxDepth=self._max_depth):
            parsed = _control_rect(control)
            if parsed is not None:
                controls.append(parsed)
        return tuple(controls)


def create_uia_snap_provider(
    *,
    cache_interval_s: float = DEFAULT_UIA_CACHE_INTERVAL_S,
    prefer_uia: bool = True,
    reader: UiaTreeReader | None = None,
) -> SnapProvider:
    resolved_reader = reader or prefer_or_fallback(
        prefer=prefer_uia
        and is_windows()
        and importlib.util.find_spec("uiautomation") is not None,
        make_preferred=lambda: cast(UiaTreeReader, UiaAutomationTreeReader()),
        make_fallback=lambda: cast(UiaTreeReader, NullUiaTreeReader()),
        exceptions=None,
    )

    def loader() -> tuple[SnapTarget, ...]:
        controls = resolved_reader.enumerate_focusable()
        return tuple(
            target
            for control in controls
            if (target := control_to_snap_target(control)) is not None
        )

    return CachedSnapProvider(loader=loader, cache_interval_s=cache_interval_s)


def control_to_snap_target(control: UiaControlRect) -> SnapTarget | None:
    if control.width <= 0 or control.height <= 0:
        return None
    target_id = _target_id(control)
    return SnapTarget(
        target_id=target_id,
        bounds=SnapRect(
            x=control.x,
            y=control.y,
            width=control.width,
            height=control.height,
        ),
        priority=_priority_for_control_type(control.control_type),
    )


def _control_rect(control: Any) -> UiaControlRect | None:
    if not _is_focusable_control(control):
        return None
    rectangle = control.BoundingRectangle
    width = float(rectangle.width())
    height = float(rectangle.height())
    if width <= 0 or height <= 0:
        return None
    return UiaControlRect(
        automation_id=str(getattr(control, "AutomationId", "") or ""),
        name=str(getattr(control, "Name", "") or ""),
        control_type=str(getattr(control, "ControlTypeName", "") or ""),
        x=float(rectangle.left),
        y=float(rectangle.top),
        width=width,
        height=height,
    )


def _is_focusable_control(control: Any) -> bool:
    control_type = str(getattr(control, "ControlTypeName", "") or "")
    if control_type not in FOCUSABLE_CONTROL_TYPES:
        return False
    if not bool(getattr(control, "IsEnabled", True)):
        return False
    return not bool(getattr(control, "IsOffscreen", False))


def _priority_for_control_type(control_type: str) -> int:
    if control_type == "ButtonControl":
        return 2
    if control_type in {"EditControl", "HyperlinkControl"}:
        return 1
    return 0


def _target_id(control: UiaControlRect) -> str:
    suffix = control.automation_id or control.name or "unnamed"
    return f"{control.control_type}:{suffix}"
