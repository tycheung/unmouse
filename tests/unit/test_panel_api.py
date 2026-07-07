"""Unit tests for control panel Python bridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from unmouse.config import Settings
from unmouse.launcher.api import PanelApi
from unmouse.launcher.calibrate_wizard import OffsetWizardOutcome
from unmouse.launcher.enroll_ui import EnrollmentCaptureResult
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.update import UpdateStatus


def _api_without_onboarding_prompt(settings: Settings | None = None) -> PanelApi:
    app_settings = settings or Settings(screen_width=800, screen_height=600)
    onboarding = MagicMock(spec=OnboardingController)
    onboarding.should_show_on_startup.return_value = False
    onboarding.get_state.return_value = {"should_show": False}
    return PanelApi(settings=app_settings, onboarding=onboarding)


def test_panel_api_opens_onboarding_on_first_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    api = PanelApi(settings=Settings(screen_width=800, screen_height=600))
    assert api.view == "onboarding"
    state = api.get_onboarding_state()
    assert state["should_show"] is True
    assert state["step_id"] == "welcome"


def test_panel_api_default_status() -> None:
    api = _api_without_onboarding_prompt()
    status = api.get_status()
    assert status["message"] == "Ready"
    assert status["tracking"] is False


def test_panel_api_update_check_without_git_repo() -> None:
    api = _api_without_onboarding_prompt()
    with patch(
        "unmouse.launcher.api.check_updates",
        return_value=UpdateStatus(
            available=False,
            message="Update check unavailable for this install.",
            channel="none",
        ),
    ):
        result = api.check_for_updates()
    assert result["available"] is False
    assert result["channel"] == "none"


def test_panel_api_calibrate_runs_offset_when_polynomial_exists() -> None:
    api = _api_without_onboarding_prompt()
    with patch(
        "unmouse.gaze.calibration.load_calibration",
        return_value=object(),
    ), patch(
        "unmouse.launcher.calibrate_wizard.run_offset_wizard",
        return_value=OffsetWizardOutcome(success=True, message="Offset profile saved."),
    ) as run_offset:
        calibrate = api.start_calibrate()
    run_offset.assert_called_once()
    assert calibrate["ok"] is True
    assert "Offset" in calibrate["message"]


def test_panel_api_launch_stub() -> None:
    api = _api_without_onboarding_prompt()
    launch = api.start_launch()
    assert launch["ok"] is False


def test_panel_api_view_navigation() -> None:
    api = _api_without_onboarding_prompt()
    assert api.get_view()["view"] == "main"
    assert api.show_settings()["view"] == "settings"
    assert api.get_view()["view"] == "settings"
    assert api.show_onboarding()["view"] == "onboarding"
    assert api.show_main()["view"] == "main"


def test_panel_api_set_status_message() -> None:
    api = _api_without_onboarding_prompt()
    updated = api.set_status_message("Calibrating")
    assert updated["message"] == "Calibrating"
    assert api.get_status()["message"] == "Calibrating"


def test_panel_api_show_enrollment_opens_session() -> None:
    api = _api_without_onboarding_prompt()
    with patch("unmouse.launcher.api.GestureEnrollmentSession") as session_cls:
        session_cls.return_value.get_state.return_value = {
            "active": True,
            "done": False,
            "gesture_index": 0,
        }
        result = api.show_enrollment()
    session_cls.return_value.open.assert_called_once()
    assert result["ok"] is True
    assert result["view"] == "enrollment"
    assert api.view == "enrollment"


def test_panel_api_enrollment_capture_marks_onboarding_complete() -> None:
    api = _api_without_onboarding_prompt()
    with patch("unmouse.launcher.api.GestureEnrollmentSession") as session_cls:
        session_cls.return_value.get_state.return_value = {"active": True, "done": True}
        session_cls.return_value.capture_current_gesture.return_value = EnrollmentCaptureResult(
            ok=True,
            message="All gesture templates enrolled.",
            done=True,
        )
        api.show_enrollment()
        result = api.enrollment_capture()
    assert result["ok"] is True
    assert api._onboarding.gestures_complete is True
