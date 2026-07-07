"""Unit tests for gaze tracker adapters."""

import numpy as np

from unmouse.gaze.tracker import GazeResult, MockGazeTracker, create_gaze_tracker


def test_mock_tracker_returns_configured_result() -> None:
    tracker = MockGazeTracker(x=123.0, y=456.0, confidence=0.8, head_yaw_deg=5.0)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    result = tracker.predict(frame)
    assert result == GazeResult(x=123.0, y=456.0, confidence=0.8, head_yaw_deg=5.0)


def test_create_gaze_tracker_falls_back_to_mock() -> None:
    tracker = create_gaze_tracker(prefer_eyegestures=True)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    result = tracker.predict(frame)
    assert 0.0 <= result.confidence <= 1.0
