from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from unmouse.config import Settings
from unmouse.gestures.scroll_zones import DEFAULT_LOG_K, DEFAULT_V_MAX, scroll_speed

DEFAULT_SCROLL_RELEASE_DEBOUNCE_S = 0.2


class ScrollState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"


@dataclass(frozen=True)
class ScrollTick:
    x: float
    y: float
    delta: float


@dataclass(frozen=True)
class ScrollFrameInput:
    timestamp_s: float
    thumbs_up_active: bool
    thumb_angle_deg: float
    gaze_x: float
    gaze_y: float


@dataclass(frozen=True)
class ScrollFrameOutput:
    state: ScrollState
    scroll_active: bool
    scroll_tick: ScrollTick | None


class ScrollFsm:
    def __init__(
        self,
        *,
        activation_delay_s: float = 0.5,
        release_debounce_s: float = DEFAULT_SCROLL_RELEASE_DEBOUNCE_S,
        v_max: float = DEFAULT_V_MAX,
        log_k: float = DEFAULT_LOG_K,
    ) -> None:
        if activation_delay_s < 0 or release_debounce_s < 0:
            msg = "scroll timing values must be non-negative"
            raise ValueError(msg)
        self._activation_delay_s = activation_delay_s
        self._release_debounce_s = release_debounce_s
        self._v_max = v_max
        self._log_k = log_k
        self._state = ScrollState.IDLE
        self._hold_started_at: float | None = None
        self._released_at: float | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> ScrollFsm:
        return cls(
            activation_delay_s=settings.scroll_activation_delay_ms / 1000.0,
            release_debounce_s=settings.scroll_release_debounce_ms / 1000.0,
        )

    @property
    def state(self) -> ScrollState:
        return self._state

    def reset(self) -> None:
        self._state = ScrollState.IDLE
        self._hold_started_at = None
        self._released_at = None

    def process(self, frame: ScrollFrameInput) -> ScrollFrameOutput:
        if frame.thumbs_up_active:
            if self._state == ScrollState.IDLE:
                if self._hold_started_at is None:
                    self._hold_started_at = frame.timestamp_s
                elif frame.timestamp_s - self._hold_started_at >= self._activation_delay_s:
                    self._state = ScrollState.ACTIVE
            self._released_at = None
        elif self._state == ScrollState.IDLE:
            self._hold_started_at = None
        elif self._released_at is None:
            self._released_at = frame.timestamp_s
        elif frame.timestamp_s - self._released_at >= self._release_debounce_s:
            self._state = ScrollState.IDLE
            self._hold_started_at = None
            self._released_at = None

        scroll_tick = self._maybe_build_tick(frame)
        return ScrollFrameOutput(
            state=self._state,
            scroll_active=self._state == ScrollState.ACTIVE,
            scroll_tick=scroll_tick,
        )

    def _maybe_build_tick(self, frame: ScrollFrameInput) -> ScrollTick | None:
        if self._state != ScrollState.ACTIVE or not frame.thumbs_up_active:
            return None
        speed = scroll_speed(frame.thumb_angle_deg, v_max=self._v_max, k=self._log_k)
        if speed == 0.0:
            return None
        return ScrollTick(x=frame.gaze_x, y=frame.gaze_y, delta=speed)
