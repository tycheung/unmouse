from __future__ import annotations

import pytest

from unmouse.gestures.enrollment import synthetic_landmarks
from unmouse.gestures.scroll_zones import (
    edge_distance_in_zone,
    scroll_speed,
    thumb_elevation_angle,
    zone_from_angle,
)


@pytest.mark.parametrize(
    ("phi", "expected_zone"),
    [
        (85.0, 0),
        (0.0, 4),
        (-85.0, 8),
        (15.0, 3),
        (70.0, 0),
        (-15.0, 5),
    ],
)
def test_zone_from_angle(phi: float, expected_zone: int) -> None:
    assert zone_from_angle(phi).index == expected_zone


def test_dead_zone_zero_speed() -> None:
    assert scroll_speed(5.0) == 0.0
    assert scroll_speed(-7.0) == 0.0


def test_scroll_speed_sign_matches_zone_direction() -> None:
    assert scroll_speed(85.0) > 0.0
    assert scroll_speed(-85.0) < 0.0


def test_log_scaling_increases_toward_zone_outer_edge() -> None:
    zone = zone_from_angle(85.0)
    inner = scroll_speed(zone.lower_deg + 1.0)
    outer = scroll_speed(zone.upper_deg)
    assert outer > inner > 0.0


def test_edge_distance_is_zero_at_dead_boundary() -> None:
    zone = zone_from_angle(20.0)
    assert edge_distance_in_zone(10.0, zone) == pytest.approx(0.0)


def test_edge_distance_is_one_at_outer_edge() -> None:
    zone = zone_from_angle(85.0)
    assert edge_distance_in_zone(90.0, zone) == pytest.approx(1.0)


def test_thumb_elevation_angle_points_up_for_thumbs_up_pose() -> None:
    hand = synthetic_landmarks("thumbs_up")
    angle = thumb_elevation_angle(hand)
    assert angle < -15.0
    assert zone_from_angle(angle).index == 5
