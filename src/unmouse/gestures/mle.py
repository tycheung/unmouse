from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from unmouse.utils.json_io import read_json_object_or_none, write_json_object

DEFAULT_RIDGE_LAMBDA = 1e-4


@dataclass(frozen=True)
class GestureTemplate:
    name: str
    mu: npt.NDArray[np.float64]
    inv_variances: npt.NDArray[np.float64]
    log_det: float

    def __post_init__(self) -> None:
        if len(self.mu) != len(self.inv_variances):
            msg = "mu and inv_variances must have the same length"
            raise ValueError(msg)

    @property
    def dim(self) -> int:
        return len(self.mu)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "mu": self.mu.tolist(),
            "variances": (1.0 / self.inv_variances).tolist(),
            "log_det": self.log_det,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GestureTemplate:
        mu = np.asarray(data["mu"], dtype=np.float64)
        variances = np.asarray(data["variances"], dtype=np.float64)
        raw_log_det = data.get("log_det")
        log_det = (
            float(raw_log_det)
            if isinstance(raw_log_det, int | float)
            else float(np.sum(np.log(variances)))
        )
        return cls(
            name=str(data["name"]),
            mu=mu,
            inv_variances=1.0 / variances,
            log_det=log_det,
        )


@dataclass(frozen=True)
class ClassificationResult:
    gesture: str | None
    log_likelihood: float
    margin: float
    runner_up: str | None


GestureLibrary = dict[str, GestureTemplate]


def build_template(
    name: str,
    samples: npt.NDArray[np.float64],
    *,
    ridge_lambda: float = DEFAULT_RIDGE_LAMBDA,
) -> GestureTemplate:
    """Fit a diagonal Gaussian template with ridge-regularized variances."""
    if samples.ndim != 2:
        msg = "samples must be a 2D array"
        raise ValueError(msg)
    n_samples, n_features = samples.shape
    if n_features == 0:
        msg = "samples must contain at least one feature"
        raise ValueError(msg)

    mu = np.mean(samples, axis=0)
    if n_samples > 1:
        variances = np.var(samples, axis=0, ddof=1) + ridge_lambda
    else:
        variances = np.full(n_features, ridge_lambda, dtype=np.float64)
    return GestureTemplate(
        name=name,
        mu=np.asarray(mu, dtype=np.float64),
        inv_variances=np.asarray(1.0 / variances, dtype=np.float64),
        log_det=float(np.sum(np.log(variances))),
    )


def log_likelihood(theta: npt.NDArray[np.float64], template: GestureTemplate) -> float:
    delta = np.asarray(theta, dtype=np.float64) - template.mu
    mahalanobis = float(np.dot(delta * delta, template.inv_variances))
    return -0.5 * mahalanobis - 0.5 * template.log_det


def classify(
    theta: npt.NDArray[np.float64],
    templates: Mapping[str, GestureTemplate],
    *,
    absolute_min: float,
    margin_min: float,
) -> ClassificationResult:
    """Return the best gesture if absolute and margin thresholds pass."""
    feature = np.asarray(theta, dtype=np.float64)
    scored = [
        (name, log_likelihood(feature, template))
        for name, template in templates.items()
        if template.dim == feature.size
    ]
    if not scored:
        return ClassificationResult(
            gesture=None,
            log_likelihood=-math.inf,
            margin=0.0,
            runner_up=None,
        )

    scored.sort(key=lambda item: item[1], reverse=True)
    best_name, best_log = scored[0]
    runner_name = scored[1][0] if len(scored) > 1 else None
    runner_log = scored[1][1] if len(scored) > 1 else -math.inf
    margin = best_log - runner_log

    passed = best_log > absolute_min and margin > margin_min
    return ClassificationResult(
        gesture=best_name if passed else None,
        log_likelihood=best_log,
        margin=margin,
        runner_up=runner_name,
    )


def save_template(path: Path, template: GestureTemplate, *, compact: bool = False) -> None:
    write_json_object(path, template.to_dict(), indent=None if compact else 2)


def load_template(path: Path) -> GestureTemplate | None:
    data = read_json_object_or_none(path, error_message="template JSON must be an object")
    if data is None:
        return None
    return GestureTemplate.from_dict(data)


def load_gesture_library(directory: Path) -> GestureLibrary:
    library: GestureLibrary = {}
    if not directory.is_dir():
        return library
    for path in sorted(directory.glob("*.json")):
        template = load_template(path)
        if template is not None:
            library[template.name] = template
    return library
