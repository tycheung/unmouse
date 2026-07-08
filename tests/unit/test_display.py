from unittest.mock import patch

from unmouse.config import Settings
from unmouse.gaze.display import VirtualDesktop


def test_clip_within_virtual_desktop_bounds() -> None:
    desktop = VirtualDesktop(left=0, top=0, width=3200, height=1080)
    x, y = desktop.clip(4000.0, -10.0)
    assert x == 3199.0
    assert y == 0.0


def test_from_settings_uses_screen_dimensions() -> None:
    with patch("unmouse.gaze.display.detect_primary_monitor_size", return_value=None):
        desktop = VirtualDesktop.from_settings(Settings(screen_width=800, screen_height=600))
    assert (desktop.left, desktop.top, desktop.width, desktop.height) == (0, 0, 800, 600)


def test_from_settings_detects_primary_monitor() -> None:
    with patch("unmouse.gaze.display.detect_primary_monitor_size", return_value=(2560, 1440)):
        desktop = VirtualDesktop.from_settings(Settings(screen_width=800, screen_height=600))
    assert (desktop.width, desktop.height) == (2560, 1440)


def test_clip_leaves_in_bounds_point_unchanged() -> None:
    with patch("unmouse.gaze.display.detect_primary_monitor_size", return_value=None):
        desktop = VirtualDesktop.from_settings(Settings(screen_width=800, screen_height=600))
    assert desktop.clip(450.0, 275.0) == (450.0, 275.0)
