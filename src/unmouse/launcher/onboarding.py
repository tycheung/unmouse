"""First-run onboarding orchestration and launcher settings persistence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from unmouse.config import Settings
from unmouse.gaze.offset_profile import load_offset_profile, offset_profile_path
from unmouse.gestures.enrollment import DEFAULT_GESTURE_NAMES, profile_gestures_dir

OnboardingStepId = Literal["welcome", "camera", "polynomial", "offset", "gestures", "ready"]
SETTINGS_FILENAME = "settings.json"
SKIP_WARNING = (
    "Skipping this step may reduce tracking accuracy. "
    "You can rerun setup later from Calibrate or Settings."
)


@dataclass
class LauncherSettings:
    first_run_complete: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LauncherSettings:
        return cls(first_run_complete=bool(data.get("first_run_complete", False)))


@dataclass(frozen=True)
class OnboardingStep:
    id: OnboardingStepId
    title: str
    description: str
    skippable: bool = False


_STEP_DATA: tuple[tuple[OnboardingStepId, str, str, bool], ...] = (
    ("welcome", "Welcome to unmouse", "Quick setup for webcam gaze and gestures.", False),
    ("camera", "Camera check", "Verify your webcam before calibrating.", False),
    ("polynomial", "9-point calibration", "Follow nine targets to map gaze to screen.", True),
    ("offset", "Offset calibration", "Sixteen-point offset correction (Epic 37 hook).", True),
    ("gestures", "Gesture enrollment", "Train V-sign, pinch, thumbs-up (Epic 38 hook).", True),
    ("ready", "Ready to launch", "Finish setup, then use Launch to track.", False),
)
ONBOARDING_STEPS = tuple(
    OnboardingStep(step_id, title, description, skippable=skippable)
    for step_id, title, description, skippable in _STEP_DATA
)


@dataclass(frozen=True)
class CameraCheckResult:
    ok: bool
    message: str
    frames_read: int = 0
    frame_rate_hz: float | None = None


@dataclass(frozen=True)
class OnboardingActionResult:
    ok: bool
    message: str
    step_complete: bool = False


def launcher_settings_path(settings: Settings) -> Path:
    return settings.app_data_dir / SETTINGS_FILENAME


def load_launcher_settings(settings: Settings) -> LauncherSettings:
    path = launcher_settings_path(settings)
    if not path.is_file():
        return LauncherSettings()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "launcher settings JSON must be an object"
        raise ValueError(msg)
    return LauncherSettings.from_dict(data)


def save_launcher_settings(settings: Settings, launcher_settings: LauncherSettings) -> Path:
    path = launcher_settings_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"first_run_complete": launcher_settings.first_run_complete}, indent=2),
        encoding="utf-8",
    )
    return path


@dataclass
class OnboardingController:
    settings: Settings
    step_index: int = 0
    skipped_steps: list[OnboardingStepId] = field(default_factory=list)
    camera_checked: bool = False
    polynomial_complete: bool = False
    offset_complete: bool = False
    gestures_complete: bool = False
    _check_camera: Callable[[Settings], CameraCheckResult] | None = None
    _run_polynomial: Callable[[Settings], OnboardingActionResult] | None = None
    _run_offset: Callable[[Settings], OnboardingActionResult] | None = None
    _run_gestures: Callable[[Settings], OnboardingActionResult] | None = None

    @classmethod
    def create(
        cls,
        settings: Settings | None = None,
        *,
        check_camera: Callable[[Settings], CameraCheckResult] | None = None,
        run_polynomial: Callable[[Settings], OnboardingActionResult] | None = None,
        run_offset: Callable[[Settings], OnboardingActionResult] | None = None,
        run_gestures: Callable[[Settings], OnboardingActionResult] | None = None,
    ) -> OnboardingController:
        return cls(
            settings=settings or Settings(),
            _check_camera=check_camera,
            _run_polynomial=run_polynomial,
            _run_offset=run_offset,
            _run_gestures=run_gestures,
        )

    @property
    def current_step(self) -> OnboardingStep:
        return ONBOARDING_STEPS[self.step_index]

    def should_show_on_startup(self) -> bool:
        return not load_launcher_settings(self.settings).first_run_complete

    def get_state(self) -> dict[str, object]:
        step = self.current_step
        return {
            "should_show": self.should_show_on_startup(),
            "first_run_complete": load_launcher_settings(self.settings).first_run_complete,
            "step_id": step.id,
            "step_index": self.step_index,
            "step_count": len(ONBOARDING_STEPS),
            "title": step.title,
            "description": step.description,
            "skippable": step.skippable,
            "skip_warning": SKIP_WARNING if step.skippable else "",
            "notice": self._step_notice(step.id),
            "actions": self._actions_for_step(step.id),
            "skipped_steps": list(self.skipped_steps),
        }

    def advance(self) -> dict[str, object]:
        step = self.current_step
        if step.id == "camera" and not self.camera_checked:
            return asdict(OnboardingActionResult(ok=False, message="Run the camera check first."))
        if step.id == "ready":
            return self.complete()
        self.step_index = min(self.step_index + 1, len(ONBOARDING_STEPS) - 1)
        return {"ok": True, "state": self.get_state()}

    def skip_current_step(self, *, confirmed: bool) -> dict[str, object]:
        step = self.current_step
        if not step.skippable:
            return asdict(OnboardingActionResult(ok=False, message="This step cannot be skipped."))
        if not confirmed:
            return asdict(
                OnboardingActionResult(ok=False, message="Confirm the skip warning first.")
            )
        if step.id not in self.skipped_steps:
            self.skipped_steps.append(step.id)
        self.step_index = min(self.step_index + 1, len(ONBOARDING_STEPS) - 1)
        return {"ok": True, "state": self.get_state()}

    def check_camera(self) -> dict[str, object]:
        result = (self._check_camera or default_camera_check)(self.settings)
        self.camera_checked = result.ok
        return {**asdict(result), "state": self.get_state()}

    def run_polynomial_step(self) -> dict[str, object]:
        return self._run_hook(self._run_polynomial, default_polynomial_step, "polynomial_complete")

    def run_offset_step(self) -> dict[str, object]:
        return self._run_hook(self._run_offset, default_offset_step, "offset_complete")

    def run_gestures_step(self) -> dict[str, object]:
        return self._run_hook(self._run_gestures, default_gestures_step, "gestures_complete")

    def complete(self) -> dict[str, object]:
        save_launcher_settings(self.settings, LauncherSettings(first_run_complete=True))
        return {"ok": True, "message": "First-run setup complete.", "state": self.get_state()}

    def _run_hook(
        self,
        override: Callable[[Settings], OnboardingActionResult] | None,
        default: Callable[[Settings], OnboardingActionResult],
        flag: str,
    ) -> dict[str, object]:
        result = (override or default)(self.settings)
        if result.ok:
            setattr(self, flag, True)
        return {**asdict(result), "state": self.get_state()}

    def _step_notice(self, step_id: OnboardingStepId) -> str:
        if step_id == "camera" and self.camera_checked:
            return "Camera check passed."
        if step_id == "polynomial" and self.polynomial_complete:
            return "Polynomial calibration saved."
        if step_id == "offset" and self.offset_complete:
            return "Offset profile saved."
        if step_id == "gestures" and self.gestures_complete:
            return "Gesture templates saved."
        return ""

    def _actions_for_step(self, step_id: OnboardingStepId) -> list[dict[str, object]]:
        specs: dict[OnboardingStepId, list[tuple[str, str, bool, bool]]] = {
            "welcome": [("next", "Get started", True, True)],
            "camera": [
                ("check_camera", "Test camera", False, True),
                ("next", "Continue", True, self.camera_checked),
            ],
            "polynomial": [
                ("run_polynomial", "Start 9-point calibration", False, True),
                ("next", "Continue", True, True),
            ],
            "offset": [
                ("run_offset", "Start offset calibration", False, True),
                ("next", "Continue", True, True),
            ],
            "gestures": [
                ("run_gestures", "Enroll gestures", False, True),
                ("next", "Continue", True, True),
            ],
            "ready": [("finish", "Finish setup", True, True)],
        }
        return [
            {"id": action_id, "label": label, "primary": primary, "enabled": enabled}
            for action_id, label, primary, enabled in specs[step_id]
        ]


def default_camera_check(settings: Settings) -> CameraCheckResult:
    import time

    import cv2

    capture = cv2.VideoCapture(settings.camera_index)
    if not capture.isOpened():
        return CameraCheckResult(
            ok=False,
            message=f"Unable to open camera {settings.camera_index}.",
        )
    frames = 0
    started = time.perf_counter()
    try:
        for _ in range(15):
            ok, _ = capture.read()
            if ok:
                frames += 1
    finally:
        capture.release()
    fps = frames / max(time.perf_counter() - started, 1e-6)
    if frames < 3:
        return CameraCheckResult(
            ok=False,
            message="Camera returned too few frames.",
            frames_read=frames,
        )
    return CameraCheckResult(
        ok=True,
        message=f"Camera OK (~{fps:.0f} Hz).",
        frames_read=frames,
        frame_rate_hz=fps,
    )


def default_polynomial_step(settings: Settings) -> OnboardingActionResult:
    from unmouse.launcher.polynomial_wizard import run_polynomial_wizard

    outcome = run_polynomial_wizard(settings)
    return OnboardingActionResult(outcome.success, outcome.message, step_complete=outcome.success)


FUTURE_HOOK_MSG = "coming in a future update. Skip to continue."


def default_offset_step(settings: Settings) -> OnboardingActionResult:
    if load_offset_profile(offset_profile_path(settings)) is not None:
        return OnboardingActionResult(True, "Offset profile already saved.", step_complete=True)
    return OnboardingActionResult(False, f"16-point offset calibration UI is {FUTURE_HOOK_MSG}")


def default_gestures_step(settings: Settings) -> OnboardingActionResult:
    gestures_dir = profile_gestures_dir(settings.profile_dir)
    if gestures_dir.is_dir() and all(
        (gestures_dir / f"{name}.json").is_file() for name in DEFAULT_GESTURE_NAMES
    ):
        return OnboardingActionResult(True, "Gesture templates already saved.", step_complete=True)
    return OnboardingActionResult(False, f"Gesture enrollment UI is {FUTURE_HOOK_MSG}")
