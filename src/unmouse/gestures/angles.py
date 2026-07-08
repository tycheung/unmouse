from __future__ import annotations

import math
from itertools import product

import numpy as np
import numpy.typing as npt

from unmouse.gestures.landmarks import NUM_HAND_LANDMARKS, HandLandmarks

WRIST = 0
MIDDLE_MCP = 9
CANONICAL_PALM_AXIS = np.array([0.0, 1.0, 0.0], dtype=np.float64)

FINGER_CHAINS: tuple[tuple[int, ...], ...] = (
    (1, 2, 3, 4),
    (5, 6, 7, 8),
    (9, 10, 11, 12),
    (13, 14, 15, 16),
    (17, 18, 19, 20),
)

HAND_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (0, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (0, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (0, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (5, 9),
    (9, 13),
    (13, 17),
)


def _build_triplet_indices() -> tuple[tuple[int, int, int], ...]:
    triplets: list[tuple[int, int, int]] = []
    for pivot in range(NUM_HAND_LANDMARKS):
        for i, k in product(range(NUM_HAND_LANDMARKS), repeat=2):
            if i == pivot or k == pivot or i == k:
                continue
            triplets.append((i, pivot, k))
    return tuple(triplets)


TRIPLET_INDICES: tuple[tuple[int, int, int], ...] = _build_triplet_indices()
INTER_FINGER_PAIRS: tuple[tuple[int, int], ...] = tuple(
    (left, right)
    for left in range(len(FINGER_CHAINS))
    for right in range(left + 1, len(FINGER_CHAINS))
)
JOINT_ANGLE_DIM = len(TRIPLET_INDICES)
INTER_FINGER_ANGLE_DIM = len(INTER_FINGER_PAIRS)
FEATURE_DIM = JOINT_ANGLE_DIM + INTER_FINGER_ANGLE_DIM


def landmarks_to_array(hand: HandLandmarks) -> npt.NDArray[np.float64]:
    return np.array(hand.points, dtype=np.float64)


def normalize_palm(
    points: npt.NDArray[np.float64],
    *,
    epsilon: float = 1e-8,
) -> npt.NDArray[np.float64]:
    """Translate to wrist, scale by palm length, rotate wrist→middle-MCP to +Y."""
    if points.shape != (NUM_HAND_LANDMARKS, 3):
        msg = f"expected shape ({NUM_HAND_LANDMARKS}, 3), got {points.shape}"
        raise ValueError(msg)

    translated = points - points[WRIST]
    palm_vector = translated[MIDDLE_MCP]
    palm_length = float(np.linalg.norm(palm_vector))
    if palm_length < epsilon:
        return np.asarray(translated, dtype=np.float64)

    scaled = translated / palm_length
    rotation = _rotation_matrix_align(scaled[MIDDLE_MCP], CANONICAL_PALM_AXIS)
    return np.asarray((rotation @ scaled.T).T, dtype=np.float64)


def _vector_angle(
    vec_a: npt.NDArray[np.float64],
    vec_b: npt.NDArray[np.float64],
    *,
    epsilon: float,
) -> float:
    norm_a = float(np.linalg.norm(vec_a))
    norm_b = float(np.linalg.norm(vec_b))
    if norm_a * norm_b < epsilon:
        return 0.0
    cosine = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
    return math.acos(min(1.0, max(-1.0, cosine)))


def joint_angle(
    i: int,
    pivot: int,
    k: int,
    points: npt.NDArray[np.float64],
    *,
    epsilon: float = 1e-8,
) -> float:
    """Return angle at pivot j between vectors to landmarks i and k."""
    return _vector_angle(points[i] - points[pivot], points[k] - points[pivot], epsilon=epsilon)


def compute_joint_angles(
    points: npt.NDArray[np.float64],
    *,
    epsilon: float = 1e-8,
) -> npt.NDArray[np.float64]:
    return np.array(
        [joint_angle(i, pivot, k, points, epsilon=epsilon) for i, pivot, k in TRIPLET_INDICES],
        dtype=np.float64,
    )


def compute_inter_finger_angles(
    points: npt.NDArray[np.float64],
    *,
    epsilon: float = 1e-8,
) -> npt.NDArray[np.float64]:
    directions = [_finger_direction(points, chain, epsilon=epsilon) for chain in FINGER_CHAINS]
    angles = [
        _vector_angle(directions[left], directions[right], epsilon=epsilon)
        for left, right in INTER_FINGER_PAIRS
    ]
    return np.array(angles, dtype=np.float64)


def compute_joint_angle_vector(
    hand: HandLandmarks,
    *,
    epsilon: float = 1e-8,
    normalize: bool = True,
) -> npt.NDArray[np.float64]:
    """Build the full gesture feature vector for one hand."""
    points = landmarks_to_array(hand)
    if normalize:
        points = normalize_palm(points, epsilon=epsilon)
    joint_angles = compute_joint_angles(points, epsilon=epsilon)
    inter_finger = compute_inter_finger_angles(points, epsilon=epsilon)
    return np.concatenate((joint_angles, inter_finger))


def _finger_direction(
    points: npt.NDArray[np.float64],
    chain: tuple[int, ...],
    *,
    epsilon: float,
) -> npt.NDArray[np.float64]:
    base = points[chain[0]]
    tip = points[chain[-1]]
    direction = tip - base
    norm = float(np.linalg.norm(direction))
    if norm < epsilon:
        return np.zeros(3, dtype=np.float64)
    return np.asarray(direction / norm, dtype=np.float64)


def _rotation_matrix_align(
    source: npt.NDArray[np.float64],
    target: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    src = source / np.linalg.norm(source)
    tgt = target / np.linalg.norm(target)
    dot = float(np.clip(np.dot(src, tgt), -1.0, 1.0))
    if dot > 1.0 - 1e-8:
        return np.eye(3, dtype=np.float64)
    if dot < -1.0 + 1e-8:
        axis = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        if abs(src[0]) > 0.9:
            axis = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        axis = axis - np.dot(axis, src) * src
        axis = axis / np.linalg.norm(axis)
        return _rodrigues(axis, math.pi)

    axis = np.cross(src, tgt)
    axis = axis / np.linalg.norm(axis)
    angle = math.acos(dot)
    return _rodrigues(axis, angle)


def _rodrigues(axis: npt.NDArray[np.float64], angle: float) -> npt.NDArray[np.float64]:
    x, y, z = axis
    cross = np.array(
        [
            [0.0, -z, y],
            [z, 0.0, -x],
            [-y, x, 0.0],
        ],
        dtype=np.float64,
    )
    identity = np.eye(3, dtype=np.float64)
    return np.asarray(
        identity + math.sin(angle) * cross + (1.0 - math.cos(angle)) * (cross @ cross),
        dtype=np.float64,
    )
