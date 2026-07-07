"""Pipeline integration with offset profile correction."""

from unmouse.config import Settings
from unmouse.gaze.offset_profile import build_calibration_targets, build_profile_from_measurements
from unmouse.gaze.pipeline import GazePipeline
from unmouse.gaze.tracker import GazeResult


def test_pipeline_applies_offset_profile_after_kalman() -> None:
    settings = Settings(screen_width=800, screen_height=600, saccade_threshold_px=50.0)
    targets = build_calibration_targets(800.0, 600.0)
    measurements = tuple((tx - 10.0, ty - 5.0) for tx, ty in targets)
    profile = build_profile_from_measurements(800.0, 600.0, measurements)
    pipeline = GazePipeline(settings, offset_profile=profile)
    pipeline.process(GazeResult(x=400.0, y=300.0, confidence=1.0))
    out = pipeline.process(GazeResult(x=400.0, y=300.0, confidence=1.0))
    assert out.x == 410.0
    assert out.y == 305.0
