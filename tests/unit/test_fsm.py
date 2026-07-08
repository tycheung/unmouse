from __future__ import annotations

from unmouse.gestures.fsm import (
    ClickEvent,
    ClickFrameInput,
    ClickFsm,
    ClickState,
)


def _frame(
    timestamp_s: float,
    *,
    v_sign_active: bool = False,
    pinch_close: bool = False,
    right_click: bool = False,
    gaze_x: float = 640.0,
    gaze_y: float = 360.0,
) -> ClickFrameInput:
    return ClickFrameInput(
        timestamp_s=timestamp_s,
        v_sign_active=v_sign_active,
        pinch_close=pinch_close,
        right_click=right_click,
        gaze_x=gaze_x,
        gaze_y=gaze_y,
    )


def test_v_sign_arms_click_mode() -> None:
    fsm = ClickFsm()
    output = fsm.process(_frame(0.0, v_sign_active=True))
    assert output.state == ClickState.ARMED
    assert output.click_mode is True
    assert output.click_event is None


def test_v_sign_loss_debounce_disarms_after_300ms() -> None:
    fsm = ClickFsm(v_sign_loss_debounce_s=0.3)
    fsm.process(_frame(0.0, v_sign_active=True))
    fsm.process(_frame(0.1, v_sign_active=False))
    still_armed = fsm.process(_frame(0.25, v_sign_active=False))
    assert still_armed.click_mode is True
    disarmed = fsm.process(_frame(0.41, v_sign_active=False))
    assert disarmed.state == ClickState.IDLE
    assert disarmed.click_mode is False


def test_v_sign_return_clears_debounce_timer() -> None:
    fsm = ClickFsm(v_sign_loss_debounce_s=0.3)
    fsm.process(_frame(0.0, v_sign_active=True))
    fsm.process(_frame(0.1, v_sign_active=False))
    fsm.process(_frame(0.2, v_sign_active=True))
    still_armed = fsm.process(_frame(0.5, v_sign_active=False))
    assert still_armed.click_mode is True


def test_pinch_fires_left_click_and_disarms() -> None:
    fsm = ClickFsm()
    fsm.process(_frame(0.0, v_sign_active=True))
    output = fsm.process(_frame(0.05, v_sign_active=True, pinch_close=True))
    assert output.click_event == ClickEvent(button="left", x=640.0, y=360.0)
    assert output.state == ClickState.IDLE
    assert output.click_mode is False


def test_pinch_uses_current_right_click_intent() -> None:
    fsm = ClickFsm()
    fsm.process(_frame(0.0, v_sign_active=True, right_click=False))
    fsm.process(_frame(0.02, v_sign_active=True, right_click=True))
    output = fsm.process(_frame(0.04, v_sign_active=True, pinch_close=True, right_click=False))
    assert output.click_event == ClickEvent(button="right", x=640.0, y=360.0)


def test_pinch_fires_during_v_sign_loss_grace_period() -> None:
    fsm = ClickFsm(v_sign_loss_debounce_s=0.3)
    fsm.process(_frame(0.0, v_sign_active=True))
    fsm.process(_frame(0.1, v_sign_active=False))
    output = fsm.process(_frame(0.15, pinch_close=True))
    assert output.click_event == ClickEvent(button="left", x=640.0, y=360.0)
    assert output.state == ClickState.IDLE


def test_orientation_updates_while_armed() -> None:
    fsm = ClickFsm()
    fsm.process(_frame(0.0, v_sign_active=True, right_click=False))
    output = fsm.process(_frame(0.01, v_sign_active=True, right_click=True))
    assert output.right_click_intent is True


def test_orientation_not_exposed_when_idle() -> None:
    fsm = ClickFsm()
    output = fsm.process(_frame(0.0, right_click=True))
    assert output.right_click_intent is False
