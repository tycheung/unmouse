from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from unmouse.config import GazeMode, Settings
from unmouse.persistence import (
    load_persisted_settings,
    save_persisted_settings,
    settings_file_path,
)

PROFILE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
RESERVED_PROFILE_NAMES = frozenset({".", ".."})


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
    pause_hotkey: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def profiles_root(settings: Settings) -> Path:
    return settings.app_data_dir / "profiles"


def get_panel_settings(settings: Settings) -> dict[str, object]:
    snapshot = panel_settings_snapshot(settings)
    return snapshot.to_dict()


def update_panel_settings(settings: Settings, updates: dict[str, object]) -> dict[str, object]:
    current = _current_settings(settings).model_copy(deep=True)
    for field, coerce in _PANEL_FIELD_COERCERS.items():
        if field in updates:
            setattr(current, field, coerce(updates[field]))
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
        pause_hotkey=settings.pause_hotkey,
    )


def toggle_gaze_mode(settings: Settings) -> GazeMode:
    current = _current_settings(settings).model_copy(deep=True)
    next_mode = (
        GazeMode.CURSOR_FOLLOW
        if current.gaze_mode is GazeMode.GAZE_ONLY
        else GazeMode.GAZE_ONLY
    )
    current.gaze_mode = next_mode
    save_persisted_settings(current)
    return next_mode


def panel_save_settings(settings: Settings, updates: dict[str, object]) -> dict[str, object]:
    snapshot = update_panel_settings(settings, updates)
    return {"ok": True, "message": "Settings saved.", "settings": snapshot}


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


_PANEL_FIELD_COERCERS: dict[str, Callable[[object], object]] = {
    "kalman_measurement_noise": _as_float,
    "saccade_threshold_px": _as_float,
    "snap_radius_px": _as_float,
    "scroll_speed_multiplier": _as_float,
    "camera_index": _as_int,
    "gaze_mode": lambda value: GazeMode(str(value)),
    "pause_hotkey": lambda value: str(value).strip().lower(),
}
