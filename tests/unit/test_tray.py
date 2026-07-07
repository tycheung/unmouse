"""Unit tests for launcher tray backend."""

from __future__ import annotations

from unmouse.launcher.tray import FakeTrayBackend, create_tray_backend, create_tray_icon_image


def test_fake_tray_records_actions() -> None:
    calls: list[str] = []
    tray = FakeTrayBackend(
        on_show=lambda: calls.append("show"),
        on_stop=lambda: calls.append("stop"),
        on_quit=lambda: calls.append("quit"),
    )
    tray.ensure_running()
    tray.trigger_show()
    tray.trigger_stop()
    tray.trigger_quit()
    assert tray.running is True
    assert calls == ["show", "stop", "quit"]
    tray.stop()
    assert tray.running is False


def test_create_tray_backend_uses_fake_when_disabled() -> None:
    tray = create_tray_backend(
        on_show=lambda: None,
        on_stop=lambda: None,
        on_quit=lambda: None,
        prefer_pystray=False,
    )
    assert isinstance(tray, FakeTrayBackend)


def test_create_tray_icon_image_returns_pil_image() -> None:
    image = create_tray_icon_image()
    assert image.size == (64, 64)
