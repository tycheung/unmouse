from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from unmouse.gestures.angles import landmarks_to_array
from unmouse.gestures.landmarks import HandLandmarks

WRIST = 0
THUMB_TIP = 4
MIDDLE_MCP = 9
DEFAULT_V_MAX = 120.0
DEFAULT_LOG_K = 9.0


@dataclass(frozen=True)
class ScrollZone:
    index: int
    tier: float
    lower_deg: float
    upper_deg: float


SCROLL_ZONES: tuple[ScrollZone, ...] = (
    ScrollZone(0, 1.00, 70.0, 90.0),
    ScrollZone(1, 0.65, 50.0, 70.0),
    ScrollZone(2, 0.40, 30.0, 50.0),
    ScrollZone(3, 0.15, 10.0, 30.0),
    ScrollZone(4, 0.0, -10.0, 10.0),
    ScrollZone(5, -0.15, -30.0, -10.0),
    ScrollZone(6, -0.40, -50.0, -30.0),
    ScrollZone(7, -0.65, -70.0, -50.0),
    ScrollZone(8, -1.00, -90.0, -70.0),
)


def zone_from_angle(phi_deg: float) -> ScrollZone:
    """Map thumb elevation angle to one of nine scroll zones."""
    clamped = min(90.0, max(-90.0, phi_deg))
    for zone in SCROLL_ZONES:
        if zone.lower_deg <= clamped <= zone.upper_deg:
            return zone
    return SCROLL_ZONES[4]


def edge_distance_in_zone(phi_deg: float, zone: ScrollZone) -> float:
    """Return 0 at the dead-zone edge and 1 at the zone outer edge."""
    if zone.tier == 0.0:
        return 0.0

    if zone.tier > 0:
        span = zone.upper_deg - zone.lower_deg
        if span <= 0:
            return 0.0
        return min(1.0, max(0.0, (phi_deg - zone.lower_deg) / span))

    span = zone.upper_deg - zone.lower_deg
    if span <= 0:
        return 0.0
    return min(1.0, max(0.0, (zone.upper_deg - phi_deg) / span))


def scroll_speed(
    phi_deg: float,
    *,
    v_max: float = DEFAULT_V_MAX,
    k: float = DEFAULT_LOG_K,
) -> float:
    """Signed scroll speed in lines per tick for a thumb elevation angle."""
    zone = zone_from_angle(phi_deg)
    if zone.tier == 0.0:
        return 0.0

    distance = edge_distance_in_zone(phi_deg, zone)
    log_scale = math.log(1.0 + k * distance) / math.log(1.0 + k)
    magnitude = v_max * abs(zone.tier) * log_scale
    return math.copysign(magnitude, zone.tier)


def thumb_elevation_angle(hand: HandLandmarks) -> float:
    """Thumb elevation angle relative to wrist→middle-MCP axis in the image plane."""
    points = landmarks_to_array(hand)
    wrist = points[WRIST, :2]
    middle_mcp = points[MIDDLE_MCP, :2]
    thumb_tip = points[THUMB_TIP, :2]
    reference = middle_mcp - wrist
    thumb_vector = thumb_tip - wrist
    ref_norm = float(np.linalg.norm(reference))
    thumb_norm = float(np.linalg.norm(thumb_vector))
    if ref_norm < 1e-8 or thumb_norm < 1e-8:
        return 0.0

    reference_unit = reference / ref_norm
    thumb_unit = thumb_vector / thumb_norm
    dot = float(np.clip(np.dot(reference_unit, thumb_unit), -1.0, 1.0))
    cross = float(reference_unit[0] * thumb_unit[1] - reference_unit[1] * thumb_unit[0])
    return math.degrees(math.atan2(cross, dot))
