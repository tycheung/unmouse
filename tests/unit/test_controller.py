from __future__ import annotations

from tests.fakes.arbitrator import NoopActionDriver, StaticSnapProvider
from unmouse.arbitrator.controller import ActionController
from unmouse.arbitrator.snap import SnapRect, SnapTarget
from unmouse.config import GazeMode, Settings
from unmouse.gestures.fsm import ClickEvent
from unmouse.gestures.scroll_fsm import ScrollTick
from unmouse.state import create_system_state


def test_controller_moves_cursor_to_snapped_target() -> None:
    settings = Settings(screen_width=800, screen_height=600, snap_radius_px=80.0)
    state = create_system_state(settings)
    state.set_gaze(102.0, 98.0, 0.9)
    driver = NoopActionDriver()
    provider = StaticSnapProvider(
        (
            SnapTarget(
                target_id="button",
                bounds=SnapRect(x=90.0, y=90.0, width=20.0, height=20.0),
            ),
        ),
    )
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=provider,
        enable_overlay=False,
    )
    x, y = controller.tick(timestamp_s=0.0)
    assert x == 100.0
    assert y == 100.0
    assert driver.moves[-1] == (100, 100)


def test_controller_respects_gaze_only_mode() -> None:
    settings = Settings(
        screen_width=800,
        screen_height=600,
        gaze_mode=GazeMode.GAZE_ONLY,
    )
    state = create_system_state(settings)
    state.set_gaze(400.0, 300.0, 0.9)
    driver = NoopActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )
    controller.tick(timestamp_s=0.0)
    assert driver.moves == []

    state.set_click_mode(True)
    controller.tick(timestamp_s=0.1)
    assert driver.moves[-1] == (400, 300)


def test_controller_executes_queued_click_and_scroll() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    state.set_gaze(400.0, 300.0, 0.9)
    driver = NoopActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )
    state.enqueue_click_event(ClickEvent(button="left", x=10.0, y=20.0))
    state.enqueue_scroll_tick(ScrollTick(x=30.0, y=40.0, delta=-3.0))
    controller.tick(timestamp_s=0.0)
    assert driver.clicks == [(10, 20, "left")]
    assert driver.scrolls == [(30, 40, -3)]


def test_controller_holds_cursor_when_gaze_invalid() -> None:
    settings = Settings(screen_width=800, screen_height=600)
    state = create_system_state(settings)
    driver = NoopActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )

    controller.tick(timestamp_s=0.0)
    assert driver.moves == []

    state.set_gaze(120.0, 90.0, 0.9)
    controller.tick(timestamp_s=0.1)
    assert driver.moves[-1] == (120, 90)

    state.set_gaze_valid(False)
    controller.tick(timestamp_s=0.2)
    assert driver.moves[-1] == (120, 90)
