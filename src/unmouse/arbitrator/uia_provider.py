"""Windows UI Automation provider for gaze snap targets."""

from __future__ import annotations

import importlib.util
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from unmouse.arbitrator.snap import SnapProvider, SnapRect, SnapTarget

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
class MockUiaTreeReader:
    controls: tuple[UiaControlRect, ...]
    calls: int = field(default=0, init=False)

    def enumerate_focusable(self) -> tuple[UiaControlRect, ...]:
        self.calls += 1
        return self.controls


class UiaAutomationTreeReader:
    """Enumerate focusable controls from the foreground window via uiautomation."""

    def __init__(self, *, max_depth: int = 8) -> None:
        self._max_depth = max_depth

    def enumerate_focusable(self) -> tuple[UiaControlRect, ...]:
        if sys.platform != "win32":
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


class UiaSnapProvider:
    """SnapProvider that caches UIA focusable control bounds."""

    def __init__(
        self,
        reader: UiaTreeReader | None = None,
        *,
        cache_interval_s: float = DEFAULT_UIA_CACHE_INTERVAL_S,
    ) -> None:
        self._reader = reader or UiaAutomationTreeReader()
        self._cache_interval_s = cache_interval_s
        self._cached_targets: tuple[SnapTarget, ...] = ()
        self._cached_at = -float("inf")

    def list_targets(self) -> tuple[SnapTarget, ...]:
        now = time.monotonic()
        if now - self._cached_at >= self._cache_interval_s:
            self._refresh(now)
        return self._cached_targets

    def refresh(self) -> tuple[SnapTarget, ...]:
        self._refresh(time.monotonic())
        return self._cached_targets

    def _refresh(self, now: float) -> None:
        try:
            controls = self._reader.enumerate_focusable()
            self._cached_targets = tuple(
                target
                for control in controls
                if (target := control_to_snap_target(control)) is not None
            )
        except OSError:
            self._cached_targets = ()
        except RuntimeError:
            self._cached_targets = ()
        self._cached_at = now


def create_uia_snap_provider(
    *,
    cache_interval_s: float = DEFAULT_UIA_CACHE_INTERVAL_S,
    prefer_uia: bool = True,
) -> SnapProvider:
    if prefer_uia and sys.platform == "win32":
        if importlib.util.find_spec("uiautomation") is None:
            return UiaSnapProvider(reader=_EmptyUiaTreeReader(), cache_interval_s=cache_interval_s)
        return UiaSnapProvider(cache_interval_s=cache_interval_s)
    return UiaSnapProvider(reader=_EmptyUiaTreeReader(), cache_interval_s=cache_interval_s)


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


@dataclass
class _EmptyUiaTreeReader:
    def enumerate_focusable(self) -> tuple[UiaControlRect, ...]:
        return ()


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
