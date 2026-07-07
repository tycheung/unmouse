"""Tracking engine entry point (spawned by launcher)."""

from __future__ import annotations

from unmouse.config import get_settings
from unmouse.main import run_engine


def run() -> None:
    run_engine(get_settings())


if __name__ == "__main__":
    run()
