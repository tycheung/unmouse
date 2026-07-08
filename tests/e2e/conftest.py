"""Shared fixtures for Playwright end-to-end tests."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.e2e.harness import E2EHarness
from tests.fakes.enrollment import FakeEnrollmentSession
from unmouse.config import Settings
from unmouse.launcher.api import PanelApi
from unmouse.launcher.calibration_wizards import OffsetWizardOutcome, PolynomialWizardOutcome
from unmouse.launcher.engine_runner import EngineRunner
from unmouse.launcher.onboarding import CameraCheckResult, OnboardingController
from unmouse.launcher.results import ActionResult
from unmouse.launcher.settings import LauncherFlags, save_launcher_flags
from unmouse.launcher.tray import NoopTrayBackend, TrayHandlers

REPO_ROOT = Path(__file__).resolve().parents[2]
EXE_PATH = REPO_ROOT / "dist" / "unmouse.exe"


def wait_for_panel_ready(page, *, onboarding: bool = False) -> None:
    selector = (
        "button:has-text('Get started')"
        if onboarding
        else "button:has-text('Launch')"
    )
    page.wait_for_selector(selector, state="visible", timeout=15_000)


class FakeEngineProcess:
    pid = 4242

    def __init__(self) -> None:
        self._alive = True

    def poll(self) -> int | None:
        return None if self._alive else 0

    def terminate(self) -> None:
        self._alive = False

    def wait(self, timeout: float | None = None) -> int:
        self._alive = False
        return 0

    def kill(self) -> None:
        self._alive = False


def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    appdata = tmp_path / "appdata"
    appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    return Settings(screen_width=800, screen_height=600, profile_name="default")


def _mock_onboarding(
    settings: Settings,
    *,
    first_run: bool,
    mock_camera: bool = True,
    mock_calibration: bool = True,
) -> OnboardingController:
    check_camera = (
        (lambda _s: CameraCheckResult(ok=True, message="Camera OK (mock).", frames_read=10))
        if mock_camera
        else None
    )
    if mock_calibration:
        def run_polynomial(_s: Settings) -> ActionResult:
            return ActionResult(
                True,
                "Polynomial calibration saved (mock).",
                step_complete=True,
            )

        def run_offset(_s: Settings) -> ActionResult:
            return ActionResult(
                True,
                "Offset profile saved (mock).",
                step_complete=True,
            )
    else:
        run_polynomial = None
        run_offset = None
    controller = OnboardingController.create(
        settings,
        check_camera=check_camera,
        run_polynomial=run_polynomial,
        run_offset=run_offset,
    )
    if not first_run:
        save_launcher_flags(settings, LauncherFlags(first_run_complete=True))
    return controller


def build_panel_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    first_run: bool = False,
    mock_engine: bool = True,
    mock_calibration: bool = True,
) -> PanelApi:
    settings = _isolated_settings(tmp_path, monkeypatch)
    onboarding = _mock_onboarding(
        settings,
        first_run=first_run,
        mock_calibration=mock_calibration,
    )
    engine_runner = EngineRunner()
    if mock_engine:
        engine_runner = EngineRunner(popen=lambda *_a, **_k: FakeEngineProcess())
    tray = NoopTrayBackend(
        TrayHandlers(on_show=lambda: None, on_stop=lambda: None, on_quit=lambda: None),
    )
    return PanelApi(
        settings=settings,
        onboarding=onboarding,
        engine_runner=engine_runner,
        tray=tray,
    )


@pytest.fixture
def e2e_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[E2EHarness]:
    api = build_panel_api(tmp_path, monkeypatch, first_run=False)
    harness = E2EHarness(api)
    harness.start()
    yield harness
    harness.stop()


@pytest.fixture
def onboarding_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[E2EHarness]:
    api = build_panel_api(tmp_path, monkeypatch, first_run=True)
    harness = E2EHarness(api)
    harness.start()
    yield harness
    harness.stop()


@pytest.fixture
def panel_page(page, e2e_harness: E2EHarness):
    page.goto(e2e_harness.url, wait_until="networkidle")
    wait_for_panel_ready(page)
    return page


@pytest.fixture
def onboarding_page(page, onboarding_harness: E2EHarness):
    page.goto(onboarding_harness.url, wait_until="networkidle")
    wait_for_panel_ready(page, onboarding=True)
    return page


def patch_calibration_wizards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "unmouse.launcher.calibration_wizards.run_polynomial_wizard",
        lambda _s: PolynomialWizardOutcome(
            success=True,
            model=None,
            residual_px=1.0,
            message="Polynomial calibration saved (mock).",
            retry_recommended=False,
        ),
    )
    monkeypatch.setattr(
        "unmouse.launcher.calibration_wizards.run_offset_wizard",
        lambda _s: OffsetWizardOutcome(success=True, message="Offset profile saved (mock)."),
    )
    monkeypatch.setattr(
        "unmouse.gaze.calibration.load_calibration",
        lambda _path: object(),
    )


def patch_enrollment_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "unmouse.launcher.services.enrollment_service.GestureEnrollmentSession",
        FakeEnrollmentSession,
    )


@pytest.fixture
def run_smoke_command() -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        kwargs: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "timeout": 30,
            "check": False,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return subprocess.run(args, **kwargs)

    return _run


@pytest.fixture
def python_smoke_argv() -> list[str]:
    return [sys.executable, "-m", "unmouse", "--smoke"]


@pytest.fixture
def exe_smoke_argv() -> list[str] | None:
    if not EXE_PATH.is_file():
        return None
    return [str(EXE_PATH), "--smoke"]
