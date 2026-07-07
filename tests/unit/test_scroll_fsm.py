"""Unit tests for scroll activation FSM."""

from __future__ import annotations

from unmouse.gestures.scroll_fsm import (
    ScrollFrameInput,
    ScrollFsm,
    ScrollState,
)


def _frame(
    timestamp_s: float,
    *,
    thumbs_up_active: bool = False,
    thumb_angle_deg: float = 85.0,
    gaze_x: float = 500.0,
    gaze_y: float = 400.0,
) -> ScrollFrameInput:
    return ScrollFrameInput(
        timestamp_s=timestamp_s,
        thumbs_up_active=thumbs_up_active,
        thumb_angle_deg=thumb_angle_deg,
        gaze_x=gaze_x,
        gaze_y=gaze_y,
    )


def test_scroll_requires_500ms_dwell_before_activation() -> None:
    fsm = ScrollFsm(activation_delay_s=0.5)
    waiting = fsm.process(_frame(0.0, thumbs_up_active=True))
    waiting = fsm.process(_frame(0.2, thumbs_up_active=True))
    assert waiting.scroll_active is False
    assert waiting.scroll_tick is None
    active = fsm.process(_frame(0.5, thumbs_up_active=True))
    assert active.state == ScrollState.ACTIVE
    assert active.scroll_active is True


def test_active_scroll_emits_tick_at_gaze_point() -> None:
    fsm = ScrollFsm(activation_delay_s=0.5)
    fsm.process(_frame(0.0, thumbs_up_active=True))
    output = fsm.process(_frame(0.5, thumbs_up_active=True, thumb_angle_deg=85.0))
    assert output.scroll_tick is not None
    assert output.scroll_tick.x == 500.0
    assert output.scroll_tick.y == 400.0
    assert output.scroll_tick.delta > 0.0


def test_dead_zone_emits_no_tick_while_active() -> None:
    fsm = ScrollFsm(activation_delay_s=0.5)
    fsm.process(_frame(0.0, thumbs_up_active=True))
    output = fsm.process(_frame(0.5, thumbs_up_active=True, thumb_angle_deg=0.0))
    assert output.scroll_active is True
    assert output.scroll_tick is None


def test_release_debounce_disarms_after_200ms() -> None:
    fsm = ScrollFsm(activation_delay_s=0.5, release_debounce_s=0.2)
    fsm.process(_frame(0.0, thumbs_up_active=True))
    fsm.process(_frame(0.5, thumbs_up_active=True))
    fsm.process(_frame(0.6, thumbs_up_active=False))
    still_active = fsm.process(_frame(0.75, thumbs_up_active=False))
    assert still_active.scroll_active is True
    stopped = fsm.process(_frame(0.81, thumbs_up_active=False))
    assert stopped.state == ScrollState.IDLE
    assert stopped.scroll_active is False


def test_brief_release_within_debounce_stays_active() -> None:
    fsm = ScrollFsm(activation_delay_s=0.5, release_debounce_s=0.2)
    fsm.process(_frame(0.0, thumbs_up_active=True))
    fsm.process(_frame(0.5, thumbs_up_active=True))
    fsm.process(_frame(0.6, thumbs_up_active=False))
    resumed = fsm.process(_frame(0.7, thumbs_up_active=True))
    assert resumed.scroll_active is True
    ticking = fsm.process(_frame(0.71, thumbs_up_active=True, thumb_angle_deg=-85.0))
    assert ticking.scroll_tick is not None
    assert ticking.scroll_tick.delta < 0.0


def test_hold_timer_resets_if_gesture_released_before_activation() -> None:
    fsm = ScrollFsm(activation_delay_s=0.5)
    fsm.process(_frame(0.0, thumbs_up_active=True))
    fsm.process(_frame(0.2, thumbs_up_active=False))
    waiting = fsm.process(_frame(0.6, thumbs_up_active=True))
    assert waiting.scroll_active is False
