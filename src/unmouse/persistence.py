from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from unmouse.config import GazeMode, Settings, clear_settings_cache
from unmouse.utils.json_io import read_json_object_or_empty, write_json_object

SETTINGS_FILENAME = "settings.json"


@dataclass
class LauncherFlags:
    first_run_complete: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LauncherFlags:
        return cls(first_run_complete=bool(data.get("first_run_complete", False)))


def settings_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / SETTINGS_FILENAME


def read_settings_file(path: Path) -> dict[str, object]:
    return read_json_object_or_empty(path, error_message="settings JSON must be an object")


def write_settings_file(path: Path, data: dict[str, object]) -> None:
    write_json_object(path, data)


def load_launcher_flags(settings: Settings) -> LauncherFlags:
    return LauncherFlags.from_dict(read_settings_file(settings_file_path(settings)))


def save_launcher_flags(settings: Settings, flags: LauncherFlags) -> Path:
    path = settings_file_path(settings)
    merged = read_settings_file(path)
    merged["first_run_complete"] = flags.first_run_complete
    write_settings_file(path, merged)
    return path


def load_persisted_settings() -> Settings:
    base = Settings()
    path = settings_file_path(base)
    if not path.is_file():
        return base
    data = read_settings_file(path)
    return _settings_from_dict(base, data)


def save_persisted_settings(settings: Settings) -> Path:
    path = settings_file_path(settings)
    merged = read_settings_file(path)
    merged.update(_settings_to_dict(settings))
    write_settings_file(path, merged)
    settings.profile_dir.mkdir(parents=True, exist_ok=True)
    clear_settings_cache()
    return path


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
