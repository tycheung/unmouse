from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from unmouse.config import Settings
from unmouse.utils.coerce import as_float
from unmouse.utils.json_io import read_json_object_or_none, write_json_object

GRID_COLS = 4
GRID_ROWS = 3
NUM_CORNERS = 4
NUM_CELLS = GRID_COLS * GRID_ROWS
NUM_SAMPLES = NUM_CORNERS + NUM_CELLS
DEFAULT_CORNER_INSET = 0.05


@dataclass(frozen=True)
class OffsetSample:
    target_x: float
    target_y: float
    delta_x: float
    delta_y: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> OffsetSample:
        return cls(
            target_x=float(data["target_x"]),
            target_y=float(data["target_y"]),
            delta_x=float(data["delta_x"]),
            delta_y=float(data["delta_y"]),
        )


@dataclass(frozen=True)
class OffsetProfile:
    screen_width: float
    screen_height: float
    corners: tuple[OffsetSample, OffsetSample, OffsetSample, OffsetSample]
    cells: tuple[OffsetSample, ...]
    corner_inset: float = DEFAULT_CORNER_INSET

    def __post_init__(self) -> None:
        if len(self.cells) != NUM_CELLS:
            msg = f"expected {NUM_CELLS} cell samples"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> OffsetProfile:
        corners_raw = data.get("corners")
        cells_raw = data.get("cells")
        if not isinstance(corners_raw, list) or not isinstance(cells_raw, list):
            msg = "offset profile requires corners and cells arrays"
            raise ValueError(msg)
        corners = tuple(
            OffsetSample.from_dict(item)
            for item in corners_raw
            if isinstance(item, dict)
        )
        cells = tuple(
            OffsetSample.from_dict(item)
            for item in cells_raw
            if isinstance(item, dict)
        )
        if len(corners) != NUM_CORNERS:
            msg = f"expected {NUM_CORNERS} corner samples"
            raise ValueError(msg)
        return cls(
            screen_width=as_float(data["screen_width"]),
            screen_height=as_float(data["screen_height"]),
            corner_inset=as_float(data.get("corner_inset", DEFAULT_CORNER_INSET)),
            corners=(corners[0], corners[1], corners[2], corners[3]),
            cells=cells,
        )


def build_calibration_targets(
    screen_width: float,
    screen_height: float,
    *,
    corner_inset: float = DEFAULT_CORNER_INSET,
) -> tuple[tuple[float, float], ...]:
    if screen_width <= 0 or screen_height <= 0:
        msg = "screen dimensions must be positive"
        raise ValueError(msg)
    inset_x = screen_width * corner_inset
    inset_y = screen_height * corner_inset
    corners = (
        (inset_x, inset_y),
        (screen_width - inset_x, inset_y),
        (inset_x, screen_height - inset_y),
        (screen_width - inset_x, screen_height - inset_y),
    )
    cells: list[tuple[float, float]] = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cells.append(
                (
                    screen_width * (col + 0.5) / GRID_COLS,
                    screen_height * (row + 0.5) / GRID_ROWS,
                ),
            )
    return corners + tuple(cells)


def sample_from_measurement(
    target_x: float,
    target_y: float,
    measured_x: float,
    measured_y: float,
) -> OffsetSample:
    return OffsetSample(
        target_x=target_x,
        target_y=target_y,
        delta_x=target_x - measured_x,
        delta_y=target_y - measured_y,
    )


def build_profile(
    screen_width: float,
    screen_height: float,
    samples: tuple[OffsetSample, ...] | list[OffsetSample],
    *,
    corner_inset: float = DEFAULT_CORNER_INSET,
) -> OffsetProfile:
    if len(samples) != NUM_SAMPLES:
        msg = f"expected {NUM_SAMPLES} offset samples"
        raise ValueError(msg)
    ordered = tuple(samples)
    return OffsetProfile(
        screen_width=screen_width,
        screen_height=screen_height,
        corner_inset=corner_inset,
        corners=(ordered[0], ordered[1], ordered[2], ordered[3]),
        cells=ordered[4:],
    )


def build_profile_from_measurements(
    screen_width: float,
    screen_height: float,
    measurements: tuple[tuple[float, float], ...] | list[tuple[float, float]],
    *,
    corner_inset: float = DEFAULT_CORNER_INSET,
) -> OffsetProfile:
    targets = build_calibration_targets(screen_width, screen_height, corner_inset=corner_inset)
    if len(measurements) != NUM_SAMPLES:
        msg = f"expected {NUM_SAMPLES} gaze measurements"
        raise ValueError(msg)
    samples = tuple(
        sample_from_measurement(tx, ty, mx, my)
        for (tx, ty), (mx, my) in zip(targets, measurements, strict=True)
    )
    return build_profile(screen_width, screen_height, samples, corner_inset=corner_inset)


