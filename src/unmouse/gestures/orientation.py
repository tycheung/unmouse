"""Hand orientation heuristics for left vs right click intent."""

from __future__ import annotations

from enum import Enum

import numpy as np
import numpy.typing as npt

from unmouse.gestures.angles import landmarks_to_array
from unmouse.gestures.landmarks import HandLandmarks

WRIST = 0
INDEX_MCP = 5
PINKY_MCP = 17
FINGERTIPS = (8, 12, 16, 20)
KNUCKLE_CHAINS = ((9, 12), (13, 16), (17, 20))
CAMERA_FORWARD = np.array([0.0, 0.0, -1.0], dtype=np.float64)
DEFAULT_NORMAL_THRESHOLD = 0.12
DEFAULT_DORSAL_KNUCKLE_MIN = 0.015
DEFAULT_PALM_DEPTH_MIN = 0.01


class ClickIntent(str, Enum):
    LEFT = "left"
    RIGHT = "right"


def compute_palm_normal(hand: HandLandmarks) -> npt.NDArray[np.float64]:
    """Unit normal for the palm plane derived from wrist and MCP landmarks."""
    points = landmarks_to_array(hand)
    wrist = points[WRIST]
    index_mcp = points[INDEX_MCP]
    pinky_mcp = points[PINKY_MCP]
    normal = np.cross(index_mcp - wrist, pinky_mcp - wrist)
    norm = float(np.linalg.norm(normal))
    if norm < 1e-8:
        return np.zeros(3, dtype=np.float64)
    normal = normal / norm
    if hand.handedness == "Left":
        normal = -normal
    return np.asarray(normal, dtype=np.float64)


def palm_normal_dot_camera(hand: HandLandmarks) -> float:
    """Signed alignment of the palm normal with the camera-forward axis."""
    return float(np.dot(compute_palm_normal(hand), CAMERA_FORWARD))


def detect_click_intent(
    hand: HandLandmarks,
    *,
    normal_threshold: float = DEFAULT_NORMAL_THRESHOLD,
    dorsal_knuckle_min: float = DEFAULT_DORSAL_KNUCKLE_MIN,
    palm_depth_min: float = DEFAULT_PALM_DEPTH_MIN,
) -> ClickIntent:
    """Map dorsal vs palm orientation to left or right click intent."""
    alignment = palm_normal_dot_camera(hand)
    if _dorsal_knuckle_heuristic(hand, dorsal_knuckle_min):
        return ClickIntent.LEFT
    if _palm_facing_heuristic(hand, palm_depth_min) or alignment > normal_threshold:
        return ClickIntent.RIGHT
    if alignment < -normal_threshold:
        return ClickIntent.LEFT
    return ClickIntent.LEFT


def detect_right_click_orientation(
    hand: HandLandmarks,
    *,
    normal_threshold: float = DEFAULT_NORMAL_THRESHOLD,
    dorsal_knuckle_min: float = DEFAULT_DORSAL_KNUCKLE_MIN,
    palm_depth_min: float = DEFAULT_PALM_DEPTH_MIN,
) -> bool:
    """Return True when palm-facing orientation selects a right click."""
    return (
        detect_click_intent(
            hand,
            normal_threshold=normal_threshold,
            dorsal_knuckle_min=dorsal_knuckle_min,
            palm_depth_min=palm_depth_min,
        )
        == ClickIntent.RIGHT
    )


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
