"""Unit tests for launcher tray backend."""

from __future__ import annotations

from unmouse.launcher.tray import (
    FakeTrayBackend,
    TrayHandlers,
    create_tray_backend,
    create_tray_icon_image,
)


def test_fake_tray_lifecycle() -> None:
    calls: list[str] = []
    handlers = TrayHandlers(
        on_show=lambda: calls.append("show"),
        on_stop=lambda: calls.append("stop"),
        on_quit=lambda: calls.append("quit"),
    )
    tray = FakeTrayBackend(handlers)
    tray.ensure_running()
    handlers.on_show()
    handlers.on_stop()
    assert tray.running is True
    tray.stop()
    assert tray.running is False


def test_create_tray_backend_uses_fake_when_disabled() -> None:
    handlers = TrayHandlers(on_show=lambda: None, on_stop=lambda: None, on_quit=lambda: None)
    assert isinstance(create_tray_backend(handlers, prefer_pystray=False), FakeTrayBackend)


def test_fake_tray_notify_records_message() -> None:
    handlers = TrayHandlers(on_show=lambda: None, on_stop=lambda: None, on_quit=lambda: None)
    tray = FakeTrayBackend(handlers)
    tray.notify("Engine crashed", title="unmouse")
    assert tray.notifications == ["Engine crashed"]


def test_create_tray_icon_image_returns_pil_image() -> None:
    assert create_tray_icon_image().size == (64, 64)
