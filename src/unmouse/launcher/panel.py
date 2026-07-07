"""pywebview control panel shell hosting Alpine.js UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from unmouse.config import Settings
from unmouse.launcher.api import PanelApi
from unmouse.launcher.onboarding import OnboardingController
from unmouse.launcher.settings import load_persisted_settings
from unmouse.utils.paths import resource_path

PANEL_TITLE = "unmouse"
PANEL_WIDTH = 420
PANEL_HEIGHT = 520


def ui_assets_dir() -> Path:
    return resource_path("assets/ui")


def ui_index_path() -> Path:
    return ui_assets_dir() / "index.html"


def create_panel_api(settings: Settings | None = None) -> PanelApi:
    app_settings = settings or load_persisted_settings()
    onboarding = OnboardingController.create(app_settings)
    return PanelApi(settings=app_settings, onboarding=onboarding)


def _panel_window_callbacks(
    api: PanelApi,
) -> tuple[Callable[[], None], Callable[[], None], Callable[[], None]]:
    import webview

    def show_panel() -> None:
        if webview.windows:
            webview.windows[0].show()
            webview.windows[0].restore()

    def minimize_panel() -> None:
        if webview.windows:
            webview.windows[0].minimize()

    def quit_app() -> None:
        api.shutdown()
        if webview.windows:
            webview.windows[0].destroy()

    return show_panel, minimize_panel, quit_app


def run(*, debug: bool = False) -> None:
    """Open the control panel window."""
    import webview

    index = ui_index_path()
    if not index.is_file():
        msg = f"control panel UI missing: {index}"
        raise FileNotFoundError(msg)

    api = create_panel_api()
    show_panel, minimize_panel, quit_app = _panel_window_callbacks(api)
    api.configure_launcher_shell(
        on_show_panel=show_panel,
        on_minimize_panel=minimize_panel,
        on_quit_app=quit_app,
    )

    window = webview.create_window(
        PANEL_TITLE,
        url=index.as_uri(),
        js_api=api,
        width=PANEL_WIDTH,
        height=PANEL_HEIGHT,
        resizable=False,
    )

    def on_closing() -> bool:
        api.shutdown()
        return True

    window.events.closing += on_closing
    webview.start(debug=debug)
