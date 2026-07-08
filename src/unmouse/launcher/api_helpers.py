from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from unmouse.config import Settings
from unmouse.launcher.update import UpdateStatus


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    step_complete: bool = False
    gesture: str | None = None
    sample_count: int = 0
    done: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def action(ok: bool, message: str, **extra: object) -> dict[str, object]:
    payload = ActionResult(ok, message).to_dict()
    payload.update(extra)
    return payload


def update_payload(status: UpdateStatus) -> dict[str, object]:
    payload = status.to_dict()
    payload["version"] = status.latest_version
    return payload


def last_calibration_label(settings: Settings) -> str | None:
    from unmouse.gaze.tracker import gaze_model_path

    path = gaze_model_path(settings)
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
