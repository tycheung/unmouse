"""Disk persistence for user settings shared by launcher and engine."""

from __future__ import annotations

import json
from pathlib import Path

from unmouse.config import GazeMode, Settings, clear_settings_cache

SETTINGS_FILENAME = "settings.json"


def settings_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / SETTINGS_FILENAME


def load_persisted_settings() -> Settings:
    base = Settings()
    path = settings_file_path(base)
    if not path.is_file():
        return base
    data = _read_file(path)
    return _settings_from_dict(base, data)


def save_persisted_settings(settings: Settings) -> Path:
    path = settings_file_path(settings)
    merged = _read_file(path)
    merged.update(_settings_to_dict(settings))
    _write_file(path, merged)
    settings.profile_dir.mkdir(parents=True, exist_ok=True)
    clear_settings_cache()
    return path


def _read_file(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "settings JSON must be an object"
        raise ValueError(msg)
    return data


def _write_file(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _settings_to_dict(settings: Settings) -> dict[str, object]:
    return {
        "profile_name": settings.profile_name,
        "kalman_measurement_noise": settings.kalman_measurement_noise,
        "saccade_threshold_px": settings.saccade_threshold_px,
        "snap_radius_px": settings.snap_radius_px,
        "scroll_speed_multiplier": settings.scroll_speed_multiplier,
        "camera_index": settings.camera_index,
        "gaze_mode": settings.gaze_mode.value,
        "pause_hotkey": settings.pause_hotkey,
    }


def _settings_from_dict(base: Settings, data: dict[str, object]) -> Settings:
    payload = base.model_dump()
    for key in (
        "profile_name",
        "kalman_measurement_noise",
        "saccade_threshold_px",
        "snap_radius_px",
        "scroll_speed_multiplier",
        "camera_index",
    ):
        if key in data:
            payload[key] = data[key]
    if "gaze_mode" in data:
        payload["gaze_mode"] = GazeMode(str(data["gaze_mode"]))
    if "pause_hotkey" in data:
        payload["pause_hotkey"] = str(data["pause_hotkey"])
    return Settings.model_validate(payload)
