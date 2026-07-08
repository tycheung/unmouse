from unmouse.config import Settings
from unmouse.gaze.calibration import fit_calibration
from unmouse.gaze.display import DisplayMapper, MonitorInfo, VirtualDesktop
from unmouse.gaze.pipeline import GazePipeline
from unmouse.gaze.tracker import GazeResult


def _settings() -> Settings:
    return Settings(screen_width=1920, screen_height=1080, saccade_threshold_px=50.0)


def test_pipeline_applies_calibration_and_clips() -> None:
    points = [
        (0.0, 0.0, 100.0, 100.0),
        (0.5, 0.0, 1060.0, 100.0),
        (1.0, 0.0, 2020.0, 100.0),
        (0.0, 0.5, 100.0, 640.0),
        (0.5, 0.5, 1060.0, 640.0),
        (1.0, 0.5, 2020.0, 640.0),
        (0.0, 1.0, 100.0, 980.0),
        (0.5, 1.0, 1060.0, 980.0),
        (1.0, 1.0, 2020.0, 980.0),
    ]
    model = fit_calibration(points)
    desktop = VirtualDesktop(
        monitors=(MonitorInfo(0, 0, 1920, 1080),),
        left=0,
        top=0,
        width=1920,
        height=1080,
    )
    pipeline = GazePipeline(
        _settings(),
        calibration=model,
        display=DisplayMapper(desktop),
    )
    out = pipeline.process(GazeResult(x=1.0, y=1.0, confidence=0.95))
    assert 0.0 <= out.x <= 1919.0
    assert 0.0 <= out.y <= 1079.0
    assert out.confidence == 0.95


def test_pipeline_bypasses_kalman_on_saccade() -> None:
    pipeline = GazePipeline(_settings())
    pipeline.process(GazeResult(x=100.0, y=100.0, confidence=1.0))
    out = pipeline.process(GazeResult(x=900.0, y=900.0, confidence=1.0))
    assert out.saccade is True
    assert out.x == 900.0
    assert out.y == 900.0
