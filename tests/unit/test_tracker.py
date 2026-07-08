import numpy as np

from tests.fakes.gaze import FakeEyeGesturesEngine
from unmouse.config import Settings
from unmouse.gaze.tracker import (
    EyeGesturesTracker,
    calibration_map,
    create_gaze_tracker,
    gaze_model_path,
    load_gaze_model,
    save_gaze_model,
)

_FRAME = np.zeros((10, 10, 3), dtype=np.uint8)


def _tracker(engine: FakeEyeGesturesEngine, points: int = 9) -> EyeGesturesTracker:
    return EyeGesturesTracker(
        screen_width=800,
        screen_height=600,
        calibration_points=points,
        calibration_radius=1000,
        fixation_threshold=1.0,
        engine=engine,
    )


def test_tracker_uploads_calibration_map_and_fixation() -> None:
    engine = FakeEyeGesturesEngine()
    _tracker(engine, points=9)
    assert engine.uploaded is not None
    uploaded_points, context = engine.uploaded
    assert context == "unmouse"
    assert len(uploaded_points) == 9
    assert engine.fixation == 1.0


def test_tracker_maps_tracking_event_to_sample() -> None:
    engine = FakeEyeGesturesEngine()
    sample, target = _tracker(engine).step(_FRAME, calibrate=False)
    assert sample is not None
    assert (sample.x, sample.y) == (400.0, 300.0)
    assert sample.fixation == 0.9
    assert sample.saccade is True
    assert target is None


def test_tracker_returns_calibration_target_when_calibrating() -> None:
    engine = FakeEyeGesturesEngine()
    _sample, target = _tracker(engine).step(_FRAME, calibrate=True)
    assert target is not None
    assert (target.x, target.y) == (10.0, 20.0)


def test_tracker_save_and_load_model() -> None:
    engine = FakeEyeGesturesEngine()
    tracker = _tracker(engine)
    assert tracker.save_model() == b"model-bytes"
    tracker.load_model(b"restored")
    assert engine.loaded == (b"restored", "unmouse")


def test_create_gaze_tracker_loads_model() -> None:
    engine = FakeEyeGesturesEngine()
    settings = Settings(screen_width=800, screen_height=600, gaze_calibration_points=9)
    create_gaze_tracker(settings, engine=engine, model=b"saved")
    assert engine.loaded == (b"saved", "unmouse")


def test_calibration_map_shape() -> None:
    grid = calibration_map(9)
    assert grid.shape == (9, 2)
    assert grid.min() >= 0.0
    assert grid.max() <= 1.0


def test_gaze_model_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(profile_name="default")
    assert load_gaze_model(settings) is None
    save_gaze_model(settings, b"payload")
    assert gaze_model_path(settings).is_file()
    assert load_gaze_model(settings) == b"payload"
