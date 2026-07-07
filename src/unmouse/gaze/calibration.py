"""Second-degree polynomial gaze-to-screen calibration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from unmouse.config import Settings

PointPair = tuple[float, float, float, float]


@dataclass(frozen=True)
class CalibrationModel:
    x_coeffs: tuple[float, ...]
    y_coeffs: tuple[float, ...]

    def to_dict(self) -> dict[str, list[float]]:
        return {"x_coeffs": list(self.x_coeffs), "y_coeffs": list(self.y_coeffs)}

    @classmethod
    def from_dict(cls, data: dict[str, list[float]]) -> CalibrationModel:
        return cls(x_coeffs=tuple(data["x_coeffs"]), y_coeffs=tuple(data["y_coeffs"]))


def _design_matrix(
    raw_x: npt.NDArray[np.float64], raw_y: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    return np.column_stack(
        [
            np.ones_like(raw_x),
            raw_x,
            raw_y,
            raw_x**2,
            raw_x * raw_y,
            raw_y**2,
        ]
    )


def fit_calibration(points: list[PointPair]) -> CalibrationModel:
    if len(points) < 6:
        msg = "At least 6 point pairs required for 2nd-degree polynomial fit"
        raise ValueError(msg)
    raw_x = np.array([p[0] for p in points], dtype=float)
    raw_y = np.array([p[1] for p in points], dtype=float)
    screen_x = np.array([p[2] for p in points], dtype=float)
    screen_y = np.array([p[3] for p in points], dtype=float)
    design = _design_matrix(raw_x, raw_y)
    x_coeffs, _, _, _ = np.linalg.lstsq(design, screen_x, rcond=None)
    y_coeffs, _, _, _ = np.linalg.lstsq(design, screen_y, rcond=None)
    return CalibrationModel(x_coeffs=tuple(x_coeffs.tolist()), y_coeffs=tuple(y_coeffs.tolist()))


def apply_calibration(
    raw_x: float, raw_y: float, model: CalibrationModel | None
) -> tuple[float, float]:
    if model is None:
        return raw_x, raw_y
    features = np.array([1.0, raw_x, raw_y, raw_x**2, raw_x * raw_y, raw_y**2])
    screen_x = float(np.dot(features, np.array(model.x_coeffs)))
    screen_y = float(np.dot(features, np.array(model.y_coeffs)))
    return screen_x, screen_y


def mean_residual_error(points: list[PointPair], model: CalibrationModel) -> float:
    errors: list[float] = []
    for raw_x, raw_y, target_x, target_y in points:
        pred_x, pred_y = apply_calibration(raw_x, raw_y, model)
        errors.append(np.hypot(pred_x - target_x, pred_y - target_y))
    return float(np.mean(errors))


def save_calibration(path: Path, model: CalibrationModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), indent=2), encoding="utf-8")


def load_calibration(path: Path) -> CalibrationModel | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return CalibrationModel.from_dict(data)


def calibration_path(settings: Settings) -> Path:
    return settings.profile_dir / "calibration.json"
