"""Unit tests for engine subprocess runner."""

from __future__ import annotations

from unittest.mock import MagicMock

from unmouse.launcher.engine_runner import (
    EngineProcessStatus,
    EngineRunner,
    EngineWatchdog,
    WatchdogEvent,
    build_engine_command,
)


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
    assert runner.intentional_stop is True


def test_engine_runner_clears_intentional_stop_on_start() -> None:
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 7
    popen = MagicMock(return_value=process)
    runner = EngineRunner(popen=popen)
    runner._intentional_stop = True
    runner.start()
    assert runner.intentional_stop is False


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


def test_watchdog_restarts_on_unexpected_exit() -> None:
    runner = MagicMock()
    runner.poll.return_value = 1
    runner.intentional_stop = False
    runner.start.return_value = EngineProcessStatus(
        ok=True,
        running=True,
        pid=42,
        message="Tracking engine started.",
    )
    events: list[WatchdogEvent] = []
    watchdog = EngineWatchdog(runner, on_crash=events.append, poll_interval_s=0.01)
    watchdog._sleep = lambda _interval: setattr(watchdog, "_running", False)
    watchdog.start()
    watchdog.stop()
    assert events[0].restarted is True
    runner.start.assert_called_once()


def test_watchdog_ignores_intentional_stop() -> None:
    runner = MagicMock()
    runner.poll.return_value = 0
    runner.intentional_stop = True
    events: list[WatchdogEvent] = []
    watchdog = EngineWatchdog(runner, on_crash=events.append, poll_interval_s=0.01)
    watchdog._sleep = lambda _interval: setattr(watchdog, "_running", False)
    watchdog.start()
    watchdog.stop()
    assert events == []
