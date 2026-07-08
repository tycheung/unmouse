from __future__ import annotations

import json
import re
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

from unmouse import __version__

UpdateChannel = Literal["release", "none"]
DEFAULT_RELEASE_REPO = "tycheung/unmouse"
VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)*)")


@dataclass(frozen=True)
class UpdateStatus:
    available: bool
    message: str
    channel: UpdateChannel = "none"
    current_version: str | None = None
    latest_version: str | None = None
    download_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def check_updates(
    *,
    frozen: bool | None = None,
    current_version: str | None = None,
    release_repo: str = DEFAULT_RELEASE_REPO,
    fetch_release: Callable[[str], dict[str, object]] | None = None,
) -> UpdateStatus:
    version = current_version or __version__
    is_frozen = frozen if frozen is not None else bool(getattr(sys, "frozen", False))
    if is_frozen:
        return _check_release_update(
            version,
            release_repo=release_repo,
            fetch_release=fetch_release or _fetch_github_release,
        )
    return UpdateStatus(
        available=False,
        message="Updates are available from the release build only.",
        channel="none",
        current_version=version,
    )


def apply_update(status: UpdateStatus) -> UpdateStatus:
    if not status.available:
        return UpdateStatus(
            available=False,
            message="No update is available.",
            channel=status.channel,
            current_version=status.current_version,
            latest_version=status.latest_version,
            download_url=status.download_url,
        )
    if status.channel == "release" and status.download_url:
        webbrowser.open(status.download_url)
        return UpdateStatus(
            available=False,
            message="Opened release download page in your browser.",
            channel="release",
            current_version=status.current_version,
            latest_version=status.latest_version,
            download_url=status.download_url,
        )
    return UpdateStatus(
        available=False,
        message="Update channel is not configured.",
        channel=status.channel,
        current_version=status.current_version,
    )


def parse_version(version: str) -> tuple[int, ...]:
    match = VERSION_PATTERN.search(version.lstrip("v"))
    if match is None:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def version_is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _check_release_update(
    current_version: str,
    *,
    release_repo: str,
    fetch_release: Callable[[str], dict[str, object]],
) -> UpdateStatus:
    try:
        payload = fetch_release(release_repo)
    except (URLError, ValueError, json.JSONDecodeError) as exc:
        return UpdateStatus(
            available=False,
            message=f"Release check failed: {exc}",
            channel="release",
            current_version=current_version,
        )
    tag = str(payload.get("tag_name", ""))
    if not tag:
        return UpdateStatus(
            available=False,
            message="Release response did not include a version tag.",
            channel="release",
            current_version=current_version,
        )
    download_url = _pick_release_download(payload)
    if version_is_newer(tag, current_version):
        return UpdateStatus(
            available=True,
            message=f"Version {tag.lstrip('v')} is available (current {current_version}).",
            channel="release",
            current_version=current_version,
            latest_version=tag.lstrip("v"),
            download_url=download_url,
        )
    return UpdateStatus(
        available=False,
        message="You are on the latest release.",
        channel="release",
        current_version=current_version,
        latest_version=tag.lstrip("v"),
        download_url=download_url,
    )


def _pick_release_download(payload: dict[str, object]) -> str | None:
    html_url = payload.get("html_url")
    if isinstance(html_url, str) and html_url:
        return html_url
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        url = asset.get("browser_download_url")
        if isinstance(url, str) and url:
            return url
    return None


def _fetch_github_release(release_repo: str) -> dict[str, object]:
    url = f"https://api.github.com/repos/{release_repo}/releases/latest"
    request = Request(url, headers={"Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        msg = "release payload must be an object"
        raise ValueError(msg)
    return payload
