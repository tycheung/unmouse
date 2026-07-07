"""Unit tests for hand landmark detection and skeleton drawing."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from unmouse.gestures.landmarks import (
    HandLandmarks,
    LandmarkDetectionResult,
    MediaPipeHandDetector,
    MockHandLandmarkDetector,
    draw_hand_skeleton,
)


def _sample_hand() -> HandLandmarks:
    points = tuple((float(i) / 20.0, 0.5, 0.0) for i in range(21))
    return HandLandmarks(points=points, handedness="Right")


def test_hand_landmarks_requires_twenty_one_points() -> None:
    with pytest.raises(ValueError, match="21 landmarks"):
        HandLandmarks(points=((0.0, 0.0, 0.0),))


def test_mock_detector_returns_configured_hands() -> None:
    hand = _sample_hand()
    detector = MockHandLandmarkDetector([hand])
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    result = detector.detect(frame)
    assert result.hands == (hand,)


def test_draw_hand_skeleton_skips_when_disabled() -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    out = draw_hand_skeleton(frame, [_sample_hand()], draw=False)
    assert out is frame


def test_draw_hand_skeleton_invokes_mediapipe_drawing() -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    mock_drawing = MagicMock()
    mock_drawing.DrawingSpec = MagicMock()
    mock_hands = MagicMock()
    mock_hands.HAND_CONNECTIONS = object()

    fake_mp = MagicMock()
    fake_mp.solutions.hands = mock_hands
    fake_mp.solutions.drawing_utils = mock_drawing
    fake_mp.framework.formats.landmark_pb2.NormalizedLandmarkList.return_value = MagicMock(
        landmark=MagicMock(add=MagicMock(return_value=MagicMock()))
    )

    with patch.dict("sys.modules", {"mediapipe": fake_mp}):
        out = draw_hand_skeleton(frame, [_sample_hand()], draw=True)

    assert out is not frame
    mock_drawing.draw_landmarks.assert_called_once()


def test_mediapipe_detector_parses_results() -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    landmark = MagicMock(x=0.1, y=0.2, z=0.3)
    hand_landmarks = MagicMock(landmark=[landmark] * 21)
    classification = MagicMock(label="Left")
    handedness = MagicMock(classification=[classification])

    mock_results = MagicMock(
        multi_hand_landmarks=[hand_landmarks],
        multi_handedness=[handedness],
    )
    mock_hands = MagicMock()
    mock_hands.process.return_value = mock_results

    fake_mp = MagicMock()
    fake_mp.solutions.hands.Hands.return_value = mock_hands

    with patch.dict("sys.modules", {"mediapipe": fake_mp}):
        detector = MediaPipeHandDetector()
        result = detector.detect(frame)

    assert isinstance(result, LandmarkDetectionResult)
    assert len(result.hands) == 1
    assert result.hands[0].handedness == "Left"
    assert result.hands[0].points[0] == (0.1, 0.2, 0.3)
    mock_hands.process.assert_called_once()
