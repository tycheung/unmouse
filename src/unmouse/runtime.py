"""Shared runtime flags synchronized between launcher and engine."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from unmouse.config import Settings

RUNTIME_FILENAME = "runtime.json"


@dataclass
class RuntimeState:
    paused: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RuntimeState:
        return cls(paused=bool(data.get("paused", False)))


def runtime_file_path(settings: Settings) -> Path:
    return settings.app_data_dir / RUNTIME_FILENAME


def load_runtime(settings: Settings) -> RuntimeState:
    path = runtime_file_path(settings)
    if not path.is_file():
        return RuntimeState()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "runtime JSON must be an object"
        raise ValueError(msg)
    return RuntimeState.from_dict(data)


def save_runtime(settings: Settings, state: RuntimeState) -> Path:
    path = runtime_file_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
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
    from unmouse.persistence import load_persisted_settings

    settings.paused = load_runtime(settings).paused
    persisted = load_persisted_settings()
    settings.gaze_mode = persisted.gaze_mode
    settings.pause_hotkey = persisted.pause_hotkey
