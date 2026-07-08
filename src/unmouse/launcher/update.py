from __future__ import annotations

import json
import re
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

from unmouse import __version__
from unmouse.utils.paths import project_root

UpdateChannel = Literal["git", "release", "none"]
RunCommand = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
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


def _git_status(
    *,
    available: bool,
    message: str,
    current_version: str | None = None,
    latest_version: str | None = None,
) -> UpdateStatus:
    return UpdateStatus(
        available=available,
        message=message,
        channel="git",
        current_version=current_version or __version__,
        latest_version=latest_version,
    )


def _release_status(
    *,
    available: bool,
    message: str,
    current_version: str | None,
    latest_version: str | None = None,
    download_url: str | None = None,
) -> UpdateStatus:
    return UpdateStatus(
        available=available,
        message=message,
        channel="release",
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
    )


def check_updates(
    *,
    root: Path | None = None,
    frozen: bool | None = None,
    current_version: str | None = None,
    release_repo: str = DEFAULT_RELEASE_REPO,
    run_command: RunCommand | None = None,
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
    repo_root = root or project_root()
    if _is_git_repo(repo_root):
        return _check_git_update(repo_root, run_command=run_command or _run_git)
    return UpdateStatus(
        available=False,
        message="Update check unavailable for this install.",
        channel="none",
        current_version=version,
    )


def apply_update(status: UpdateStatus, *, run_command: RunCommand | None = None) -> UpdateStatus:
    if not status.available:
        return UpdateStatus(
            available=False,
            message="No update is available.",
            channel=status.channel,
            current_version=status.current_version,
            latest_version=status.latest_version,
            download_url=status.download_url,
        )
    if status.channel == "git":
        return _apply_git_update(project_root(), run_command=run_command or _run_git)
    if status.channel == "release" and status.download_url:
        webbrowser.open(status.download_url)
        return _release_status(
            available=False,
            message="Opened release download page in your browser.",
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


def _is_git_repo(root: Path) -> bool:
    return (root / ".git").is_dir()


def _check_git_update(root: Path, *, run_command: RunCommand) -> UpdateStatus:
    try:
        run_command(["git", "-C", str(root), "fetch", "--quiet"], root)
        local = run_command(["git", "-C", str(root), "rev-parse", "HEAD"], root)
        remote = run_command(["git", "-C", str(root), "rev-parse", "@{u}"], root)
    except RuntimeError as exc:
        return _git_status(available=False, message=str(exc))
    local_sha = local.stdout.strip()
    remote_sha = remote.stdout.strip()
    if local_sha == remote_sha:
        return _git_status(
            available=False,
            message="Git install is up to date.",
            latest_version=remote_sha[:7],
        )
    return _git_status(
        available=True,
        message="Git updates are available. Click Update Software to pull.",
        current_version=local_sha[:7],
        latest_version=remote_sha[:7],
    )


def _apply_git_update(root: Path, *, run_command: RunCommand) -> UpdateStatus:
    try:
        result = run_command(["git", "-C", str(root), "pull", "--ff-only"], root)
    except RuntimeError as exc:
        return _git_status(available=True, message=str(exc))
    message = result.stdout.strip() or "Git pull completed."
    return _git_status(available=False, message=message)


def _check_release_update(
    current_version: str,
    *,
    release_repo: str,
    fetch_release: Callable[[str], dict[str, object]],
) -> UpdateStatus:
    try:
        payload = fetch_release(release_repo)
    except (URLError, ValueError, json.JSONDecodeError) as exc:
        return _release_status(
            available=False,
            message=f"Release check failed: {exc}",
            current_version=current_version,
        )
    tag = str(payload.get("tag_name", ""))
    if not tag:
        return _release_status(
            available=False,
            message="Release response did not include a version tag.",
            current_version=current_version,
        )
    download_url = _pick_release_download(payload)
    if version_is_newer(tag, current_version):
        return _release_status(
            available=True,
            message=f"Version {tag.lstrip('v')} is available (current {current_version}).",
            current_version=current_version,
            latest_version=tag.lstrip("v"),
            download_url=download_url,
        )
    return _release_status(
        available=False,
        message="You are on the latest release.",
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


def _run_git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        msg = f"{args[-1]} failed: {detail}"
        raise RuntimeError(msg)
    return result
