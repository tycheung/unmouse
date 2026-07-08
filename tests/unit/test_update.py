from __future__ import annotations

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


def test_check_updates_unavailable_in_dev_install() -> None:
    status = check_updates(frozen=False)
    assert status.available is False
    assert status.channel == "none"
    assert "release build" in status.message.lower()


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
