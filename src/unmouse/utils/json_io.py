from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_object(path: Path, *, error_message: str) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(error_message)
    return {str(k): v for k, v in data.items()}


def read_json_object_or_empty(path: Path, *, error_message: str) -> dict[str, object]:
    if not path.is_file():
        return {}
    return read_json_object(path, error_message=error_message)


def write_json_object(path: Path, data: dict[str, Any], *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent), encoding="utf-8")

