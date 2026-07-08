from pathlib import Path

import pytest

from unmouse.config import GazeMode, Settings, clear_settings_cache, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_default_settings() -> None:
    settings = Settings()
    assert settings.saccade_threshold_px == 80.0
    assert settings.gaze_mode is GazeMode.CURSOR_FOLLOW
    assert settings.pyautogui_failsafe is False
    assert settings.broker_queue_size == 2


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNMOUSE_SACCADE_THRESHOLD_PX", "120")
    monkeypatch.setenv("UNMOUSE_GAZE_MODE", "gaze_only")
    monkeypatch.setenv("UNMOUSE_DEBUG", "true")
    clear_settings_cache()
    settings = Settings()
    assert settings.saccade_threshold_px == 120.0
    assert settings.gaze_mode is GazeMode.GAZE_ONLY
    assert settings.debug is True


def test_profile_dir_uses_app_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", "C:\\Users\\test\\AppData\\Roaming")
    settings = Settings(profile_name="desk")
    expected = Path("C:/Users/test/AppData/Roaming/unmouse/profiles/desk")
    assert settings.profile_dir == expected


def test_get_settings_cached() -> None:
    assert get_settings() is get_settings()
