"""Integration tests from gaze pipeline output through action controller."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from unmouse.arbitrator.actions import FakeActionDriver
from unmouse.arbitrator.controller import ActionController
from unmouse.arbitrator.snap import SnapRect, SnapTarget, StaticSnapProvider
from unmouse.broker.video_broker import MockFrameSource, VideoBroker
from unmouse.config import Settings
from unmouse.gaze.calibration import fit_calibration
from unmouse.gaze.pipeline import GazePipeline
from unmouse.gaze.thread import GazeWorker
from unmouse.gaze.tracker import MockGazeTracker
from unmouse.gestures.fsm import ClickFsm
from unmouse.gestures.landmarks import HandLandmarks, LandmarkDetectionResult
from unmouse.gestures.scroll_fsm import ScrollFsm
from unmouse.gestures.thread import GestureWorker
from unmouse.state import create_system_state

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "gestures"


def _load_fixture(name: str) -> HandLandmarks:
    data = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    points = tuple(tuple(float(value) for value in point) for point in data["points"])
    return HandLandmarks(points=points, handedness=str(data.get("handedness", "Right")))


class _SequenceDetector:
    def __init__(self, hands: list[HandLandmarks | None]) -> None:
        self._hands = hands
        self._index = 0

    def detect(self, frame: np.ndarray) -> LandmarkDetectionResult:
        _ = frame
        hand = self._hands[min(self._index, len(self._hands) - 1)]
        self._index += 1
        if hand is None:
            return LandmarkDetectionResult(hands=())
        return LandmarkDetectionResult(hands=(hand,))


def _calibration_points(
    screen_width: int,
    screen_height: int,
) -> list[tuple[float, float, float, float]]:
    xs = (0.0, 0.5, 1.0)
    ys = (0.0, 0.5, 1.0)
    points: list[tuple[float, float, float, float]] = []
    for raw_y in ys:
        for raw_x in xs:
            points.append(
                (
                    raw_x,
                    raw_y,
                    100 + (screen_width - 200) * raw_x,
                    100 + (screen_height - 200) * raw_y,
                ),
            )
    return points


def test_gaze_worker_feeds_controller_cursor_moves() -> None:
    settings = Settings(screen_width=800, screen_height=600, saccade_threshold_px=200.0)
    state = create_system_state(settings)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    broker = VideoBroker(state, settings, source=MockFrameSource([frame] * 10))
    gaze_worker = GazeWorker(
        state,
        settings,
        tracker=MockGazeTracker(x=450.0, y=275.0, confidence=0.92),
        pipeline=GazePipeline(settings),
    )
    driver = FakeActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )

    broker.start()
    gaze_worker.start()
    controller.start()

    deadline = time.time() + 2.0
    while time.time() < deadline:
        snap = state.get_gaze()
        if driver.moves and driver.moves[-1] == (int(round(snap.x)), int(round(snap.y))):
            if abs(snap.x - settings.screen_width / 2) > 1.0:
                break
        time.sleep(0.01)

    state.stop()
    controller.join(timeout=2.0)
    gaze_worker.join(timeout=2.0)
    broker.join(timeout=2.0)

    snap = state.get_gaze()
    assert driver.moves
    assert driver.moves[-1] == (int(round(snap.x)), int(round(snap.y)))
    assert abs(snap.x - settings.screen_width / 2) > 1.0
    assert abs(snap.y - settings.screen_height / 2) > 1.0


def test_gaze_to_action_applies_calibration_before_controller() -> None:
    settings = Settings(screen_width=820, screen_height=620, saccade_threshold_px=200.0)
    model = fit_calibration(_calibration_points(settings.screen_width, settings.screen_height))
    pipeline = GazePipeline(settings, calibration=model)
    state = create_system_state(settings)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    broker = VideoBroker(state, settings, source=MockFrameSource([frame] * 8))
    gaze_worker = GazeWorker(
        state,
        settings,
        tracker=MockGazeTracker(x=1.0, y=1.0, confidence=0.95),
        pipeline=pipeline,
    )
    driver = FakeActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )

    broker.start()
    gaze_worker.start()
    controller.start()

    deadline = time.time() + 2.0
    while time.time() < deadline:
        snap = state.get_gaze()
        if driver.moves and driver.moves[-1] == (int(round(snap.x)), int(round(snap.y))):
            if abs(snap.x - 720.0) < 1.0 and abs(snap.y - 520.0) < 1.0:
                break
        time.sleep(0.01)

    state.stop()
    controller.join(timeout=2.0)
    gaze_worker.join(timeout=2.0)
    broker.join(timeout=2.0)

    snap = state.get_gaze()
    assert driver.moves[-1] == (720, 520)
    assert abs(snap.x - 720.0) < 1.0
    assert abs(snap.y - 520.0) < 1.0


def test_gaze_to_action_snaps_cursor_to_target() -> None:
    settings = Settings(screen_width=800, screen_height=600, snap_radius_px=80.0)
    state = create_system_state(settings)
    state.set_gaze(103.0, 97.0, 0.95)
    driver = FakeActionDriver()
    snap_target = SnapTarget(
        target_id="save",
        bounds=SnapRect(x=90.0, y=90.0, width=20.0, height=20.0),
    )
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider((snap_target,)),
        enable_overlay=False,
    )
    controller.tick(timestamp_s=0.0)
    assert driver.moves[-1] == (100, 100)


def test_gaze_to_action_executes_gesture_click_at_gaze_point() -> None:
    settings = Settings(
        screen_width=800,
        screen_height=600,
        scroll_activation_delay_ms=0,
    )
    state = create_system_state(settings)
    state.set_gaze(610.0, 410.0, 0.93)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    from unmouse.gestures.enrollment import default_gestures_dir
    from unmouse.gestures.mle import load_gesture_library

    gesture_worker = GestureWorker(
        state,
        settings,
        detector=_SequenceDetector([_load_fixture("v_sign"), _load_fixture("pinch_close")]),
        library=load_gesture_library(default_gestures_dir()),
        click_fsm=ClickFsm(),
        scroll_fsm=ScrollFsm(activation_delay_s=0.0),
    )
    driver = FakeActionDriver()
    controller = ActionController(
        state,
        settings,
        driver=driver,
        snap_orchestrator=StaticSnapProvider(()),
        enable_overlay=False,
    )
    controller.start()
    gesture_worker.process_frame(frame, timestamp_s=0.0)
    gesture_worker.process_frame(frame, timestamp_s=0.05)

    deadline = time.time() + 2.0
    while time.time() < deadline and not driver.clicks:
        time.sleep(0.01)

    controller.stop()
    controller.join(timeout=2.0)

    assert driver.clicks == [(610, 410, "left")]
