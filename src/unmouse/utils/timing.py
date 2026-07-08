from __future__ import annotations

import time
from collections.abc import Callable


def run_at_interval(
    running: Callable[[], bool],
    work: Callable[[], object],
    interval_s: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.perf_counter,
) -> None:
    while running():
        started = clock()
        work()
        remaining = interval_s - (clock() - started)
        if remaining > 0:
            sleep(remaining)
