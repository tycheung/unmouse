import pytest

from unmouse.gaze.saccade import frame_distance, is_saccade


@pytest.mark.parametrize(
    ("x0", "y0", "x1", "y1", "threshold", "expected"),
    [
        (0.0, 0.0, 100.0, 0.0, 80.0, True),
        (0.0, 0.0, 50.0, 0.0, 80.0, False),
        (0.0, 0.0, 80.0, 0.0, 80.0, False),
        (0.0, 0.0, 80.1, 0.0, 80.0, True),
    ],
)
def test_is_saccade_threshold(
    x0: float, y0: float, x1: float, y1: float, threshold: float, expected: bool
) -> None:
    assert is_saccade(x1, y1, x0, y0, threshold) is expected


def test_frame_distance() -> None:
    assert frame_distance(0.0, 0.0, 3.0, 4.0) == pytest.approx(5.0)
