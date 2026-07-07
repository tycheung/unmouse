"""Unit tests for gaze Kalman filter."""

from unmouse.gaze.kalman import GazeKalmanFilter


def test_reset_zeros_velocity() -> None:
    filt = GazeKalmanFilter(100.0, 200.0)
    filt.update(150.0, 250.0)
    filt.reset(10.0, 20.0)
    x, y = filt.update(10.0, 20.0)
    assert abs(x - 10.0) < 5.0
    assert abs(y - 20.0) < 5.0


def test_smoothing_reduces_jitter() -> None:
    filt = GazeKalmanFilter(500.0, 500.0)
    coords = [(500.0, 500.0), (510.0, 490.0), (495.0, 505.0), (502.0, 498.0)]
    outputs = [filt.update(x, y) for x, y in coords]
    xs = [p[0] for p in outputs]
    assert max(xs) - min(xs) < 20.0
