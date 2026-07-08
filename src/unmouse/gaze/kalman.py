from __future__ import annotations

import numpy as np
from filterpy.kalman import KalmanFilter  # type: ignore[import-untyped]


class GazeKalmanFilter:
    def __init__(
        self,
        initial_x: float,
        initial_y: float,
        measurement_noise: float = 10.0,
        process_noise: float = 0.1,
    ) -> None:
        self._kf = KalmanFilter(dim_x=4, dim_z=2)
        self._kf.F = np.array(
            [[1.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 1.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        )
        self._kf.H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        self._kf.R *= measurement_noise
        self._kf.Q *= process_noise
        self.reset(initial_x, initial_y)

    def reset(self, x: float, y: float) -> None:
        self._kf.x = np.array([[x], [y], [0.0], [0.0]])

    def update(self, x: float, y: float) -> tuple[float, float]:
        self._kf.predict()
        self._kf.update(np.array([[x], [y]]))
        return float(self._kf.x[0, 0]), float(self._kf.x[1, 0])
