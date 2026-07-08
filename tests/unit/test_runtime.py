"""Unit tests for launcher/engine runtime flag sync."""

from __future__ import annotations

from unmouse.config import GazeMode, Settings
from unmouse.launcher.settings import save_persisted_settings
from unmouse.runtime import (
    RuntimeState,
    save_runtime,
    sync_engine_controls,
    toggle_paused,
)


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return Settings(screen_width=800, screen_height=600, profile_name="default")


def test_runtime_pause_round_trip(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    save_runtime(settings, RuntimeState(paused=True))
    assert toggle_paused(settings).paused is False


def test_sync_engine_controls_reads_runtime_and_settings(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    save_persisted_settings(
        settings.model_copy(
            update={"gaze_mode": GazeMode.GAZE_ONLY, "pause_hotkey": "ctrl+shift+o"},
        ),
    )
    save_runtime(settings, RuntimeState(paused=True))
    live = Settings(screen_width=800, screen_height=600)
    sync_engine_controls(live)
    assert live.paused is True
    assert live.gaze_mode is GazeMode.GAZE_ONLY
