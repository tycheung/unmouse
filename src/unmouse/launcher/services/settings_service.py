"""Settings and profile panel operations."""

from __future__ import annotations

from unmouse.launcher.api_helpers import action
from unmouse.launcher.services.panel_state import PanelState, PanelStatus
from unmouse.launcher.settings import (
    activate_profile,
    create_profile,
    delete_profile,
    get_panel_settings,
    rename_profile,
    update_panel_settings,
)
from unmouse.persistence import load_persisted_settings


class SettingsService:
    def __init__(self, state: PanelState) -> None:
        self._state = state

    def get_panel(self) -> dict[str, object]:
        return get_panel_settings(self._state.settings)

    def save_panel(self, updates: dict[str, object]) -> dict[str, object]:
        snapshot = update_panel_settings(self._state.settings, updates)
        self._state.settings = load_persisted_settings()
        self._state.status = PanelStatus(message="Settings saved")
        return {"ok": True, "message": "Settings saved.", "settings": snapshot}

    def create_profile(self, name: str) -> dict[str, object]:
        try:
            return create_profile(self._state.settings, name)
        except ValueError as exc:
            return action(False, str(exc))

    def rename_profile(self, old_name: str, new_name: str) -> dict[str, object]:
        try:
            result = rename_profile(self._state.settings, old_name, new_name)
            if result.get("ok"):
                self._state.settings = load_persisted_settings()
            return result
        except ValueError as exc:
            return action(False, str(exc))

    def delete_profile(self, name: str) -> dict[str, object]:
        try:
            return delete_profile(self._state.settings, name)
        except ValueError as exc:
            return action(False, str(exc))

    def activate_profile(self, name: str) -> dict[str, object]:
        try:
            result = activate_profile(self._state.settings, name)
            if result.get("ok"):
                self._state.settings = load_persisted_settings()
            return result
        except ValueError as exc:
            return action(False, str(exc))
