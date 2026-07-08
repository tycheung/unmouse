from unittest.mock import patch

from unmouse.config import Settings
from unmouse.diagnostics import (
    DiagnosticsService,
    NoopDiagnosticsOverlay,
    collect_snapshot,
    load_diagnostics_snapshot,
    save_diagnostics_snapshot,
)
from unmouse.main import run_engine
from unmouse.state import create_system_state


def test_run_engine_exits_when_stopped() -> None:
    settings = Settings()
    state = create_system_state(settings)
    state.stop()
    with patch("unmouse.main.time.sleep", side_effect=lambda _: state.stop()):
        run_engine(settings, state)


def test_run_engine_handles_keyboard_interrupt(settings: Settings) -> None:
    state = create_system_state(settings)
    with patch("unmouse.main.time.sleep", side_effect=KeyboardInterrupt):
        run_engine(settings, state)
    assert state.is_running() is False


def test_diagnostics_snapshot_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    state.set_gaze(1.0, 2.0, 0.75)
    snapshot = collect_snapshot(state, broker_fps=24.0)
    save_diagnostics_snapshot(settings, snapshot)
    assert load_diagnostics_snapshot(settings) == snapshot


def test_diagnostics_service_publishes_when_debug_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600, debug=True)
    state = create_system_state(settings)
    overlay = NoopDiagnosticsOverlay()
    service = DiagnosticsService(
        state,
        settings,
        sleep=lambda _interval: state.stop(),
        overlay=overlay,
    )
    service.record_broker_frame()
    service.start()
    if service._thread is not None:
        service._thread.join(timeout=2.0)
    service.stop()
    assert load_diagnostics_snapshot(settings) is not None
    assert overlay.lines is not None
