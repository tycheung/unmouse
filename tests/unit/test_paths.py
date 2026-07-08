import logging
from pathlib import Path

from unmouse.config import Settings
from unmouse.utils import paths
from unmouse.utils.logging import LOG_FILENAME, log_file_path, setup_logging


def test_resource_path_dev_mode(monkeypatch) -> None:
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    root = paths.project_root()
    assert paths.resource_path("assets/gestures") == root / "assets/gestures"


def test_resource_path_frozen_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("assets/ui") == tmp_path / "assets/ui"


def test_setup_logging_writes_rotating_file(tmp_path, monkeypatch) -> None:
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(screen_width=800, screen_height=600, debug=True)
    logger = setup_logging(settings, name="unmouse.test")
    logger.info("hello watchdog")
    for handler in root.handlers:
        handler.flush()
    log_path = log_file_path(settings)
    assert log_path.name == LOG_FILENAME
    assert "hello watchdog" in log_path.read_text(encoding="utf-8")
