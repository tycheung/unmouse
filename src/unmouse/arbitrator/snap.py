from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_STICKY_DWELL_S = 0.2
DEFAULT_RELEASE_RADIUS_RATIO = 0.6


@dataclass(frozen=True)
class SnapRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2.0, self.y + self.height / 2.0


@dataclass(frozen=True)
class SnapTarget:
    target_id: str
    bounds: SnapRect
    priority: int = 0


@dataclass(frozen=True)
class SnapResult:
    x: float
    y: float
    snapped: bool
    target_id: str | None


class SnapProvider(Protocol):
    def list_targets(self) -> tuple[SnapTarget, ...]: ...


@dataclass
class CachedSnapProvider:
    loader: Callable[[], tuple[SnapTarget, ...]]
    cache_interval_s: float
    _cached_targets: tuple[SnapTarget, ...] = field(default=(), init=False)
    _cached_at: float = field(default=-float("inf"), init=False)

    def list_targets(self) -> tuple[SnapTarget, ...]:
        now = time.monotonic()
        if now - self._cached_at >= self.cache_interval_s:
            self._refresh(now)
        return self._cached_targets

    def _refresh(self, now: float) -> None:
        try:
            self._cached_targets = self.loader()
        except OSError:
            self._cached_targets = ()
        except RuntimeError:
            self._cached_targets = ()
        self._cached_at = now


@dataclass
class StaticSnapProvider:
    targets: tuple[SnapTarget, ...]

    def list_targets(self) -> tuple[SnapTarget, ...]:
        return self.targets


class CompositeSnapOrchestrator:
    def __init__(self, providers: Sequence[SnapProvider]) -> None:
        self._providers = tuple(providers)

    def list_targets(self) -> tuple[SnapTarget, ...]:
        merged: list[SnapTarget] = []
        for provider in self._providers:
            merged.extend(provider.list_targets())
        return tuple(merged)


class SnapEngine:
    def __init__(
        self,
        *,
        snap_radius_px: float,
        release_radius_px: float | None = None,
        sticky_dwell_s: float = DEFAULT_STICKY_DWELL_S,
    ) -> None:
        if snap_radius_px <= 0:
            msg = "snap_radius_px must be positive"
            raise ValueError(msg)
        self._snap_radius_px = snap_radius_px
        self._release_radius_px = release_radius_px or snap_radius_px * DEFAULT_RELEASE_RADIUS_RATIO
        self._sticky_dwell_s = sticky_dwell_s
        self._active_target_id: str | None = None
        self._active_center: tuple[float, float] | None = None
        self._snapped_at: float | None = None

    def reset(self) -> None:
        self._active_target_id = None
        self._active_center = None
        self._snapped_at = None

    def snap(
        self,
        gaze_x: float,
        gaze_y: float,
        targets: Sequence[SnapTarget],
        *,
        timestamp_s: float,
    ) -> SnapResult:
        sticky = self._maybe_keep_sticky(gaze_x, gaze_y, timestamp_s)
        if sticky is not None:
            return sticky

        match = nearest_snap_target(gaze_x, gaze_y, targets, self._snap_radius_px)
        if match is None:
            self.reset()
            return SnapResult(x=gaze_x, y=gaze_y, snapped=False, target_id=None)

        target, _distance = match
        center_x, center_y = target.bounds.center
        self._active_target_id = target.target_id
        self._active_center = (center_x, center_y)
        self._snapped_at = timestamp_s
        return SnapResult(x=center_x, y=center_y, snapped=True, target_id=target.target_id)

    def _maybe_keep_sticky(
        self,
        gaze_x: float,
        gaze_y: float,
        timestamp_s: float,
    ) -> SnapResult | None:
        if self._active_target_id is None or self._active_center is None:
            return None

        center_x, center_y = self._active_center
        distance = math.hypot(gaze_x - center_x, gaze_y - center_y)
        within_release = distance <= self._release_radius_px
        within_dwell = (
            self._snapped_at is not None
            and timestamp_s - self._snapped_at <= self._sticky_dwell_s
        )
        if within_release or within_dwell:
            return SnapResult(
                x=center_x,
                y=center_y,
                snapped=True,
                target_id=self._active_target_id,
            )
        self.reset()
        return None


def nearest_snap_target(
    gaze_x: float,
    gaze_y: float,
    targets: Sequence[SnapTarget],
    snap_radius_px: float,
) -> tuple[SnapTarget, float] | None:
    best: SnapTarget | None = None
    best_distance = float("inf")
    for target in targets:
        center_x, center_y = target.bounds.center
        distance = math.hypot(gaze_x - center_x, gaze_y - center_y)
        if distance > snap_radius_px:
            continue
        if distance < best_distance or (
            math.isclose(distance, best_distance)
            and target.priority > (best.priority if best else -1)
        ):
            best = target
            best_distance = distance
    if best is None:
        return None
    return best, best_distance
