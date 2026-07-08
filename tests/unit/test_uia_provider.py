"""Unit tests for Windows UIA snap provider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from unmouse.arbitrator.snap import SnapEngine
from unmouse.arbitrator.uia_provider import (
    NullUiaTreeReader,
    UiaControlRect,
    UiaSnapProvider,
    control_to_snap_target,
    create_uia_snap_provider,
)


def _control(
    *,
    automation_id: str = "ok",
    name: str = "OK",
    control_type: str = "ButtonControl",
    x: float = 100.0,
    y: float = 50.0,
    width: float = 80.0,
    height: float = 24.0,
) -> UiaControlRect:
    return UiaControlRect(
        automation_id=automation_id,
        name=name,
        control_type=control_type,
        x=x,
        y=y,
        width=width,
        height=height,
    )


def test_control_to_snap_target_uses_center_bounds() -> None:
    target = control_to_snap_target(_control())
    assert target is not None
    assert target.bounds.center == (140.0, 62.0)
    assert target.priority == 2


def test_control_to_snap_target_rejects_empty_rect() -> None:
    assert control_to_snap_target(_control(width=0.0)) is None


def test_uia_provider_maps_controls_to_snap_targets() -> None:
    reader = NullUiaTreeReader(
        (_control(), _control(automation_id="cancel", name="Cancel", x=220.0)),
    )
    provider = UiaSnapProvider(reader=reader, cache_interval_s=10.0)
    targets = provider.list_targets()
    assert len(targets) == 2
    assert targets[0].target_id == "ButtonControl:ok"


def test_uia_provider_caches_enumeration() -> None:
    reader = NullUiaTreeReader((_control(),))
    provider = UiaSnapProvider(reader=reader, cache_interval_s=10.0)
    provider.list_targets()
    provider.list_targets()
    assert reader.calls == 1


def test_uia_provider_gracefully_handles_reader_errors() -> None:
    reader = MagicMock()
    reader.enumerate_focusable.side_effect = RuntimeError("uia unavailable")
    provider = UiaSnapProvider(reader=reader, cache_interval_s=0.0)
    assert provider.list_targets() == ()


def test_uia_provider_snaps_gaze_to_mocked_button() -> None:
    reader = NullUiaTreeReader((_control(x=100.0, y=50.0, width=80.0, height=24.0),))
    provider = UiaSnapProvider(reader=reader, cache_interval_s=0.0)
    engine = SnapEngine(snap_radius_px=50.0)
    result = engine.snap(145.0, 60.0, provider.list_targets(), timestamp_s=0.0)
    assert result.snapped is True
    assert result.x == 140.0
    assert result.y == 62.0


def test_create_uia_snap_provider_falls_back_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("unmouse.arbitrator.uia_provider.sys.platform", "linux")
    provider = create_uia_snap_provider(prefer_uia=True)
    assert provider.list_targets() == ()
