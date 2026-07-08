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
    log_det: float
    diagonal: bool
    precision: npt.NDArray[np.float64] | None = None
    inv_variances: npt.NDArray[np.float64] | None = None

    def __post_init__(self) -> None:
        if self.diagonal:
            if self.inv_variances is None:
                msg = "diagonal templates require inv_variances"
                raise ValueError(msg)
            if len(self.mu) != len(self.inv_variances):
                msg = "mu and inv_variances must have the same length"
                raise ValueError(msg)
        elif self.precision is None:
            msg = "full templates require precision"
            raise ValueError(msg)
        elif self.precision.shape != (len(self.mu), len(self.mu)):
            msg = "precision shape must match mu dimension"
            raise ValueError(msg)

    @property
    def dim(self) -> int:
        return len(self.mu)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "mu": self.mu.tolist(),
            "diagonal": self.diagonal,
            "log_det": self.log_det,
        }
        if self.diagonal:
            assert self.inv_variances is not None
            variances = 1.0 / self.inv_variances
            payload["variances"] = variances.tolist()
        else:
            assert self.precision is not None
            covariance = np.linalg.inv(self.precision)
            payload["covariance"] = covariance.tolist()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GestureTemplate:
        name = str(data["name"])
        mu = np.asarray(data["mu"], dtype=np.float64)
        diagonal = bool(data.get("diagonal", False))
        raw_log_det = data.get("log_det")
        log_det = float(raw_log_det) if isinstance(raw_log_det, int | float) else 0.0
        if diagonal:
            variances = np.asarray(data["variances"], dtype=np.float64)
            inv_variances = 1.0 / variances
            if raw_log_det is None:
                log_det = float(np.sum(np.log(variances)))
            return cls(
                name=name,
                mu=mu,
                log_det=log_det,
                diagonal=True,
                inv_variances=inv_variances,
            )
        covariance = np.asarray(data["covariance"], dtype=np.float64)
        precision = np.linalg.inv(covariance)
        if raw_log_det is None:
            sign, value = np.linalg.slogdet(covariance)
            if sign <= 0:
                msg = "covariance must be positive definite"
                raise ValueError(msg)
            log_det = float(value)
        return cls(
            name=name,
            mu=mu,
            log_det=log_det,
            diagonal=False,
            precision=precision,
        )


@dataclass(frozen=True)
class ClassificationResult:
    gesture: str | None
    log_likelihood: float
    margin: float
    runner_up: str | None


GestureLibrary = dict[str, GestureTemplate]


def fit_gaussian(
    samples: npt.NDArray[np.float64],
    *,
    ridge_lambda: float = DEFAULT_RIDGE_LAMBDA,
    force_diagonal: bool | None = None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], bool]:
    """Fit mean and (co)variance with ridge regularization."""
    if samples.ndim != 2:
        msg = "samples must be a 2D array"
        raise ValueError(msg)

    n_samples, n_features = samples.shape
    if n_features == 0:
        msg = "samples must contain at least one feature"
        raise ValueError(msg)

    mu = np.mean(samples, axis=0)
    centered = samples - mu
    use_diagonal = force_diagonal if force_diagonal is not None else n_samples < n_features

    if use_diagonal:
        if n_samples > 1:
            variances = np.var(centered, axis=0, ddof=1) + ridge_lambda
        else:
            variances = np.full(n_features, ridge_lambda, dtype=np.float64)
        return mu, variances, True

    if n_samples > 1:
        covariance = (centered.T @ centered) / (n_samples - 1)
        covariance = covariance + ridge_lambda * np.eye(n_features, dtype=np.float64)
    else:
        covariance = np.eye(n_features, dtype=np.float64) * ridge_lambda
    return mu, covariance, False


def build_template(
    name: str,
    samples: npt.NDArray[np.float64],
    *,
    ridge_lambda: float = DEFAULT_RIDGE_LAMBDA,
    force_diagonal: bool | None = None,
) -> GestureTemplate:
    mu, cov_or_var, diagonal = fit_gaussian(
        samples,
        ridge_lambda=ridge_lambda,
        force_diagonal=force_diagonal,
    )
    if diagonal:
        variances = cov_or_var
        inv_variances = 1.0 / variances
        log_det = float(np.sum(np.log(variances)))
        return GestureTemplate(
            name=name,
            mu=np.asarray(mu, dtype=np.float64),
            log_det=log_det,
            diagonal=True,
            inv_variances=np.asarray(inv_variances, dtype=np.float64),
        )

    sign, log_det_value = np.linalg.slogdet(cov_or_var)
    if sign <= 0:
        msg = "fitted covariance must be positive definite"
        raise ValueError(msg)
    precision = np.linalg.inv(cov_or_var)
    return GestureTemplate(
        name=name,
        mu=np.asarray(mu, dtype=np.float64),
        log_det=float(log_det_value),
        diagonal=False,
        precision=np.asarray(precision, dtype=np.float64),
    )


def log_likelihood(theta: npt.NDArray[np.float64], template: GestureTemplate) -> float:
    delta = np.asarray(theta, dtype=np.float64) - template.mu
    if template.diagonal:
        assert template.inv_variances is not None
        mahalanobis = float(np.dot(delta * delta, template.inv_variances))
    else:
        assert template.precision is not None
        mahalanobis = float(delta @ template.precision @ delta)
    return -0.5 * mahalanobis - 0.5 * template.log_det


def classify(
    theta: npt.NDArray[np.float64],
    templates: Mapping[str, GestureTemplate],
    *,
    absolute_min: float,
    margin_min: float,
) -> ClassificationResult:
    """Return the best gesture if absolute and margin thresholds pass."""
    if not templates:
        return ClassificationResult(
            gesture=None,
            log_likelihood=-math.inf,
            margin=0.0,
            runner_up=None,
        )

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

    if best_log <= absolute_min or margin <= margin_min:
        return ClassificationResult(
            gesture=None,
            log_likelihood=best_log,
            margin=margin,
            runner_up=runner_name,
        )
    return ClassificationResult(
        gesture=best_name,
        log_likelihood=best_log,
        margin=margin,
        runner_up=runner_name,
    )


def save_template(path: Path, template: GestureTemplate) -> None:
    write_json_object(path, template.to_dict())


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
