"""Subprocess lifecycle for the tracking engine."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

EnginePopen = Callable[..., subprocess.Popen[bytes]]


@dataclass(frozen=True)
class EngineProcessStatus:
    ok: bool
    running: bool
    pid: int | None
    message: str


def build_engine_command(*, executable: str | None = None) -> list[str]:
    """Return argv for spawning the tracking engine entry point."""
    return [executable or sys.executable, "-m", "unmouse", "--engine"]


class EngineRunner:
    """Spawn and stop the `--engine` subprocess from the launcher."""

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
