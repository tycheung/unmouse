from __future__ import annotations

import numpy as np
import numpy.typing as npt

from unmouse.gestures.angles import landmarks_to_array
from unmouse.gestures.landmarks import INDEX_MCP, PINKY_MCP, WRIST, HandLandmarks

FINGERTIPS = (8, 12, 16, 20)
KNUCKLE_CHAINS = ((9, 12), (13, 16), (17, 20))
CAMERA_FORWARD = np.array([0.0, 0.0, -1.0], dtype=np.float64)
DEFAULT_NORMAL_THRESHOLD = 0.12
DEFAULT_DORSAL_KNUCKLE_MIN = 0.015
DEFAULT_PALM_DEPTH_MIN = 0.01


def detect_right_click_orientation(
    hand: HandLandmarks,
    *,
    normal_threshold: float = DEFAULT_NORMAL_THRESHOLD,
    dorsal_knuckle_min: float = DEFAULT_DORSAL_KNUCKLE_MIN,
    palm_depth_min: float = DEFAULT_PALM_DEPTH_MIN,
) -> bool:
    """Return True when a palm-facing orientation selects a right click."""
    if _dorsal_knuckle_heuristic(hand, dorsal_knuckle_min):
        return False
    alignment = float(np.dot(palm_normal(hand), CAMERA_FORWARD))
    return _palm_facing_heuristic(hand, palm_depth_min) or alignment > normal_threshold


def palm_normal(hand: HandLandmarks) -> npt.NDArray[np.float64]:
    """Unit normal for the palm plane derived from wrist and MCP landmarks."""
    points = landmarks_to_array(hand)
    normal = np.cross(points[INDEX_MCP] - points[WRIST], points[PINKY_MCP] - points[WRIST])
    norm = float(np.linalg.norm(normal))
    if norm < 1e-8:
        return np.zeros(3, dtype=np.float64)
    normal = normal / norm
    if hand.handedness == "Left":
        normal = -normal
    return np.asarray(normal, dtype=np.float64)


def _dorsal_knuckle_heuristic(hand: HandLandmarks, min_score: float) -> bool:
    """True when curled middle/ring/pinky knuckles face the camera."""
    points = landmarks_to_array(hand)
    scores = [float(points[tip][2] - points[base][2]) for base, tip in KNUCKLE_CHAINS]
    return float(np.mean(scores)) > min_score


def _palm_facing_heuristic(hand: HandLandmarks, min_depth_delta: float) -> bool:
    """True when fingertips are closer to the camera than the wrist."""
    points = landmarks_to_array(hand)
    wrist_z = float(points[WRIST][2])
    fingertip_z = float(np.mean([points[index][2] for index in FINGERTIPS]))
    return fingertip_z + min_depth_delta < wrist_z
