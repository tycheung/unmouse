from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from unmouse.config import GazeMode, Settings, clear_settings_cache
from unmouse.utils.json_io import read_json_object, read_json_object_or_empty, write_json_object

SETTINGS_FILENAME = "settings.json"
RUNTIME_FILENAME = "runtime.json"

PERSISTED_SETTING_FIELDS = (
    "profile_name",
    "gaze_calibration_points",
    "fixation_threshold",
    "snap_radius_px",
    "scroll_speed_multiplier",
    "camera_index",
    "gaze_mode",
    "pause_hotkey",
)


@dataclass
class LauncherFlags:
    first_run_complete: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LauncherFlags:
        return cls(first_run_complete=bool(data.get("first_run_complete", False)))


@dataclass
class RuntimeState:
    paused: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RuntimeState:
        return cls(paused=bool(data.get("paused", False)))


def settings_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / SETTINGS_FILENAME


def runtime_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / RUNTIME_FILENAME


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


def load_runtime(settings: Settings) -> RuntimeState:
    path = runtime_file_path(settings)
    if not path.is_file():
        return RuntimeState()
    data = read_json_object(path, error_message="runtime JSON must be an object")
    return RuntimeState.from_dict(data)


def save_runtime(settings: Settings, state: RuntimeState) -> Path:
    path = runtime_file_path(settings)
    write_json_object(path, state.to_dict())
    return path


def set_paused(settings: Settings, paused: bool) -> RuntimeState:
    state = RuntimeState(paused=paused)
    save_runtime(settings, state)
    return state


def toggle_paused(settings: Settings) -> RuntimeState:
    state = load_runtime(settings)
    state.paused = not state.paused
    save_runtime(settings, state)
    return state


def sync_engine_controls(settings: Settings) -> None:
    settings.paused = load_runtime(settings).paused
    persisted = load_persisted_settings()
    settings.gaze_mode = persisted.gaze_mode
    settings.pause_hotkey = persisted.pause_hotkey


def _settings_to_dict(settings: Settings) -> dict[str, object]:
    data: dict[str, object] = {}
    for field in PERSISTED_SETTING_FIELDS:
        value = getattr(settings, field)
        data[field] = value.value if isinstance(value, GazeMode) else value
    return data


def _settings_from_dict(base: Settings, data: dict[str, object]) -> Settings:
    payload = base.model_dump()
    for field in PERSISTED_SETTING_FIELDS:
        if field in data:
            payload[field] = data[field]
    return Settings.model_validate(payload)
