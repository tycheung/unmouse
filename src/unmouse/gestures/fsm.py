from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from unmouse.config import Settings

DEFAULT_V_SIGN_LOSS_DEBOUNCE_S = 0.3
ClickButton = Literal["left", "right"]


class ClickState(str, Enum):
    IDLE = "idle"
    ARMED = "armed"


@dataclass(frozen=True)
class ClickEvent:
    button: ClickButton
    x: float
    y: float


@dataclass(frozen=True)
class ClickFrameInput:
    timestamp_s: float
    v_sign_active: bool
    pinch_close: bool
    right_click: bool
    gaze_x: float
    gaze_y: float


@dataclass(frozen=True)
class ClickFrameOutput:
    state: ClickState
    click_mode: bool
    right_click_intent: bool
    click_event: ClickEvent | None


class ClickFsm:
    def __init__(self, v_sign_loss_debounce_s: float = DEFAULT_V_SIGN_LOSS_DEBOUNCE_S) -> None:
        if v_sign_loss_debounce_s <= 0:
            msg = "v_sign_loss_debounce_s must be positive"
            raise ValueError(msg)
        self._debounce_s = v_sign_loss_debounce_s
        self._state = ClickState.IDLE
        self._right_click_intent = False
        self._v_sign_lost_at: float | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> ClickFsm:
        return cls(v_sign_loss_debounce_s=settings.v_sign_loss_debounce_ms / 1000.0)

    @property
    def state(self) -> ClickState:
        return self._state

    def reset(self) -> None:
        self._state = ClickState.IDLE
        self._right_click_intent = False
        self._v_sign_lost_at = None

    def process(self, frame: ClickFrameInput) -> ClickFrameOutput:
        click_event: ClickEvent | None = None

        if self._state == ClickState.IDLE:
            if frame.v_sign_active:
                self._state = ClickState.ARMED
                self._right_click_intent = frame.right_click
                self._v_sign_lost_at = None
        elif self._state == ClickState.ARMED:
            if frame.pinch_close:
                button: ClickButton = "right" if self._right_click_intent else "left"
                click_event = ClickEvent(button=button, x=frame.gaze_x, y=frame.gaze_y)
                self._state = ClickState.IDLE
                self._right_click_intent = False
                self._v_sign_lost_at = None
            elif frame.v_sign_active:
                self._right_click_intent = frame.right_click
                self._v_sign_lost_at = None
            else:
                if self._v_sign_lost_at is None:
                    self._v_sign_lost_at = frame.timestamp_s
                elif frame.timestamp_s - self._v_sign_lost_at >= self._debounce_s:
                    self._state = ClickState.IDLE
                    self._right_click_intent = False
                    self._v_sign_lost_at = None

        armed = self._state == ClickState.ARMED
        return ClickFrameOutput(
            state=self._state,
            click_mode=armed,
            right_click_intent=self._right_click_intent if armed else False,
            click_event=click_event,
        )
