"""Shared helpers for the control panel API layer."""

from __future__ import annotations

from datetime import datetime

from unmouse.config import Settings
from unmouse.launcher.results import ActionResult
from unmouse.launcher.update import UpdateStatus


def action(ok: bool, message: str, **extra: object) -> dict[str, object]:
    payload = ActionResult(ok, message).to_dict()
    payload.update(extra)
    return payload


def update_payload(status: UpdateStatus) -> dict[str, object]:
    payload = status.to_dict()
    payload["version"] = status.latest_version
    return payload


def last_calibration_label(settings: Settings) -> str | None:
    from unmouse.gaze.calibration import calibration_path, load_calibration
    from unmouse.gaze.offset_profile import load_offset_profile, offset_profile_path

    candidates: list[float] = []
    cal_path = calibration_path(settings)
    if load_calibration(cal_path) is not None and cal_path.is_file():
        candidates.append(cal_path.stat().st_mtime)
    off_path = offset_profile_path(settings)
    if load_offset_profile(off_path) is not None and off_path.is_file():
        candidates.append(off_path.stat().st_mtime)
    if not candidates:
        return None
    return datetime.fromtimestamp(max(candidates)).strftime("%Y-%m-%d")
