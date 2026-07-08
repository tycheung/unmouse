"""Tracking engine entry point (spawned by launcher)."""

from __future__ import annotations

from unmouse.launcher.settings import load_persisted_settings
from unmouse.main import run_engine


def run() -> None:
    run_engine(load_persisted_settings())


if __name__ == "__main__":
    run()
