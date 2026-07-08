from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_onboarding_welcome_to_finish(onboarding_page: Page) -> None:
    expect(onboarding_page.get_by_text("Step 1/5")).to_be_visible()
    onboarding_page.get_by_role("button", name="Get started").click()
    expect(onboarding_page.get_by_role("heading", name="Camera check")).to_be_visible()

    onboarding_page.get_by_role("button", name="Test camera").click()
    expect(onboarding_page.locator(".onboarding-note")).to_contain_text("Camera check passed")
    onboarding_page.get_by_role("button", name="Continue").click()

    expect(onboarding_page.get_by_role("heading", name="Gaze calibration")).to_be_visible()
    onboarding_page.get_by_role("button", name="Start calibration").click()
    expect(onboarding_page.locator(".onboarding-note")).to_contain_text(
        "Gaze calibration saved",
    )
    onboarding_page.get_by_role("button", name="Continue").click()

    expect(onboarding_page.get_by_role("heading", name="Gesture enrollment")).to_be_visible()
    onboarding_page.get_by_role("button", name="Continue").click()

    expect(onboarding_page.get_by_role("heading", name="Ready to launch")).to_be_visible()
    onboarding_page.get_by_role("button", name="Finish setup").click()
    expect(onboarding_page.get_by_role("button", name="Launch")).to_be_visible()


def test_onboarding_skip_calibration_step(onboarding_page: Page) -> None:
    onboarding_page.get_by_role("button", name="Get started").click()
    onboarding_page.get_by_role("button", name="Test camera").click()
    onboarding_page.get_by_role("button", name="Continue").click()

    onboarding_page.get_by_role("button", name="Skip this step").click()
    onboarding_page.get_by_role("button", name="Skip anyway").click()
    expect(onboarding_page.get_by_role("heading", name="Gesture enrollment")).to_be_visible()


def test_onboarding_enroll_gestures_from_wizard(
    onboarding_page: Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.e2e.conftest import patch_enrollment_session

    patch_enrollment_session(monkeypatch)
    onboarding_page.get_by_role("button", name="Get started").click()
    onboarding_page.get_by_role("button", name="Test camera").click()
    onboarding_page.get_by_role("button", name="Continue").click()
    onboarding_page.get_by_role("button", name="Start calibration").click()
    onboarding_page.get_by_role("button", name="Continue").click()

    onboarding_page.get_by_role("button", name="Enroll gestures").click()
    expect(onboarding_page.get_by_role("heading", name="Train Gestures")).to_be_visible()
    onboarding_page.get_by_role("button", name="Capture (hold 1s)").click()
    onboarding_page.get_by_role("button", name="← Back").click()
    expect(onboarding_page.get_by_role("heading", name="Gesture enrollment")).to_be_visible()


def test_calibrate_runs_wizard_from_main(
    panel_page: Page,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.e2e.conftest import build_panel_api, patch_calibration_wizards
    from tests.e2e.harness import E2EHarness

    patch_calibration_wizards(monkeypatch)
    calls = {"calibration": 0}

    def fake_wizard(_settings: object) -> object:
        calls["calibration"] += 1
        from unmouse.launcher.calibration_wizards import ActionResult

        return ActionResult(True, "Gaze calibration saved (mock).")

    monkeypatch.setattr(
        "unmouse.launcher.calibration_wizards.run_calibration_wizard", fake_wizard
    )

    api = build_panel_api(tmp_path, monkeypatch, first_run=False)
    harness = E2EHarness(api)
    harness.start()
    try:
        panel_page.goto(harness.url)
        panel_page.wait_for_selector("h1:text('unmouse')")
        panel_page.get_by_role("button", name="Calibrate").click()
        expect(panel_page.locator(".message")).to_contain_text("Gaze calibration saved")
    finally:
        harness.stop()

    assert calls["calibration"] == 1
