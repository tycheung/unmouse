"""Unit tests for resource path resolution."""

from pathlib import Path

from unmouse.utils import paths


def test_resource_path_dev_mode(monkeypatch) -> None:
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    root = paths.project_root()
    assert paths.resource_path("assets/gestures") == root / "assets/gestures"


def test_resource_path_frozen_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("assets/ui") == tmp_path / "assets/ui"
