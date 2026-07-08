"""Unit tests for gaze indicator overlay."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from unmouse.overlay.indicator import (
    BOLD_STROKE,
    DARK_FILL,
    LIGHT_FILL,
    RIGHT_CLICK_FILL,
    THIN_STROKE,
    NoopIndicatorBackend,
    NoopLuminanceSampler,
    GazeIndicatorOverlay,
    IndicatorAppearance,
    IndicatorState,
    adaptive_fill_color,
    average_luminance_from_bgra,
    compose_indicator_state,
    create_indicator_backend,
    indicator_state_from_system,
    relative_luminance,
)
from unmouse.overlay.tk_overlay import (
    CLICK_THROUGH_STYLES,
    _window_origin,
    apply_click_through_styles,
)
from unmouse.state import SystemState


def test_fake_backend_records_updates() -> None:
    backend = NoopIndicatorBackend()
    state = IndicatorState(x=100.0, y=200.0)
    backend.start()
    backend.update(state)
    backend.stop()
    assert backend.updates == [state]
    assert backend.active is False


def test_overlay_tick_updates_backend() -> None:
    backend = NoopIndicatorBackend()
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
    monkeypatch.setattr("unmouse.overlay.tk_overlay.sys.platform", "win32")
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
    assert isinstance(backend, NoopIndicatorBackend)


def test_window_origin_centers_indicator() -> None:
    assert _window_origin(100.0, 50.0, 20) == "+90+40"


def test_relative_luminance_white_is_one() -> None:
    assert relative_luminance(255, 255, 255) == pytest.approx(1.0)


def test_adaptive_fill_flips_on_luminance() -> None:
    assert adaptive_fill_color(0.2, click_mode=False, right_click=False) == DARK_FILL
    assert adaptive_fill_color(0.8, click_mode=False, right_click=False) == LIGHT_FILL


def test_right_click_overrides_adaptive_fill() -> None:
    color = adaptive_fill_color(0.2, click_mode=True, right_click=True)
    assert color == RIGHT_CLICK_FILL


def test_compose_click_mode_boldens_indicator() -> None:
    state = compose_indicator_state(
        10.0,
        20.0,
        appearance=IndicatorAppearance(click_mode=True),
        sampler=NoopLuminanceSampler(0.2),
    )
    assert state.stroke_width == BOLD_STROKE
    assert state.diameter > 20
    assert state.fill_color == DARK_FILL


def test_compose_scroll_mode_adds_chevron() -> None:
    state = compose_indicator_state(
        0.0,
        0.0,
        appearance=IndicatorAppearance(scroll_active=True, scroll_up=False),
        sampler=NoopLuminanceSampler(0.8),
    )
    assert state.stroke_width == THIN_STROKE
    assert state.scroll_chevron == "down"


def test_average_luminance_from_bgra() -> None:
    raw = bytes([255, 255, 255, 255]) * 4
    assert average_luminance_from_bgra(raw, 2, 2) == pytest.approx(1.0)


def test_indicator_state_from_system() -> None:
    system = SystemState(gaze_x=50.0, gaze_y=60.0, click_mode=True, right_click_intent=True)
    state = indicator_state_from_system(system, sampler=NoopLuminanceSampler(0.2))
    assert state.x == 50.0
    assert state.fill_color == RIGHT_CLICK_FILL


def test_gaze_indicator_overlay_background_loop() -> None:
    backend = NoopIndicatorBackend()
    overlay = GazeIndicatorOverlay(
        backend=backend,
        target_fps=30.0,
        state_provider=lambda: IndicatorState(x=1.0, y=2.0),
    )
    overlay.start()
    deadline = time.time() + 1.0
    while time.time() < deadline and not backend.updates:
        time.sleep(0.01)
    overlay.stop()
    assert backend.updates
