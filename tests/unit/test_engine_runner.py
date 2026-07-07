"""Unit tests for engine subprocess runner."""

from __future__ import annotations

from unittest.mock import MagicMock

from unmouse.launcher.engine_runner import EngineRunner, build_engine_command


def test_build_engine_command_uses_module_flag() -> None:
    command = build_engine_command(executable="python")
    assert command == ["python", "-m", "unmouse", "--engine"]


def test_engine_runner_start_and_stop() -> None:
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 4242
    popen = MagicMock(return_value=process)
    runner = EngineRunner(command=["python", "-m", "unmouse", "--engine"], popen=popen)

    started = runner.start()
    assert started.ok is True
    assert started.running is True
    assert started.pid == 4242
    assert runner.is_running() is True

    stopped = runner.stop()
    process.terminate.assert_called_once()
    process.wait.assert_called()
    assert stopped.ok is True
    assert stopped.running is False
    assert runner.is_running() is False


def test_engine_runner_start_is_idempotent() -> None:
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 99
    popen = MagicMock(return_value=process)
    runner = EngineRunner(popen=popen)

    first = runner.start()
    second = runner.start()
    assert first.ok is True
    assert second.message == "Engine already running."
    popen.assert_called_once()


def test_engine_runner_stop_when_not_running() -> None:
    runner = EngineRunner()
    stopped = runner.stop()
    assert stopped.ok is True
    assert stopped.running is False
    assert stopped.message == "Engine is not running."
