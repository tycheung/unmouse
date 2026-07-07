"""Unit tests for engine lifecycle."""

from unittest.mock import patch

from unmouse.config import Settings
from unmouse.main import run_engine
from unmouse.state import create_system_state


def test_run_engine_exits_when_stopped() -> None:
    settings = Settings()
    state = create_system_state(settings)
    state.stop()
    with patch("unmouse.main.time.sleep", side_effect=lambda _: state.stop()):
        run_engine(settings, state)
