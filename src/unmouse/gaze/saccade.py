from __future__ import annotations

import math


def frame_distance(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.hypot(x1 - x0, y1 - y0)


def is_saccade(
    current_x: float,
    current_y: float,
    previous_x: float,
    previous_y: float,
    threshold_px: float,
) -> bool:
    return frame_distance(previous_x, previous_y, current_x, current_y) > threshold_px
