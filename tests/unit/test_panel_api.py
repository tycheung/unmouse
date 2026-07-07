"""Unit tests for control panel Python bridge."""

from __future__ import annotations

from unmouse.config import Settings
from unmouse.launcher.api import PanelApi


def test_panel_api_default_status() -> None:
    api = PanelApi(settings=Settings(screen_width=800, screen_height=600))
    status = api.get_status()
    assert status["message"] == "Ready"
    assert status["tracking"] is False


def test_panel_api_update_check_stub() -> None:
    api = PanelApi()
    result = api.check_for_updates()
    assert result["available"] is False
    assert "not configured" in str(result["message"]).lower()


def test_panel_api_calibrate_and_launch_stubs() -> None:
    api = PanelApi()
    calibrate = api.start_calibrate()
    launch = api.start_launch()
    assert calibrate["ok"] is False
    assert launch["ok"] is False


def test_panel_api_view_navigation() -> None:
    api = PanelApi()
    assert api.get_view()["view"] == "main"
    assert api.show_settings()["view"] == "settings"
    assert api.get_view()["view"] == "settings"
    assert api.show_onboarding()["view"] == "onboarding"
    assert api.show_main()["view"] == "main"


def test_panel_api_set_status_message() -> None:
    api = PanelApi()
    updated = api.set_status_message("Calibrating")
    assert updated["message"] == "Calibrating"
    assert api.get_status()["message"] == "Calibrating"
