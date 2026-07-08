"""First-run onboarding orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Literal

from unmouse.broker.camera import open_camera
from unmouse.config import Settings
from unmouse.gaze.offset_profile import load_offset_profile, offset_profile_path
from unmouse.launcher.api_helpers import ActionResult
from unmouse.launcher.settings import LauncherFlags, load_launcher_flags, save_launcher_flags

OnboardingStepId = Literal["welcome", "camera", "polynomial", "offset", "gestures", "ready"]
SKIP_WARNING = (
    "Skipping this step may reduce tracking accuracy. "
    "You can rerun setup later from Calibrate or Settings."
)


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
    ("offset", "Offset calibration", "Sixteen-point offset correction after polynomial fit.", True),
    (
        "gestures",
        "Gesture enrollment",
        "Train V-sign, pinch, and thumbs-up from the camera preview.",
        True,
    ),
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
    _run_polynomial: Callable[[Settings], ActionResult] | None = None
    _run_offset: Callable[[Settings], ActionResult] | None = None

    @classmethod
    def create(
        cls,
        settings: Settings | None = None,
        *,
        check_camera: Callable[[Settings], CameraCheckResult] | None = None,
        run_polynomial: Callable[[Settings], ActionResult] | None = None,
        run_offset: Callable[[Settings], ActionResult] | None = None,
    ) -> OnboardingController:
        return cls(
            settings=settings or Settings(),
            _check_camera=check_camera,
            _run_polynomial=run_polynomial,
            _run_offset=run_offset,
        )

    @property
    def current_step(self) -> OnboardingStep:
        return ONBOARDING_STEPS[self.step_index]

    def should_show_on_startup(self) -> bool:
        return not load_launcher_flags(self.settings).first_run_complete

    def get_state(self) -> dict[str, object]:
        step = self.current_step
        flags = load_launcher_flags(self.settings)
        return {
            "should_show": self.should_show_on_startup(),
            "first_run_complete": flags.first_run_complete,
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
            return ActionResult(False, "Run the camera check first.").to_dict()
        if step.id == "ready":
            return self.complete()
        self.step_index = min(self.step_index + 1, len(ONBOARDING_STEPS) - 1)
        return {"ok": True, "state": self.get_state()}

    def skip_current_step(self, *, confirmed: bool) -> dict[str, object]:
        step = self.current_step
        if not step.skippable:
            return ActionResult(False, "This step cannot be skipped.").to_dict()
        if not confirmed:
            return ActionResult(False, "Confirm the skip warning first.").to_dict()
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

    def complete(self) -> dict[str, object]:
        save_launcher_flags(
            self.settings,
            LauncherFlags(first_run_complete=True),
        )
        return {"ok": True, "message": "First-run setup complete.", "state": self.get_state()}

    def _run_hook(
        self,
        override: Callable[[Settings], ActionResult] | None,
        default: Callable[[Settings], ActionResult],
        flag: str,
    ) -> dict[str, object]:
        result = (override or default)(self.settings)
        if result.ok:
            setattr(self, flag, True)
        return {**result.to_dict(), "state": self.get_state()}

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

    try:
        capture = open_camera(settings.camera_index)
    except RuntimeError:
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


def default_polynomial_step(settings: Settings) -> ActionResult:
    from unmouse.launcher.calibration_wizards import run_polynomial_wizard

    outcome = run_polynomial_wizard(settings)
    return ActionResult(
        outcome.success,
        outcome.message,
        step_complete=outcome.success,
    )


def default_offset_step(settings: Settings) -> ActionResult:
    if load_offset_profile(offset_profile_path(settings)) is not None:
        return ActionResult(True, "Offset profile already saved.", step_complete=True)
    from unmouse.launcher.calibration_wizards import run_offset_wizard

    outcome = run_offset_wizard(settings)
    return ActionResult(outcome.success, outcome.message, step_complete=outcome.success)
