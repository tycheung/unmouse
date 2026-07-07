"""End-to-end gaze signal processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from unmouse.config import Settings
from unmouse.gaze.calibration import CalibrationModel, apply_calibration
from unmouse.gaze.display import DisplayMapper, VirtualDesktop
from unmouse.gaze.kalman import GazeKalmanFilter
from unmouse.gaze.offset_profile import OffsetProfile, apply_offset_profile
from unmouse.gaze.quality import GazeQualityGate, QualityOutput
from unmouse.gaze.saccade import is_saccade
from unmouse.gaze.tracker import GazeResult


@dataclass(frozen=True)
class PipelineOutput:
    x: float
    y: float
    confidence: float
    head_pose_ok: bool
    recalibrate_hint: bool
    saccade: bool


class GazePipeline:
    def __init__(
        self,
        settings: Settings,
        calibration: CalibrationModel | None = None,
        display: DisplayMapper | None = None,
        offset_profile: OffsetProfile | None = None,
    ) -> None:
        self._settings = settings
        self._calibration = calibration
        self._offset_profile = offset_profile
        self._quality = GazeQualityGate(
            confidence_min=settings.gaze_confidence_min,
            head_pose_drift_deg=settings.head_pose_drift_deg,
            drift_dwell_s=settings.head_pose_drift_dwell_s,
        )
        desktop = display.desktop if display else VirtualDesktop.from_settings(settings)
        self._display = display or DisplayMapper(desktop)
        self._kalman = GazeKalmanFilter(
            initial_x=settings.screen_width / 2,
            initial_y=settings.screen_height / 2,
            measurement_noise=settings.kalman_measurement_noise,
            process_noise=settings.kalman_process_noise,
        )
        self._last_x = settings.screen_width / 2
        self._last_y = settings.screen_height / 2

    def process(self, result: GazeResult) -> PipelineOutput:
        cal_x, cal_y = apply_calibration(result.x, result.y, self._calibration)
        quality_in = GazeResult(
            x=cal_x,
            y=cal_y,
            confidence=result.confidence,
            head_yaw_deg=result.head_yaw_deg,
        )
        quality: QualityOutput = self._quality.process(quality_in)

        saccade = is_saccade(
            quality.x,
            quality.y,
            self._last_x,
            self._last_y,
            self._settings.saccade_threshold_px,
        )
        if saccade:
            self._kalman.reset(quality.x, quality.y)
            smooth_x, smooth_y = quality.x, quality.y
        else:
            smooth_x, smooth_y = self._kalman.update(quality.x, quality.y)

        offset_x, offset_y = apply_offset_profile(smooth_x, smooth_y, self._offset_profile)
        mapped_x, mapped_y = self._display.map_point(offset_x, offset_y)
        self._last_x = mapped_x
        self._last_y = mapped_y

        return PipelineOutput(
            x=mapped_x,
            y=mapped_y,
            confidence=quality.confidence,
            head_pose_ok=quality.head_pose_ok,
            recalibrate_hint=quality.recalibrate_hint,
            saccade=saccade,
        )
