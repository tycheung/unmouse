from __future__ import annotations

import json

from unmouse.config import GazeMode, Settings
from unmouse.launcher.settings import (
    activate_profile,
    create_profile,
    delete_profile,
    rename_profile,
    update_panel_settings,
)
from unmouse.persistence import (
    LauncherFlags,
    load_launcher_flags,
    load_persisted_settings,
    save_launcher_flags,
    save_persisted_settings,
    settings_file_path,
)


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return Settings(screen_width=800, screen_height=600, profile_name="default")


def test_save_and_load_persisted_settings(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    settings = settings.model_copy(
        update={
            "kalman_measurement_noise": 15.0,
            "gaze_mode": GazeMode.GAZE_ONLY,
            "scroll_speed_multiplier": 1.5,
        }
    )
    save_persisted_settings(settings)
    loaded = load_persisted_settings()
    assert loaded.kalman_measurement_noise == 15.0
    assert loaded.gaze_mode is GazeMode.GAZE_ONLY
    assert loaded.scroll_speed_multiplier == 1.5


def test_launcher_flags_merge_with_user_settings(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    save_persisted_settings(settings.model_copy(update={"snap_radius_px": 60.0}))
    save_launcher_flags(settings, LauncherFlags(first_run_complete=True))
    data = json.loads(settings_file_path(settings).read_text(encoding="utf-8"))
    assert data["first_run_complete"] is True
    assert data["snap_radius_px"] == 60.0
    assert load_launcher_flags(settings).first_run_complete is True


def test_profile_crud(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    assert create_profile(settings, "desk")["ok"] is True
    assert create_profile(settings, "desk")["ok"] is False
    assert "desk" in create_profile(settings, "laptop")["profiles"]
    renamed = rename_profile(settings, "desk", "office")
    assert renamed["ok"] is True
    assert activate_profile(settings, "laptop")["profile_name"] == "laptop"
    deleted = delete_profile(settings, "office")
    assert deleted["ok"] is True
    assert delete_profile(load_persisted_settings(), "laptop")["ok"] is False
    assert activate_profile(load_persisted_settings(), "default")["profile_name"] == "default"
    assert delete_profile(load_persisted_settings(), "laptop")["ok"] is True


def test_update_panel_settings(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    result = update_panel_settings(
        settings,
        {
            "snap_radius_px": 75.0,
            "camera_index": 1,
            "gaze_mode": "gaze_only",
            "pause_hotkey": "ctrl+shift+o",
        },
    )
    assert result["snap_radius_px"] == 75.0
    assert result["camera_index"] == 1
    assert result["gaze_mode"] == "gaze_only"
    assert result["pause_hotkey"] == "ctrl+shift+o"
