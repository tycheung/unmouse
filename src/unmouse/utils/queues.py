from __future__ import annotations

from queue import Empty, Full, Queue
from typing import TypeVar

_T = TypeVar("_T")


def offer_latest(queue: Queue[_T] | None, item: _T) -> None:
    if queue is None:
        return
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        try:
            queue.put_nowait(item)
        except Full:
            pass
