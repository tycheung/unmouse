"""Resolve bundled and development asset paths."""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(relative: str) -> Path:
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", project_root()))
    else:
        base = project_root()
    return base / relative
