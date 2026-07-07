"""Application orchestrator."""

from __future__ import annotations

import signal
import sys
import time

from unmouse.config import Settings, get_settings
from unmouse.state import SystemState, create_system_state


def run_engine(settings: Settings, state: SystemState | None = None) -> None:
    runtime_state = state or create_system_state(settings)
    _install_signal_handlers(runtime_state)

    from unmouse.broker.video_broker import VideoBroker
    from unmouse.gaze.thread import GazeWorker

    broker = VideoBroker(runtime_state, settings)
    gaze_worker = GazeWorker(runtime_state, settings)
    broker.start()
    gaze_worker.start()

    print(f"unmouse engine — screen {settings.screen_width}x{settings.screen_height}")
    try:
        while runtime_state.is_running():
            time.sleep(0.05)
    except KeyboardInterrupt:
        runtime_state.stop()
    finally:
        gaze_worker.join(timeout=1.0)
        broker.join(timeout=1.0)
        print("unmouse engine stopped.")


def run() -> None:
    settings = get_settings()
    state = create_system_state(settings)
    run_engine(settings, state)


def _install_signal_handlers(state: SystemState) -> None:
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, lambda _sig, _frame: state.stop())
        signal.signal(signal.SIGTERM, lambda _sig, _frame: state.stop())
