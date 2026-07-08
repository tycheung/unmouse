"""Unit tests for PyInstaller packaging artifacts."""

from __future__ import annotations

from pathlib import Path

from unmouse.launcher.engine_runner import build_engine_command
from unmouse.utils import paths

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "unmouse.spec"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_exe.ps1"


def test_unmouse_spec_bundles_required_assets() -> None:
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert "assets/gestures" in text
    assert "assets/ui" in text
    assert "icon.ico" in text
    assert 'name="unmouse"' in text
    assert "onefile=True" in text


def test_unmouse_spec_lists_hiddenimports() -> None:
    text = SPEC_PATH.read_text(encoding="utf-8")
    for module in ("webview", "pystray", "uiautomation", "mss", "mediapipe"):
        assert module in text


def test_build_exe_script_runs_pyinstaller() -> None:
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "pyinstaller unmouse.spec" in text
    assert "generate_icon.py" in text


def test_build_engine_command_uses_exe_flag_when_frozen(monkeypatch) -> None:
    monkeypatch.setattr("unmouse.launcher.engine_runner.sys.frozen", True, raising=False)
    assert build_engine_command(executable=r"C:\dist\unmouse.exe") == [
        r"C:\dist\unmouse.exe",
        "--engine",
    ]


def test_is_frozen_helper(monkeypatch) -> None:
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    assert paths.is_frozen() is False
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    assert paths.is_frozen() is True


def test_packaged_asset_paths_exist() -> None:
    assert (REPO_ROOT / "assets" / "ui" / "index.html").is_file()
    assert (REPO_ROOT / "assets" / "gestures" / "v_sign.json").is_file()
    assert (REPO_ROOT / "assets" / "icon.ico").is_file()
