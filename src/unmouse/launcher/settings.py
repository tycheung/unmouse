"""User settings and profile persistence for the control panel."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from unmouse.config import GazeMode, Settings, clear_settings_cache

SETTINGS_FILENAME = "settings.json"
PROFILE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
RESERVED_PROFILE_NAMES = frozenset({".", ".."})


@dataclass
class LauncherFlags:
    first_run_complete: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LauncherFlags:
        return cls(first_run_complete=bool(data.get("first_run_complete", False)))


@dataclass(frozen=True)
class PanelSettingsSnapshot:
    profile_name: str
    profiles: tuple[str, ...]
    kalman_measurement_noise: float
    saccade_threshold_px: float
    snap_radius_px: float
    scroll_speed_multiplier: float
    camera_index: int
    gaze_mode: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def settings_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / SETTINGS_FILENAME


def profiles_root(settings: Settings) -> Path:
    return settings.app_data_dir / "profiles"


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


def load_launcher_flags(settings: Settings) -> LauncherFlags:
    return LauncherFlags.from_dict(_read_file(settings_file_path(settings)))


def save_launcher_flags(settings: Settings, flags: LauncherFlags) -> Path:
    path = settings_file_path(settings)
    merged = _read_file(path)
    merged["first_run_complete"] = flags.first_run_complete
    _write_file(path, merged)
    return path


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


def get_panel_settings(settings: Settings) -> dict[str, object]:
    snapshot = panel_settings_snapshot(settings)
    return snapshot.to_dict()


def update_panel_settings(settings: Settings, updates: dict[str, object]) -> dict[str, object]:
    current = _current_settings(settings).model_copy(deep=True)
    if "kalman_measurement_noise" in updates:
        current.kalman_measurement_noise = _as_float(updates["kalman_measurement_noise"])
    if "saccade_threshold_px" in updates:
        current.saccade_threshold_px = _as_float(updates["saccade_threshold_px"])
    if "snap_radius_px" in updates:
        current.snap_radius_px = _as_float(updates["snap_radius_px"])
    if "scroll_speed_multiplier" in updates:
        current.scroll_speed_multiplier = _as_float(updates["scroll_speed_multiplier"])
    if "camera_index" in updates:
        current.camera_index = _as_int(updates["camera_index"])
    if "gaze_mode" in updates:
        current.gaze_mode = GazeMode(str(updates["gaze_mode"]))
    save_persisted_settings(current)
    return get_panel_settings(current)


def list_profiles(settings: Settings) -> list[str]:
    root = profiles_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    names = sorted(path.name for path in root.iterdir() if path.is_dir())
    if settings.profile_name not in names:
        names.append(settings.profile_name)
        names.sort()
    return names


def create_profile(settings: Settings, name: str) -> dict[str, object]:
    profile = _validate_profile_name(name)
    path = profiles_root(settings) / profile
    if path.exists():
        return {"ok": False, "message": f"Profile '{profile}' already exists."}
    path.mkdir(parents=True, exist_ok=False)
    return {
        "ok": True,
        "message": f"Created profile '{profile}'.",
        "profiles": list_profiles(_current_settings(settings)),
    }


def rename_profile(settings: Settings, old_name: str, new_name: str) -> dict[str, object]:
    old = _validate_profile_name(old_name)
    new = _validate_profile_name(new_name)
    root = profiles_root(settings)
    source = root / old
    target = root / new
    if not source.is_dir():
        return {"ok": False, "message": f"Profile '{old}' not found."}
    if target.exists():
        return {"ok": False, "message": f"Profile '{new}' already exists."}
    source.rename(target)
    current = _current_settings(settings).model_copy(deep=True)
    if current.profile_name == old:
        current.profile_name = new
        save_persisted_settings(current)
    return {
        "ok": True,
        "message": f"Renamed '{old}' to '{new}'.",
        "profiles": list_profiles(current),
        "profile_name": current.profile_name,
    }


def delete_profile(settings: Settings, name: str) -> dict[str, object]:
    current = _current_settings(settings)
    profile = _validate_profile_name(name)
    profiles = list_profiles(current)
    if len(profiles) <= 1:
        return {"ok": False, "message": "Cannot delete the only profile."}
    if profile == current.profile_name:
        return {
            "ok": False,
            "message": "Switch to another profile before deleting the active one.",
        }
    path = profiles_root(settings) / profile
    if not path.is_dir():
        return {"ok": False, "message": f"Profile '{profile}' not found."}
    shutil.rmtree(path)
    return {
        "ok": True,
        "message": f"Deleted profile '{profile}'.",
        "profiles": list_profiles(current),
    }


def activate_profile(settings: Settings, name: str) -> dict[str, object]:
    profile = _validate_profile_name(name)
    path = profiles_root(settings) / profile
    path.mkdir(parents=True, exist_ok=True)
    current = _current_settings(settings).model_copy(deep=True)
    current.profile_name = profile
    save_persisted_settings(current)
    return {
        "ok": True,
        "message": f"Active profile: {profile}",
        "profile_name": profile,
        "profiles": list_profiles(current),
    }


def panel_settings_snapshot(settings: Settings) -> PanelSettingsSnapshot:
    return PanelSettingsSnapshot(
        profile_name=settings.profile_name,
        profiles=tuple(list_profiles(settings)),
        kalman_measurement_noise=settings.kalman_measurement_noise,
        saccade_threshold_px=settings.saccade_threshold_px,
        snap_radius_px=settings.snap_radius_px,
        scroll_speed_multiplier=settings.scroll_speed_multiplier,
        camera_index=settings.camera_index,
        gaze_mode=settings.gaze_mode.value,
    )


def _settings_to_dict(settings: Settings) -> dict[str, object]:
    return {
        "profile_name": settings.profile_name,
        "kalman_measurement_noise": settings.kalman_measurement_noise,
        "saccade_threshold_px": settings.saccade_threshold_px,
        "snap_radius_px": settings.snap_radius_px,
        "scroll_speed_multiplier": settings.scroll_speed_multiplier,
        "camera_index": settings.camera_index,
        "gaze_mode": settings.gaze_mode.value,
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
    return Settings.model_validate(payload)


def _validate_profile_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or cleaned in RESERVED_PROFILE_NAMES:
        msg = "profile name is required"
        raise ValueError(msg)
    if not PROFILE_NAME_PATTERN.fullmatch(cleaned):
        msg = "profile name may only contain letters, numbers, underscore, or hyphen"
        raise ValueError(msg)
    return cleaned


def _current_settings(settings: Settings) -> Settings:
    path = settings_file_path(settings)
    if path.is_file():
        return load_persisted_settings()
    return settings


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value))
