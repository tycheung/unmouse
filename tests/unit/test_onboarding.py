"""Unit tests for first-run onboarding."""

from __future__ import annotations

import json

from unmouse.config import Settings
from unmouse.launcher.onboarding import (
    CameraCheckResult,
    LauncherSettings,
    OnboardingActionResult,
    OnboardingController,
    load_launcher_settings,
    save_launcher_settings,
)


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return Settings(screen_width=800, screen_height=600, profile_name="lab")


def test_launcher_settings_round_trip(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    path = save_launcher_settings(settings, LauncherSettings(first_run_complete=True))
    assert json.loads(path.read_text(encoding="utf-8"))["first_run_complete"] is True
    assert load_launcher_settings(settings).first_run_complete is True


def test_onboarding_flow_skip_and_complete(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    controller = OnboardingController.create(
        settings,
        check_camera=lambda _s: CameraCheckResult(ok=True, message="ok"),
        run_polynomial=lambda _s: OnboardingActionResult(True, "saved", step_complete=True),
        run_offset=lambda _s: OnboardingActionResult(True, "offset saved", step_complete=True),
    )
    assert controller.should_show_on_startup() is True
    controller.advance()
    controller.check_camera()
    controller.advance()
    assert controller.run_polynomial_step()["ok"] is True
    assert controller.skip_current_step(confirmed=False)["ok"] is False
    assert controller.skip_current_step(confirmed=True)["ok"] is True
    controller.step_index = 3
    assert controller.run_offset_step()["ok"] is True
    controller.step_index = 5
    controller.complete()
    assert load_launcher_settings(settings).first_run_complete is True
