"""Subprocess lifecycle for the tracking engine."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

EnginePopen = Callable[..., subprocess.Popen[bytes]]
CrashCallback = Callable[["WatchdogEvent"], None]
SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class EngineProcessStatus:
    ok: bool
    running: bool
    pid: int | None
    message: str


def build_engine_command(*, executable: str | None = None) -> list[str]:
    exe = executable or sys.executable
    if getattr(sys, "frozen", False):
        return [exe, "--engine"]
    return [exe, "-m", "unmouse", "--engine"]


class EngineRunner:
    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        popen: EnginePopen | None = None,
        stop_timeout_s: float = 5.0,
    ) -> None:
        self._command = list(command or build_engine_command())
        self._popen = popen or subprocess.Popen
        self._stop_timeout_s = stop_timeout_s
        self._process: subprocess.Popen[bytes] | None = None
        self._intentional_stop = False

    @property
    def intentional_stop(self) -> bool:
        return self._intentional_stop

    @property
    def pid(self) -> int | None:
        if self._process is None:
            return None
        return self._process.pid

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> EngineProcessStatus:
        if self.is_running():
            return EngineProcessStatus(
                ok=True,
                running=True,
                pid=self.pid,
                message="Engine already running.",
            )
        try:
            self._intentional_stop = False
            self._process = self._popen(
                self._command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._process = None
            return EngineProcessStatus(
                ok=False,
                running=False,
                pid=None,
                message=f"Failed to start engine: {exc}",
            )
        return EngineProcessStatus(
            ok=True,
            running=True,
            pid=self.pid,
            message="Tracking engine started.",
        )

    def stop(self) -> EngineProcessStatus:
        if not self.is_running():
            self._process = None
            return EngineProcessStatus(
                ok=True,
                running=False,
                pid=None,
                message="Engine is not running.",
            )
        process = self._process
        assert process is not None
        self._intentional_stop = True
        process.terminate()
        try:
            process.wait(timeout=self._stop_timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=self._stop_timeout_s)
        self._process = None
        return EngineProcessStatus(
            ok=True,
            running=False,
            pid=None,
            message="Tracking engine stopped.",
        )

    def poll(self) -> int | None:
        if self._process is None:
            return None
        return self._process.poll()


@dataclass(frozen=True)
class WatchdogEvent:
    exit_code: int
    message: str
    restarted: bool = False


class EngineWatchdog:
    def __init__(
        self,
        runner: EngineRunner,
        *,
        on_crash: CrashCallback,
        auto_restart: bool = True,
        poll_interval_s: float = 1.0,
        sleep: SleepFn = time.sleep,
    ) -> None:
        self._runner = runner
        self._on_crash = on_crash
        self._auto_restart = auto_restart
        self._poll_interval_s = poll_interval_s
        self._sleep = sleep
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="engine-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        while self._running:
            exit_code = self._runner.poll()
            if exit_code is not None and not self._runner.intentional_stop:
                restarted = False
                message = f"Engine exited unexpectedly (code {exit_code})."
                if self._auto_restart:
                    status = self._runner.start()
                    restarted = status.ok and status.running
                    if restarted:
                        message = f"{message} Restarted engine."
                event = WatchdogEvent(exit_code=exit_code, message=message, restarted=restarted)
                self._on_crash(event)
            self._sleep(self._poll_interval_s)
