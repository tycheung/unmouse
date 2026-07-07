"""Unit tests for pywebview control panel shell."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from unmouse.launcher import panel
from unmouse.launcher.panel import create_panel_api, ui_assets_dir, ui_index_path


def test_ui_assets_paths_exist() -> None:
    assets = ui_assets_dir()
    index = ui_index_path()
    assert assets.is_dir()
    assert index.is_file()
    assert (assets / "styles.css").is_file()
    assert (assets / "alpine.min.js").is_file()


def test_ui_index_references_local_assets() -> None:
    html = ui_index_path().read_text(encoding="utf-8")
    assert 'href="styles.css"' in html
    assert 'src="alpine.min.js"' in html
    assert "Update Software" in html
    assert "Calibrate" in html
    assert "Launch" in html
    assert "Settings" in html


def test_create_panel_api_uses_settings() -> None:
    from unmouse.config import Settings

    api = create_panel_api(settings=Settings(screen_width=640, screen_height=480))
    assert api.get_status()["message"] == "Ready"


def test_run_raises_when_ui_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.html"
    with patch.object(panel, "ui_index_path", return_value=missing):
        with pytest.raises(FileNotFoundError, match="control panel UI missing"):
            panel.run()


def test_run_starts_webview_window() -> None:
    fake_webview = MagicMock()
    with patch.object(panel, "ui_index_path", return_value=ui_index_path()):
        with patch.dict("sys.modules", {"webview": fake_webview}):
            panel.run()
    fake_webview.create_window.assert_called_once()
    fake_webview.start.assert_called_once()
    kwargs = fake_webview.create_window.call_args.kwargs
    assert kwargs["width"] == 420
    assert kwargs["height"] == 520
    assert kwargs["resizable"] is False
