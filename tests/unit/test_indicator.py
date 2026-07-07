"""Unit tests for gaze indicator overlay."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from unmouse.overlay.indicator import (
    CLICK_THROUGH_STYLES,
    FakeIndicatorBackend,
    GazeIndicatorOverlay,
    IndicatorState,
    _window_origin,
    apply_click_through_styles,
    create_indicator_backend,
)


def test_fake_backend_records_updates() -> None:
    backend = FakeIndicatorBackend()
    state = IndicatorState(x=100.0, y=200.0)
    backend.start()
    backend.update(state)
    backend.stop()
    assert backend.updates == [state]
    assert backend.active is False


def test_overlay_tick_updates_backend() -> None:
    backend = FakeIndicatorBackend()
    provider_calls = 0

    def provider() -> IndicatorState:
        nonlocal provider_calls
        provider_calls += 1
        return IndicatorState(x=10.0, y=20.0)

    overlay = GazeIndicatorOverlay(backend=backend, target_fps=30.0, state_provider=provider)
    overlay.tick()
    assert provider_calls == 1
    assert backend.updates[-1].x == 10.0


def test_overlay_rejects_fps_below_minimum() -> None:
    with pytest.raises(ValueError, match="target_fps"):
        GazeIndicatorOverlay(target_fps=20.0)


def test_apply_click_through_styles_sets_win32_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("unmouse.overlay.indicator.sys.platform", "win32")
    recorded: list[int] = []

    fake_user32 = MagicMock()
    fake_user32.GetWindowLongW.return_value = 0
    fake_user32.SetWindowLongW = lambda _hwnd, _index, value: recorded.append(value)

    fake_windll = MagicMock()
    fake_windll.user32 = fake_user32
    monkeypatch.setattr("ctypes.windll", fake_windll, raising=False)

    apply_click_through_styles(12345)
    assert recorded
    assert recorded[0] & CLICK_THROUGH_STYLES == CLICK_THROUGH_STYLES


def test_create_indicator_backend_uses_fake_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("unmouse.overlay.indicator.sys.platform", "linux")
    backend = create_indicator_backend(prefer_win32=True)
    assert isinstance(backend, FakeIndicatorBackend)


def test_window_origin_centers_indicator() -> None:
    assert _window_origin(100.0, 50.0, 20) == "+90+40"
