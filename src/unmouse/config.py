from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GazeMode(str, Enum):
    CURSOR_FOLLOW = "cursor_follow"
    GAZE_ONLY = "gaze_only"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UNMOUSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    screen_width: int = Field(default=1920, ge=1)
    screen_height: int = Field(default=1080, ge=1)

    pinch_threshold: float = Field(default=0.03, gt=0)
    v_sign_log_likelihood_min: float = -800.0
    v_sign_loss_debounce_ms: int = Field(default=300, ge=0)
    mle_margin_min: float = Field(default=5.0, ge=0)
    mle_absolute_min: float = -800.0
    scroll_activation_delay_ms: int = Field(default=500, ge=0)
    scroll_release_debounce_ms: int = Field(default=200, ge=0)
    snap_radius_px: float = Field(default=50.0, gt=0)

    camera_index: int = Field(default=0, ge=0)
    camera_width: int = Field(default=640, ge=160)
    camera_height: int = Field(default=480, ge=120)

    debug: bool = False
    draw_hand_skeleton: bool = False
    gaze_mode: GazeMode = GazeMode.CURSOR_FOLLOW
    paused: bool = False
    pyautogui_failsafe: bool = False
    profile_name: str = "default"
    pause_hotkey: str = "ctrl+shift+p"

    broker_queue_size: int = Field(default=2, ge=1, le=8)

    gaze_calibration_points: int = Field(default=25, ge=4, le=64)
    gaze_calibration_radius: int = Field(default=1000, gt=0)
    fixation_threshold: float = Field(default=1.0, gt=0.0, le=1.0)
    scroll_speed_multiplier: float = Field(default=1.0, gt=0)

    @property
    def app_data_dir(self) -> Path:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / ".unmouse"
        return base / "unmouse"

    @property
    def profile_dir(self) -> Path:
        return self.app_data_dir / "profiles" / self.profile_name

    @property
    def logs_dir(self) -> Path:
        return self.app_data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
