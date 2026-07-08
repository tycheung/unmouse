from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from unmouse.arbitrator.actions import NoopActionDriver, PyAutoGUIActionDriver, create_action_driver


def test_fake_action_driver_records_operations() -> None:
    driver = NoopActionDriver()
    driver.move_to(10.4, 20.6)
    driver.click(10.4, 20.6, button="right")
    driver.scroll(30.0, 40.0, -2.6)
    driver.scroll(30.0, 40.0, 0.2)
    assert driver.moves == [(10, 21)]
    assert driver.clicks == [(10, 21, "right")]
    assert driver.scrolls == [(30, 40, -3)]


def test_fake_action_driver_clear_resets_history() -> None:
    driver = NoopActionDriver()
    driver.move_to(1.0, 2.0)
    driver.clear()
    assert driver.moves == []
    assert driver.clicks == []
    assert driver.scrolls == []


def test_pyautogui_driver_disables_failsafe_by_default() -> None:
    fake_pg = MagicMock()
    with patch.dict("sys.modules", {"pyautogui": fake_pg}):
        PyAutoGUIActionDriver()
    assert fake_pg.FAILSAFE is False
    assert fake_pg.PAUSE == 0.0


def test_pyautogui_driver_delegates_to_pyautogui() -> None:
    fake_pg = MagicMock()
    with patch.dict("sys.modules", {"pyautogui": fake_pg}):
        driver = PyAutoGUIActionDriver(failsafe=True, pause=0.01)
        driver.move_to(100.2, 200.8)
        driver.click(100.2, 200.8, button="left")
        driver.scroll(50.0, 60.0, 4.4)
    fake_pg.moveTo.assert_called_once_with(100, 201)
    fake_pg.click.assert_called_once_with(x=100, y=201, button="left")
    fake_pg.scroll.assert_called_once_with(4, x=50, y=60)


def test_create_action_driver_builds_pyautogui_driver() -> None:
    fake_pg = MagicMock()
    with patch.dict("sys.modules", {"pyautogui": fake_pg}):
        driver = create_action_driver()
    assert isinstance(driver, PyAutoGUIActionDriver)


def test_create_action_driver_raises_when_pyautogui_missing() -> None:
    with patch(
        "unmouse.arbitrator.actions.PyAutoGUIActionDriver",
        side_effect=ImportError("missing"),
    ), pytest.raises(ImportError):
        create_action_driver()
