from __future__ import annotations

from unmouse.arbitrator.snap import SnapEngine, SnapRect, SnapTarget, StaticSnapProvider
from unmouse.arbitrator.uia_provider import (
    NullUiaTreeReader,
    UiaControlRect,
    create_uia_snap_provider,
)
from unmouse.arbitrator.window_chrome import (
    NullWindowChromeReader,
    WindowRect,
    build_heuristic_chrome_buttons,
    chrome_buttons_to_snap_targets,
    create_snap_orchestrator,
    create_window_chrome_provider,
)


def _window() -> WindowRect:
    return WindowRect(left=100.0, top=50.0, right=1100.0, bottom=800.0)


def test_build_heuristic_chrome_buttons_aligns_right() -> None:
    buttons = build_heuristic_chrome_buttons(_window())
    assert [button.role for button in buttons] == ["close", "maximize", "minimize"]
    assert buttons[0].bounds.x == 1054.0
    assert buttons[1].bounds.x == 1008.0
    assert buttons[2].bounds.x == 962.0


def test_chrome_targets_use_high_priority() -> None:
    buttons = build_heuristic_chrome_buttons(_window())
    targets = chrome_buttons_to_snap_targets(buttons)
    assert all(target.priority == 10 for target in targets)
    assert targets[0].target_id == "chrome:close"


def test_window_chrome_provider_caches_buttons() -> None:
    buttons = build_heuristic_chrome_buttons(_window())
    reader = NullWindowChromeReader(buttons=buttons)
    provider = create_window_chrome_provider(
        reader=reader,
        cache_interval_s=10.0,
        prefer_win32=False,
    )
    provider.list_targets()
    provider.list_targets()
    assert reader.calls == 1


def test_chrome_snap_wins_over_uia_at_equal_distance() -> None:
    window = _window()
    chrome_buttons = build_heuristic_chrome_buttons(window)
    chrome_provider = create_window_chrome_provider(
        reader=NullWindowChromeReader(buttons=chrome_buttons),
        cache_interval_s=0.0,
        prefer_win32=False,
    )
    uia_control = UiaControlRect(
        automation_id="save",
        name="Save",
        control_type="ButtonControl",
        x=1042.0,
        y=50.0,
        width=46.0,
        height=32.0,
    )
    uia_provider = create_uia_snap_provider(
        reader=NullUiaTreeReader((uia_control,)),
        cache_interval_s=0.0,
        prefer_uia=False,
    )
    orchestrator = create_snap_orchestrator(
        chrome_provider=chrome_provider,
        extra_providers=(uia_provider,),
    )
    engine = SnapEngine(snap_radius_px=80.0)
    result = engine.snap(1077.0, 66.0, orchestrator.list_targets(), timestamp_s=0.0)
    assert result.snapped is True
    assert result.target_id == "chrome:close"


def test_create_window_chrome_provider_off_windows(monkeypatch) -> None:
    monkeypatch.setattr("unmouse.arbitrator.window_chrome.is_windows", lambda: False)
    provider = create_window_chrome_provider(prefer_win32=True)
    assert provider.list_targets() == ()


def test_static_uia_target_has_lower_priority_than_chrome() -> None:
    chrome = SnapTarget(
        target_id="chrome:close",
        bounds=SnapRect(1054.0, 50.0, 46.0, 32.0),
        priority=10,
    )
    uia = SnapTarget(
        target_id="ButtonControl:save",
        bounds=SnapRect(1054.0, 50.0, 46.0, 32.0),
        priority=2,
    )
    orchestrator = create_snap_orchestrator(
        chrome_provider=StaticSnapProvider((chrome,)),
        extra_providers=(StaticSnapProvider((uia,)),),
    )
    engine = SnapEngine(snap_radius_px=80.0)
    result = engine.snap(1077.0, 66.0, orchestrator.list_targets(), timestamp_s=0.0)
    assert result.target_id == "chrome:close"
