"""Shared OpenCV camera open helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import cv2


def open_camera(
    camera_index: int,
    *,
    width: int | None = None,
    height: int | None = None,
) -> cv2.VideoCapture:
    import cv2

    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        msg = f"Unable to open camera {camera_index}."
        raise RuntimeError(msg)
    if width is not None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height is not None:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture
