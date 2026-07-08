"""Application orchestrator."""

from __future__ import annotations

import signal
import sys
import time

from unmouse.config import Settings
from unmouse.diagnostics import DiagnosticsService
from unmouse.engine_controls import EngineRuntimeController
from unmouse.state import SystemState, create_system_state
from unmouse.utils.logging import setup_logging


def run_engine(settings: Settings, state: SystemState | None = None) -> None:
    runtime_state = state or create_system_state(settings)
    logger = setup_logging(settings, name="unmouse.engine")
    _install_signal_handlers(runtime_state)

    from unmouse.arbitrator.controller import ActionController
    from unmouse.broker.video_broker import VideoBroker
    from unmouse.gaze.thread import GazeWorker
    from unmouse.gestures.thread import GestureWorker

    diagnostics = DiagnosticsService(runtime_state, settings)
    broker = VideoBroker(
        runtime_state,
        settings,
        on_frame=diagnostics.record_broker_frame,
    )
    gaze_worker = GazeWorker(runtime_state, settings)
    gesture_worker = GestureWorker(runtime_state, settings)
    controller = ActionController(runtime_state, settings, enable_overlay=False)
    runtime_controller = EngineRuntimeController(settings)
    broker.start()
    gaze_worker.start()
    gesture_worker.start()
    controller.start()
    runtime_controller.start()
    diagnostics.start()

    logger.info("Engine started for screen %sx%s", settings.screen_width, settings.screen_height)
    try:
        while runtime_state.is_running():
            time.sleep(0.05)
    except KeyboardInterrupt:
        runtime_state.stop()
    finally:
        diagnostics.stop()
        runtime_controller.stop()
        controller.stop()
        controller.join(timeout=1.0)
        gesture_worker.join(timeout=1.0)
        gaze_worker.join(timeout=1.0)
        broker.join(timeout=1.0)
        logger.info("Engine stopped")


def run_engine_cli() -> None:
    from unmouse.persistence import load_persisted_settings

    run_engine(load_persisted_settings())


def run() -> None:
    from unmouse.launcher.panel import run as run_panel

    run_panel()


def _install_signal_handlers(state: SystemState) -> None:
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, lambda _sig, _frame: state.stop())
        signal.signal(signal.SIGTERM, lambda _sig, _frame: state.stop())
