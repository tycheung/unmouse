"""Unit tests for control panel Python bridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from unmouse.config import Settings
from unmouse.diagnostics import DiagnosticsSnapshot, save_diagnostics_snapshot
from unmouse.launcher.api import PanelApi
from unmouse.launcher.calibrate_wizard import OffsetWizardOutcome
from unmouse.launcher.engine_runner import EngineRunner, EngineWatchdog, WatchdogEvent
from unmouse.launcher.enroll_ui import EnrollmentCaptureResult
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.tray import FakeTrayBackend, TrayHandlers
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


def test_panel_api_launch_starts_engine_and_minimizes() -> None:
    runner = EngineRunner()
    tray = FakeTrayBackend(
        TrayHandlers(on_show=lambda: None, on_stop=lambda: None, on_quit=lambda: None),
    )
    minimized = {"called": False}
    api = PanelApi(
        settings=Settings(screen_width=800, screen_height=600),
        onboarding=MagicMock(spec=OnboardingController),
        engine_runner=runner,
        tray=tray,
    )
    api._onboarding.should_show_on_startup.return_value = False
    api.configure_launcher_shell(on_minimize_panel=lambda: minimized.__setitem__("called", True))

    class FakeProcess:
        pid = 1234

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    with patch.object(runner, "_popen", return_value=FakeProcess()):
        result = api.start_launch()

    assert result["ok"] is True
    assert result["tracking"] is True
    assert result["minimize"] is True
    assert minimized["called"] is True
    assert tray.running is True
    assert api.get_status()["tracking"] is True


def test_panel_api_stop_engine_updates_status() -> None:
    runner = EngineRunner()
    api = PanelApi(
        settings=Settings(screen_width=800, screen_height=600),
        onboarding=MagicMock(spec=OnboardingController),
        engine_runner=runner,
        tray=FakeTrayBackend(
            TrayHandlers(on_show=lambda: None, on_stop=lambda: None, on_quit=lambda: None),
        ),
    )
    api._onboarding.should_show_on_startup.return_value = False

    class FakeProcess:
        pid = 77

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    with patch.object(runner, "_popen", return_value=FakeProcess()):
        api.start_launch()
    result = api.stop_engine()
    assert result["ok"] is True
    assert api.get_status()["tracking"] is False


def test_panel_api_toggle_pause_updates_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    runner = EngineRunner()
    handlers = TrayHandlers(on_show=lambda: None, on_stop=lambda: None, on_quit=lambda: None)

    class FakeProcess:
        pid = 1

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    api = PanelApi(
        settings=Settings(screen_width=800, screen_height=600),
        onboarding=MagicMock(spec=OnboardingController),
        engine_runner=runner,
        tray=FakeTrayBackend(handlers),
    )
    api._onboarding.should_show_on_startup.return_value = False
    with patch.object(runner, "_popen", return_value=FakeProcess()):
        api.start_launch()
    assert api.toggle_pause()["paused"] is True
    assert api.toggle_pause()["paused"] is False


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


def test_panel_api_watchdog_diagnostics_and_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600)
    runner = EngineRunner()
    tray = FakeTrayBackend(
        TrayHandlers(on_show=lambda: None, on_stop=lambda: None, on_quit=lambda: None),
    )
    watchdog = MagicMock(spec=EngineWatchdog)
    api = PanelApi(
        settings=settings,
        onboarding=MagicMock(spec=OnboardingController),
        engine_runner=runner,
        tray=tray,
        watchdog=watchdog,
    )
    api._onboarding.should_show_on_startup.return_value = False

    class FakeProcess:
        pid = 55

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    with patch.object(runner, "_popen", return_value=FakeProcess()):
        api.start_launch()
    watchdog.start.assert_called_once()
    save_diagnostics_snapshot(
        settings,
        DiagnosticsSnapshot(
            broker_fps=28.5,
            gaze_confidence=0.77,
            gaze_queue_depth=0,
            gesture_queue_depth=0,
        ),
    )
    status = api.get_status()
    assert status["fps"] == 28.5
    assert status["confidence"] == 0.77
    api._handle_engine_crash(
        WatchdogEvent(exit_code=1, message="Engine exited unexpectedly (code 1).", restarted=True),
    )
    assert tray.notifications == ["Engine exited unexpectedly (code 1)."]
