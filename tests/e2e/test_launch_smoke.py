"""Launch and installer smoke tests for dev and frozen builds."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.e2e.conftest import REPO_ROOT, build_panel_api
from tests.e2e.harness import E2EHarness
from unmouse.launcher.panel import ui_index_path

pytestmark = pytest.mark.e2e

BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_exe.ps1"
EXE_PATH = REPO_ROOT / "dist" / "unmouse.exe"


def test_smoke_entry_point_python(
    run_smoke_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
    python_smoke_argv: list[str],
) -> None:
    result = run_smoke_command(python_smoke_argv)
    assert result.returncode == 0, result.stderr or result.stdout
    assert "smoke ok" in result.stdout


@pytest.mark.skipif(not EXE_PATH.is_file(), reason="dist/unmouse.exe not built")
def test_smoke_entry_point_frozen_exe(
    run_smoke_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
    exe_smoke_argv: list[str] | None,
) -> None:
    assert exe_smoke_argv is not None
    result = run_smoke_command(exe_smoke_argv)
    assert result.returncode == 0, result.stderr or result.stdout
    assert "smoke ok" in result.stdout


def test_ui_assets_present() -> None:
    index = ui_index_path()
    assert index.is_file()
    html = index.read_text(encoding="utf-8")
    for label in ("Launch", "Calibrate", "Settings", "Train Gestures"):
        assert label in html


def test_e2e_harness_serves_panel(
    e2e_harness: E2EHarness,
    run_smoke_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    import urllib.request

    with urllib.request.urlopen(e2e_harness.url, timeout=5) as response:
        body = response.read().decode("utf-8")
    assert "unmouse" in body
    assert "window.pywebview" in body


def test_engine_argv_uses_module_in_dev() -> None:
    from unmouse.launcher.engine_runner import build_engine_command

    command = build_engine_command(executable=sys.executable)
    assert command[0] == sys.executable
    assert "-m" in command
    assert "unmouse" in command
    assert "--engine" in command


@pytest.mark.skipif(not BUILD_SCRIPT.is_file(), reason="build script missing")
def test_build_script_exists() -> None:
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "pyinstaller" in text.lower()
    assert "unmouse.spec" in text


@pytest.mark.skipif(not EXE_PATH.is_file(), reason="dist/unmouse.exe not built")
def test_frozen_exe_launches_smoke_without_python(
    run_smoke_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    result = run_smoke_command([str(EXE_PATH), "--smoke"])
    assert result.returncode == 0
    assert EXE_PATH.stat().st_size > 1_000_000


def test_harness_panel_api_starts_on_main_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    api = build_panel_api(tmp_path, monkeypatch, first_run=False)
    state = api.get_onboarding_state()
    assert state["should_show"] is False
    assert api.get_view()["view"] == "main"


def test_harness_api_bridge_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.e2e.conftest import build_panel_api

    api = build_panel_api(tmp_path, monkeypatch, first_run=False)
    harness = E2EHarness(api)
    harness.start()
    try:
        import json
        import urllib.request

        payload = json.dumps({"args": []}).encode("utf-8")
        request = urllib.request.Request(
            f"{harness.url}api/get_status",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["message"] == "Ready"
        assert data["tracking"] is False
    finally:
        harness.stop()
