"""Unit tests for gaze quality gate."""

from unittest.mock import patch

from unmouse.gaze.quality import GazeQualityGate
from unmouse.gaze.tracker import GazeResult


def test_low_confidence_holds_last_good_position() -> None:
    gate = GazeQualityGate(confidence_min=0.5)
    gate.process(GazeResult(x=100.0, y=200.0, confidence=0.9))
    out = gate.process(GazeResult(x=500.0, y=600.0, confidence=0.1))
    assert out.hold_active is True
    assert out.x == 100.0
    assert out.y == 200.0


def test_head_pose_drift_emits_recalibrate_hint() -> None:
    gate = GazeQualityGate(head_pose_drift_deg=10.0, drift_dwell_s=0.5)
    with patch("unmouse.gaze.quality.time.monotonic") as mock_time:
        mock_time.return_value = 0.0
        gate.process(GazeResult(x=1.0, y=2.0, confidence=1.0, head_yaw_deg=0.0))
        mock_time.return_value = 0.1
        gate.process(GazeResult(x=1.0, y=2.0, confidence=1.0, head_yaw_deg=25.0))
        mock_time.return_value = 2.0
        out = gate.process(GazeResult(x=1.0, y=2.0, confidence=1.0, head_yaw_deg=25.0))
        assert out.recalibrate_hint is True
        assert out.head_pose_ok is False
