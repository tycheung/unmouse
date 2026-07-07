"""JavaScript ↔ Python bridge for the control panel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from unmouse.config import Settings
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.settings import (
    activate_profile,
    create_profile,
    delete_profile,
    get_panel_settings,
    load_persisted_settings,
    rename_profile,
    update_panel_settings,
)
from unmouse.launcher.update import UpdateStatus, apply_update, check_updates

PanelView = Literal["main", "settings", "onboarding"]


@dataclass(frozen=True)
class PanelStatus:
    message: str
    fps: float | None = None
    confidence: float | None = None
    tracking: bool = False


@dataclass(frozen=True)
class PanelActionResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class UpdateCheckResult:
    available: bool
    message: str
    version: str | None = None
    channel: str = "none"
    current_version: str | None = None
    latest_version: str | None = None
    download_url: str | None = None

    @classmethod
    def from_status(cls, status: UpdateStatus) -> UpdateCheckResult:
        return cls(
            available=status.available,
            message=status.message,
            version=status.latest_version,
            channel=status.channel,
            current_version=status.current_version,
            latest_version=status.latest_version,
            download_url=status.download_url,
        )


class PanelApi:
    """Methods exposed to Alpine.js through pywebview's js_api."""

    def __init__(
        self,
        settings: Settings | None = None,
        onboarding: OnboardingController | None = None,
    ) -> None:
        self._settings = settings or load_persisted_settings()
        self._onboarding = onboarding or OnboardingController.create(self._settings)
        self._view: PanelView = "main"
        self._status = PanelStatus(message="Ready")
        self._update_status: UpdateStatus | None = None
        if self._onboarding.should_show_on_startup():
            self._view = "onboarding"

    @property
    def view(self) -> PanelView:
        return self._view

    def get_status(self) -> dict[str, object]:
        return asdict(self._status)

    def get_view(self) -> dict[str, str]:
        return {"view": self._view}

    def get_onboarding_state(self) -> dict[str, object]:
        return self._onboarding.get_state()

    def onboarding_advance(self) -> dict[str, object]:
        result = self._onboarding.advance()
        if result.get("ok") and self._onboarding.current_step.id == "ready":
            self._status = PanelStatus(message="Setup complete")
        return result

    def onboarding_skip(self, confirmed: bool = False) -> dict[str, object]:
        return self._onboarding.skip_current_step(confirmed=confirmed)

    def onboarding_check_camera(self) -> dict[str, object]:
        result = self._onboarding.check_camera()
        if result.get("ok"):
            self._status = PanelStatus(message=str(result.get("message", "Camera OK")))
        return result

    def onboarding_run_polynomial(self) -> dict[str, object]:
        result = self._onboarding.run_polynomial_step()
        if result.get("ok"):
            self._status = PanelStatus(message=str(result.get("message", "Calibration saved")))
        return result

    def onboarding_run_offset(self) -> dict[str, object]:
        return self._onboarding.run_offset_step()

    def onboarding_run_gestures(self) -> dict[str, object]:
        return self._onboarding.run_gestures_step()

    def onboarding_complete(self) -> dict[str, object]:
        result = self._onboarding.complete()
        self._view = "main"
        self._status = PanelStatus(message="Ready")
        return result

    def check_for_updates(self) -> dict[str, object]:
        self._update_status = check_updates()
        result = UpdateCheckResult.from_status(self._update_status)
        return asdict(result)

    def apply_update(self) -> dict[str, object]:
        if self._update_status is None or not self._update_status.available:
            result = PanelActionResult(ok=False, message="No update is available.")
            return asdict(result)
        self._update_status = apply_update(self._update_status)
        self._status = PanelStatus(message=self._update_status.message)
        result = PanelActionResult(
            ok=not self._update_status.available,
            message=self._update_status.message,
        )
        payload = asdict(result)
        payload["update"] = asdict(UpdateCheckResult.from_status(self._update_status))
        return payload

    def start_calibrate(self) -> dict[str, object]:
        from unmouse.gaze.calibration import calibration_path, load_calibration
        from unmouse.launcher.calibrate_wizard import run_offset_wizard
        from unmouse.launcher.polynomial_wizard import run_polynomial_wizard

        if load_calibration(calibration_path(self._settings)) is None:
            poly = run_polynomial_wizard(self._settings)
            if not poly.success:
                result = PanelActionResult(ok=False, message=poly.message)
                return asdict(result)
        outcome = run_offset_wizard(self._settings)
        self._status = PanelStatus(message=outcome.message)
        result = PanelActionResult(ok=outcome.success, message=outcome.message)
        return asdict(result)

    def start_launch(self) -> dict[str, object]:
        result = PanelActionResult(
            ok=False,
            message="Engine launch will spawn the tracking process in a future epic.",
        )
        return asdict(result)

    def show_settings(self) -> dict[str, str]:
        self._view = "settings"
        return {"view": self._view}

    def get_settings_panel(self) -> dict[str, object]:
        return get_panel_settings(self._settings)

    def save_settings_panel(self, updates: dict[str, object]) -> dict[str, object]:
        snapshot = update_panel_settings(self._settings, updates)
        self._settings = load_persisted_settings()
        self._status = PanelStatus(message="Settings saved")
        return {"ok": True, "message": "Settings saved.", "settings": snapshot}

    def create_profile(self, name: str) -> dict[str, object]:
        try:
            return create_profile(self._settings, name)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def rename_profile(self, old_name: str, new_name: str) -> dict[str, object]:
        try:
            result = rename_profile(self._settings, old_name, new_name)
            if result.get("ok"):
                self._settings = load_persisted_settings()
            return result
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def delete_profile(self, name: str) -> dict[str, object]:
        try:
            return delete_profile(self._settings, name)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def activate_profile(self, name: str) -> dict[str, object]:
        try:
            result = activate_profile(self._settings, name)
            if result.get("ok"):
                self._settings = load_persisted_settings()
            return result
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

    def show_onboarding(self) -> dict[str, str]:
        self._view = "onboarding"
        return {"view": self._view}

    def show_main(self) -> dict[str, str]:
        self._view = "main"
        return {"view": self._view}

    def set_status_message(self, message: str) -> dict[str, object]:
        self._status = PanelStatus(
            message=message,
            fps=self._status.fps,
            confidence=self._status.confidence,
            tracking=self._status.tracking,
        )
        return asdict(self._status)
