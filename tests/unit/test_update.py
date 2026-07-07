"""Unit tests for launcher update detection."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from unmouse.launcher.update import (
    UpdateStatus,
    apply_update,
    check_updates,
    parse_version,
    version_is_newer,
)


def test_version_comparison() -> None:
    assert version_is_newer("1.2.0", "1.0.0")
    assert not version_is_newer("1.0.0", "1.2.0")
    assert parse_version("v2.10.3") == (2, 10, 3)


def test_check_git_update_when_behind(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        if args[-1] == "fetch":
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[-1] == "HEAD":
            return subprocess.CompletedProcess(args, 0, "aaa", "")
        return subprocess.CompletedProcess(args, 0, "bbb", "")

    status = check_updates(root=tmp_path, frozen=False, run_command=fake_run)
    assert status.available is True
    assert status.channel == "git"
    assert str(tmp_path) in calls[0]


def test_check_git_update_when_current(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "same", "")

    status = check_updates(root=tmp_path, frozen=False, run_command=fake_run)
    assert status.available is False
    assert "up to date" in status.message.lower()


def test_check_release_update_when_newer() -> None:
    payload = {
        "tag_name": "v2.0.0",
        "html_url": "https://github.com/tycheung/unmouse/releases/tag/v2.0.0",
        "assets": [{"browser_download_url": "https://example.com/unmouse.zip"}],
    }
    status = check_updates(
        frozen=True,
        current_version="1.0.0",
        fetch_release=lambda _repo: payload,
    )
    assert status.available is True
    assert status.channel == "release"
    assert status.download_url == payload["html_url"]


def test_apply_git_update_runs_pull(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "Already up to date.", "")

    pending = UpdateStatus(
        available=True,
        message="pending",
        channel="git",
    )
    with patch("unmouse.launcher.update.project_root", return_value=tmp_path):
        result = apply_update(pending, run_command=fake_run)
    assert result.available is False
    assert calls[-1][-2:] == ["pull", "--ff-only"]


def test_apply_release_update_opens_browser() -> None:
    pending = UpdateStatus(
        available=True,
        message="pending",
        channel="release",
        download_url="https://example.com/download",
    )
    with patch("unmouse.launcher.update.webbrowser.open") as open_mock:
        result = apply_update(pending)
    open_mock.assert_called_once_with("https://example.com/download")
    assert result.available is False
