"""Playwright end-to-end tests for the control panel shell."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_main_panel_buttons_visible(panel_page: Page) -> None:
    expect(panel_page.get_by_role("button", name="Launch")).to_be_visible()
    expect(panel_page.get_by_role("button", name="Settings")).to_be_visible()
    expect(panel_page.get_by_role("button", name="Calibrate")).to_be_visible()
    expect(panel_page.get_by_role("button", name="Train Gestures")).to_be_visible()
    expect(panel_page.get_by_role("button", name="Update Software")).to_be_visible()
    expect(panel_page.locator(".status-pill")).to_have_text("Idle")


def test_settings_save_and_return(panel_page: Page) -> None:
    panel_page.get_by_role("button", name="Settings").click()
    expect(panel_page.get_by_role("heading", name="Settings")).to_be_visible()

    slider = panel_page.locator('input[type="range"]').first
    slider.fill("25")
    panel_page.get_by_role("button", name="Save").click()
    expect(panel_page.locator(".message")).to_contain_text("Settings saved")

    panel_page.get_by_role("button", name="← Back").click()
    expect(panel_page.get_by_role("button", name="Launch")).to_be_visible()


def test_create_profile(panel_page: Page) -> None:
    panel_page.get_by_role("button", name="Settings").click()
    panel_page.get_by_placeholder("New profile").fill("lab")
    panel_page.get_by_role("button", name="Create").click()
    expect(panel_page.locator(".message")).not_to_have_text("")
    expect(panel_page.locator("select option")).to_contain_text(["lab"])


def test_launch_and_stop_tracking(panel_page: Page) -> None:
    panel_page.get_by_role("button", name="Launch").click()
    expect(panel_page.get_by_role("button", name="Stop Tracking")).to_be_visible()
    expect(panel_page.locator(".status-pill")).to_have_text("Tracking")
    expect(panel_page.get_by_role("button", name="Pause / Resume")).to_be_enabled()

    panel_page.get_by_role("button", name="Stop Tracking").click()
    expect(panel_page.get_by_role("button", name="Launch")).to_be_visible()
    expect(panel_page.locator(".status-pill")).to_have_text("Idle")


def test_pause_requires_running_engine(panel_page: Page) -> None:
    panel_page.get_by_role("button", name="Launch").click()
    panel_page.get_by_role("button", name="Pause / Resume").click()
    expect(panel_page.locator(".status-pill")).to_have_text("Paused")
    panel_page.get_by_role("button", name="Pause / Resume").click()
    expect(panel_page.locator(".status-pill")).to_have_text("Tracking")


def test_update_check(panel_page: Page) -> None:
    panel_page.get_by_role("button", name="Update Software").click()
    expect(panel_page.locator(".message")).not_to_have_text("Ready")


def test_calibrate_from_main_panel(panel_page: Page, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.e2e.conftest import patch_calibration_wizards

    patch_calibration_wizards(monkeypatch)
    panel_page.get_by_role("button", name="Calibrate").click()
    expect(panel_page.locator(".message")).to_contain_text("Offset profile saved")


def test_train_gestures_flow(panel_page: Page, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.e2e.conftest import patch_enrollment_session

    patch_enrollment_session(monkeypatch)
    panel_page.get_by_role("button", name="Train Gestures").click()
    expect(panel_page.get_by_role("heading", name="Train Gestures")).to_be_visible()

    for _ in range(3):
        panel_page.get_by_role("button", name="Capture (hold 1s)").click()
    expect(panel_page.locator(".enrollment-progress")).to_contain_text("Gesture")

    panel_page.get_by_role("button", name="← Back").click()
    expect(panel_page.get_by_role("button", name="Launch")).to_be_visible()
