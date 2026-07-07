"""pywebview control panel shell hosting Alpine.js UI."""

from __future__ import annotations

from pathlib import Path

from unmouse.config import Settings
from unmouse.launcher.api import PanelApi
from unmouse.utils.paths import resource_path

PANEL_TITLE = "unmouse"
PANEL_WIDTH = 420
PANEL_HEIGHT = 320


def ui_assets_dir() -> Path:
    return resource_path("assets/ui")


def ui_index_path() -> Path:
    return ui_assets_dir() / "index.html"


def create_panel_api(settings: Settings | None = None) -> PanelApi:
    return PanelApi(settings=settings)


def run(*, debug: bool = False) -> None:
    """Open the control panel window."""
    import webview

    index = ui_index_path()
    if not index.is_file():
        msg = f"control panel UI missing: {index}"
        raise FileNotFoundError(msg)

    api = create_panel_api()
    webview.create_window(
        PANEL_TITLE,
        url=index.as_uri(),
        js_api=api,
        width=PANEL_WIDTH,
        height=PANEL_HEIGHT,
        resizable=False,
    )
    webview.start(debug=debug)
