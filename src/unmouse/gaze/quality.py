"""Gaze quality gate: confidence hold and head-pose drift detection."""

from __future__ import annotations

import time
from dataclasses import dataclass

from unmouse.gaze.tracker import GazeResult


@dataclass
class QualityOutput:
    x: float
    y: float
    confidence: float
    head_pose_ok: bool
    recalibrate_hint: bool
    hold_active: bool


class GazeQualityGate:
    def __init__(
        self,
        confidence_min: float = 0.4,
        head_pose_drift_deg: float = 15.0,
        drift_dwell_s: float = 2.0,
    ) -> None:
        self._confidence_min = confidence_min
        self._head_pose_drift_deg = head_pose_drift_deg
        self._drift_dwell_s = drift_dwell_s
        self._last_good_x = 0.0
        self._last_good_y = 0.0
        self._drift_started_at: float | None = None

    def process(self, result: GazeResult) -> QualityOutput:
        now = time.monotonic()
        head_pose_ok = abs(result.head_yaw_deg) <= self._head_pose_drift_deg
        if not head_pose_ok:
            if self._drift_started_at is None:
                self._drift_started_at = now
        else:
            self._drift_started_at = None

        drift_elapsed = 0.0 if self._drift_started_at is None else now - self._drift_started_at
        recalibrate_hint = not head_pose_ok and drift_elapsed >= self._drift_dwell_s

        if result.confidence >= self._confidence_min and head_pose_ok:
            self._last_good_x = result.x
            self._last_good_y = result.y
            return QualityOutput(
                x=result.x,
                y=result.y,
                confidence=result.confidence,
                head_pose_ok=True,
                recalibrate_hint=recalibrate_hint,
                hold_active=False,
            )

        return QualityOutput(
            x=self._last_good_x,
            y=self._last_good_y,
            confidence=result.confidence,
            head_pose_ok=head_pose_ok,
            recalibrate_hint=recalibrate_hint,
            hold_active=True,
        )
