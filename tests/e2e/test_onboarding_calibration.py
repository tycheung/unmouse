"""Playwright end-to-end tests for first-run onboarding and calibration."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_onboarding_welcome_to_finish(onboarding_page: Page) -> None:
    expect(onboarding_page.get_by_text("Step 1/6")).to_be_visible()
    onboarding_page.get_by_role("button", name="Get started").click()
    expect(onboarding_page.get_by_role("heading", name="Camera check")).to_be_visible()

    onboarding_page.get_by_role("button", name="Test camera").click()
    expect(onboarding_page.locator(".onboarding-note")).to_contain_text("Camera check passed")
    onboarding_page.get_by_role("button", name="Continue").click()

    expect(onboarding_page.get_by_role("heading", name="9-point calibration")).to_be_visible()
    onboarding_page.get_by_role("button", name="Start 9-point calibration").click()
    expect(onboarding_page.locator(".onboarding-note")).to_contain_text(
        "Polynomial calibration saved",
    )
    onboarding_page.get_by_role("button", name="Continue").click()

    expect(onboarding_page.get_by_role("heading", name="Offset calibration")).to_be_visible()
    onboarding_page.get_by_role("button", name="Start offset calibration").click()
    expect(onboarding_page.locator(".onboarding-note")).to_contain_text("Offset profile saved")
    onboarding_page.get_by_role("button", name="Continue").click()

    expect(onboarding_page.get_by_role("heading", name="Gesture enrollment")).to_be_visible()
    onboarding_page.get_by_role("button", name="Continue").click()

    expect(onboarding_page.get_by_role("heading", name="Ready to launch")).to_be_visible()
    onboarding_page.get_by_role("button", name="Finish setup").click()
    expect(onboarding_page.get_by_role("button", name="Launch")).to_be_visible()


def test_onboarding_skip_polynomial_step(onboarding_page: Page) -> None:
    onboarding_page.get_by_role("button", name="Get started").click()
    onboarding_page.get_by_role("button", name="Test camera").click()
    onboarding_page.get_by_role("button", name="Continue").click()

    onboarding_page.get_by_role("button", name="Skip this step").click()
    onboarding_page.get_by_role("button", name="Skip anyway").click()
    expect(onboarding_page.get_by_role("heading", name="Offset calibration")).to_be_visible()


def test_onboarding_enroll_gestures_from_wizard(
    onboarding_page: Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.e2e.conftest import patch_enrollment_session

    patch_enrollment_session(monkeypatch)
    onboarding_page.get_by_role("button", name="Get started").click()
    onboarding_page.get_by_role("button", name="Test camera").click()
    onboarding_page.get_by_role("button", name="Continue").click()
    onboarding_page.get_by_role("button", name="Start 9-point calibration").click()
    onboarding_page.get_by_role("button", name="Continue").click()
    onboarding_page.get_by_role("button", name="Start offset calibration").click()
    onboarding_page.get_by_role("button", name="Continue").click()

    onboarding_page.get_by_role("button", name="Enroll gestures").click()
    expect(onboarding_page.get_by_role("heading", name="Train Gestures")).to_be_visible()
    onboarding_page.get_by_role("button", name="Capture (hold 1s)").click()
    onboarding_page.get_by_role("button", name="← Back").click()
    expect(onboarding_page.get_by_role("heading", name="Gesture enrollment")).to_be_visible()


def test_calibrate_runs_polynomial_when_missing(
    panel_page: Page,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.e2e.conftest import build_panel_api, patch_calibration_wizards
    from tests.e2e.harness import E2EHarness

    patch_calibration_wizards(monkeypatch)
    monkeypatch.setattr(
        "unmouse.gaze.calibration.load_calibration",
        lambda _path: None,
    )
    calls = {"polynomial": 0, "offset": 0}

    def fake_poly(_settings: object) -> object:
        calls["polynomial"] += 1
        from unmouse.launcher.calibration_wizards import PolynomialWizardOutcome

        return PolynomialWizardOutcome(
            success=True,
            model=None,
            residual_px=1.0,
            message="Polynomial calibration saved (mock).",
            retry_recommended=False,
        )

    def fake_offset(_settings: object) -> object:
        calls["offset"] += 1
        from unmouse.launcher.calibration_wizards import OffsetWizardOutcome

        return OffsetWizardOutcome(success=True, message="Offset profile saved (mock).")

    monkeypatch.setattr("unmouse.launcher.calibration_wizards.run_polynomial_wizard", fake_poly)
    monkeypatch.setattr("unmouse.launcher.calibration_wizards.run_offset_wizard", fake_offset)

    api = build_panel_api(tmp_path, monkeypatch, first_run=False)
    harness = E2EHarness(api)
    harness.start()
    try:
        panel_page.goto(harness.url)
        panel_page.wait_for_selector("h1:text('unmouse')")
        panel_page.get_by_role("button", name="Calibrate").click()
        expect(panel_page.locator(".message")).to_contain_text("Offset profile saved")
    finally:
        harness.stop()

    assert calls["polynomial"] == 1
    assert calls["offset"] == 1