def apply_offset_profile(
    x: float,
    y: float,
    profile: OffsetProfile | None,
) -> tuple[float, float]:
    if profile is None:
        return x, y
    delta = interpolate_offset_delta(x, y, profile)
    return x + delta[0], y + delta[1]


def interpolate_offset_delta(
    x: float,
    y: float,
    profile: OffsetProfile,
) -> tuple[float, float]:
    grid = vertex_delta_grid(profile)
    gx = _normalize_axis(x, profile.screen_width, GRID_COLS)
    gy = _normalize_axis(y, profile.screen_height, GRID_ROWS)
    delta = _bilinear_sample(grid, gx, gy)
    return float(delta[0]), float(delta[1])


def vertex_delta_grid(profile: OffsetProfile) -> npt.NDArray[np.float64]:
    """Build a (GRID_ROWS + 1) × (GRID_COLS + 1) vertex grid of delta vectors."""
    grid = np.zeros((GRID_ROWS + 1, GRID_COLS + 1, 2), dtype=np.float64)
    cell_deltas = np.array(
        [[sample.delta_x, sample.delta_y] for sample in profile.cells],
        dtype=np.float64,
    ).reshape(GRID_ROWS, GRID_COLS, 2)

    grid[0, 0] = _delta(profile.corners[0])
    grid[0, GRID_COLS] = _delta(profile.corners[1])
    grid[GRID_ROWS, 0] = _delta(profile.corners[2])
    grid[GRID_ROWS, GRID_COLS] = _delta(profile.corners[3])

    for col in range(1, GRID_COLS):
        grid[0, col] = _average(grid[0, col - 1], cell_deltas[0, col - 1], cell_deltas[0, col])
        grid[GRID_ROWS, col] = _average(
            grid[GRID_ROWS, col - 1],
            cell_deltas[GRID_ROWS - 1, col - 1],
            cell_deltas[GRID_ROWS - 1, col],
        )

    for row in range(1, GRID_ROWS):
        grid[row, 0] = _average(grid[row - 1, 0], cell_deltas[row - 1, 0], cell_deltas[row, 0])
        grid[row, GRID_COLS] = _average(
            grid[row - 1, GRID_COLS],
            cell_deltas[row - 1, GRID_COLS - 1],
            cell_deltas[row, GRID_COLS - 1],
        )

    for row in range(1, GRID_ROWS):
        for col in range(1, GRID_COLS):
            grid[row, col] = _average(
                cell_deltas[row - 1, col - 1],
                cell_deltas[row - 1, col],
                cell_deltas[row, col - 1],
                cell_deltas[row, col],
            )
    return grid


def save_offset_profile(path: Path, profile: OffsetProfile) -> None:
    write_json_object(path, profile.to_dict())


def load_offset_profile(path: Path) -> OffsetProfile | None:
    data = read_json_object_or_none(path, error_message="offset profile JSON must be an object")
    if data is None:
        return None
    return OffsetProfile.from_dict(data)


def offset_profile_path(settings: Settings) -> Path:
    return settings.profile_dir / "offset_profile.json"


def load_offset_profile_for_settings(settings: Settings) -> OffsetProfile | None:
    return load_offset_profile(offset_profile_path(settings))


def _delta(sample: OffsetSample) -> npt.NDArray[np.float64]:
    return np.array([sample.delta_x, sample.delta_y], dtype=np.float64)


def _average(*vectors: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    stack = np.stack(vectors, axis=0)
    return np.asarray(np.mean(stack, axis=0), dtype=np.float64)


def _normalize_axis(value: float, span: float, segments: int) -> float:
    if span <= 0:
        return 0.0
    ratio = min(max(value / span, 0.0), 1.0)
    return ratio * segments


def _bilinear_sample(
    grid: npt.NDArray[np.float64],
    gx: float,
    gy: float,
) -> npt.NDArray[np.float64]:
    max_x = GRID_COLS - 1e-9
    max_y = GRID_ROWS - 1e-9
    gx = min(max(gx, 0.0), max_x)
    gy = min(max(gy, 0.0), max_y)

    x0 = int(gx)
    y0 = int(gy)
    x1 = min(x0 + 1, GRID_COLS)
    y1 = min(y0 + 1, GRID_ROWS)
    tx = gx - x0
    ty = gy - y0

    top = grid[y0, x0] * (1.0 - tx) + grid[y0, x1] * tx
    bottom = grid[y1, x0] * (1.0 - tx) + grid[y1, x1] * tx
    return np.asarray(top * (1.0 - ty) + bottom * ty, dtype=np.float64)
