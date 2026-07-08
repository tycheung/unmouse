from __future__ import annotations

from unmouse.arbitrator.snap import (
    CachedSnapProvider,
    CompositeSnapOrchestrator,
    SnapEngine,
    SnapRect,
    SnapTarget,
    StaticSnapProvider,
    nearest_snap_target,
)


def _button(target_id: str, x: float, y: float, size: float = 40.0) -> SnapTarget:
    return SnapTarget(target_id=target_id, bounds=SnapRect(x=x, y=y, width=size, height=size))


def test_nearest_snap_target_picks_closest_center() -> None:
    targets = (
        _button("close", 100.0, 20.0),
        _button("minimize", 200.0, 20.0),
    )
    match = nearest_snap_target(118.0, 35.0, targets, snap_radius_px=50.0)
    assert match is not None
    target, distance = match
    assert target.target_id == "close"
    assert distance < 20.0


def test_nearest_snap_target_returns_none_outside_radius() -> None:
    targets = (_button("close", 100.0, 20.0),)
    assert nearest_snap_target(300.0, 300.0, targets, snap_radius_px=50.0) is None


def test_snap_engine_snaps_to_target_center() -> None:
    engine = SnapEngine(snap_radius_px=50.0)
    targets = (_button("close", 100.0, 20.0),)
    result = engine.snap(118.0, 35.0, targets, timestamp_s=0.0)
    assert result.snapped is True
    assert result.target_id == "close"
    assert result.x == 120.0
    assert result.y == 40.0


def test_snap_engine_holds_sticky_target_inside_release_radius() -> None:
    engine = SnapEngine(snap_radius_px=50.0, release_radius_px=20.0, sticky_dwell_s=0.0)
    targets = (_button("close", 100.0, 20.0),)
    engine.snap(118.0, 35.0, targets, timestamp_s=0.0)
    result = engine.snap(130.0, 45.0, targets, timestamp_s=0.5)
    assert result.snapped is True
    assert result.target_id == "close"
    assert result.x == 120.0
    assert result.y == 40.0


def test_snap_engine_releases_sticky_target_after_exit_and_dwell() -> None:
    engine = SnapEngine(snap_radius_px=50.0, release_radius_px=15.0, sticky_dwell_s=0.1)
    targets = (_button("close", 100.0, 20.0),)
    engine.snap(118.0, 35.0, targets, timestamp_s=0.0)
    released = engine.snap(200.0, 200.0, targets, timestamp_s=0.5)
    assert released.snapped is False
    assert released.target_id is None
    assert released.x == 200.0
    assert released.y == 200.0


def test_composite_orchestrator_merges_provider_targets() -> None:
    provider_a = StaticSnapProvider((_button("a", 10.0, 10.0),))
    provider_b = StaticSnapProvider((_button("b", 50.0, 10.0),))
    orchestrator = CompositeSnapOrchestrator([provider_a, provider_b])
    assert len(orchestrator.list_targets()) == 2


def test_cached_snap_provider_clears_targets_on_load_error() -> None:
    def failing_loader() -> tuple[SnapTarget, ...]:
        raise OSError("snap source unavailable")

    provider = CachedSnapProvider(loader=failing_loader, cache_interval_s=0.0)
    assert provider.list_targets() == ()
    assert provider.refresh() == ()
