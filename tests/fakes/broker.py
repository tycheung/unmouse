"""Broker test doubles."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


class MockFrameSource:
    def __init__(self, frames: list[npt.NDArray[np.uint8]]) -> None:
        self._frames = frames
        self._index = 0
        self.released = False

    def read(self) -> tuple[bool, npt.NDArray[np.uint8] | None]:
        if self._index >= len(self._frames):
            return False, None
        frame = self._frames[self._index]
        self._index += 1
        return True, frame

    def release(self) -> None:
        self.released = True
