from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import numpy.typing as npt

from unmouse.gestures.angles import compute_joint_angle_vector
from unmouse.gestures.landmarks import NUM_HAND_LANDMARKS, HandLandmarks
from unmouse.gestures.mle import GestureTemplate, build_template, save_template
from unmouse.utils.paths import resource_path

DEFAULT_GESTURE_NAMES: tuple[str, ...] = ("v_sign", "pinch_close", "thumbs_up")
DEFAULT_SAMPLE_COUNT = 30
DEFAULT_SAMPLE_NOISE = 0.008
DEFAULT_CAPTURE_DURATION_S = 1.0
DEFAULT_CAPTURE_WARMUP_S = 0.2
DEFAULT_CAPTURE_FPS = 30.0


def default_gestures_dir() -> Path:
    return resource_path("assets/gestures")


def profile_gestures_dir(profile_dir: Path) -> Path:
    return profile_dir / "gestures"


def synthetic_landmarks(gesture: str) -> HandLandmarks:
    if gesture not in DEFAULT_GESTURE_NAMES:
        msg = f"unsupported gesture: {gesture}"
        raise ValueError(msg)

    points = np.zeros((NUM_HAND_LANDMARKS, 3), dtype=np.float64)
    points[0] = (0.50, 0.85, 0.0)
    points[9] = (0.50, 0.72, 0.0)
    points[13] = (0.56, 0.72, 0.0)
    points[17] = (0.62, 0.72, 0.0)
    points[5] = (0.44, 0.72, 0.0)
    points[1] = (0.38, 0.74, 0.0)

    if gesture == "v_sign":
        _extend_finger(points, (5, 6, 7, 8), (0.44, 0.72, 0.0), (0.40, 0.42, 0.0))
        _extend_finger(points, (9, 10, 11, 12), (0.50, 0.72, 0.0), (0.50, 0.40, 0.0))
        _curl_finger(points, (13, 14, 15, 16), (0.56, 0.72, 0.0))
        _curl_finger(points, (17, 18, 19, 20), (0.62, 0.72, 0.0))
        _curl_finger(points, (1, 2, 3, 4), (0.38, 0.74, 0.0))
    elif gesture == "pinch_close":
        pinch = (0.50, 0.56, 0.0)
        _extend_finger(points, (5, 6, 7, 8), (0.46, 0.72, 0.0), pinch)
        _extend_finger(points, (1, 2, 3, 4), (0.54, 0.74, 0.0), pinch)
        _curl_finger(points, (9, 10, 11, 12), (0.50, 0.72, 0.0))
        _curl_finger(points, (13, 14, 15, 16), (0.56, 0.72, 0.0))
        _curl_finger(points, (17, 18, 19, 20), (0.62, 0.72, 0.0))
    else:
        _extend_finger(points, (1, 2, 3, 4), (0.38, 0.74, 0.0), (0.34, 0.40, 0.0))
        for chain, base in (
            ((5, 6, 7, 8), (0.44, 0.72, 0.0)),
            ((9, 10, 11, 12), (0.50, 0.72, 0.0)),
            ((13, 14, 15, 16), (0.56, 0.72, 0.0)),
            ((17, 18, 19, 20), (0.62, 0.72, 0.0)),
        ):
            _curl_finger(points, chain, base)

    tuples = tuple((float(x), float(y), float(z)) for x, y, z in points)
    return HandLandmarks(points=tuples, handedness="Right")


def samples_from_landmarks(
    hand: HandLandmarks,
    *,
    count: int = DEFAULT_SAMPLE_COUNT,
    noise: float = DEFAULT_SAMPLE_NOISE,
    seed: int = 0,
) -> npt.NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    base = np.array(hand.points, dtype=np.float64)
    rows: list[npt.NDArray[np.float64]] = []
    for _ in range(count):
        jitter = base + rng.normal(0.0, noise, base.shape)
        tuples = tuple((float(x), float(y), float(z)) for x, y, z in jitter)
        jittered = HandLandmarks(points=tuples, handedness=hand.handedness)
        rows.append(compute_joint_angle_vector(jittered))
    return np.stack(rows, axis=0)


def build_default_template(
    gesture: str,
    *,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    sample_noise: float = DEFAULT_SAMPLE_NOISE,
    seed: int = 0,
) -> GestureTemplate:
    samples = samples_from_landmarks(
        synthetic_landmarks(gesture),
        count=sample_count,
        noise=sample_noise,
        seed=seed,
    )
    return build_template(gesture, samples, force_diagonal=True)


def enroll_from_samples(
    gesture: str,
    samples: npt.NDArray[np.float64],
    output_dir: Path,
) -> Path:
    template = build_template(gesture, samples, force_diagonal=True)
    path = output_dir / f"{gesture}.json"
    save_template(path, template)
    return path


def save_template_compact(path: Path, template: GestureTemplate) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(template.to_dict(), separators=(",", ":")),
        encoding="utf-8",
    )


def generate_default_templates(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    seeds = {"v_sign": 11, "pinch_close": 22, "thumbs_up": 33}
    written: list[Path] = []
    for gesture in DEFAULT_GESTURE_NAMES:
        template = build_default_template(gesture, seed=seeds[gesture])
        path = output_dir / f"{gesture}.json"
        save_template_compact(path, template)
        written.append(path)
    return written


def capture_angle_samples(
    *,
    camera_index: int = 0,
    duration_s: float = DEFAULT_CAPTURE_DURATION_S,
    warmup_s: float = DEFAULT_CAPTURE_WARMUP_S,
    target_fps: float = DEFAULT_CAPTURE_FPS,
) -> npt.NDArray[np.float64]:
    import time

    from unmouse.broker.camera import open_camera
    from unmouse.gestures.landmarks import MediaPipeHandDetector

    detector = MediaPipeHandDetector()
    try:
        capture = open_camera(camera_index)
    except RuntimeError as exc:
        detector.close()
        raise RuntimeError(str(exc)) from exc

    samples: list[npt.NDArray[np.float64]] = []
    frame_interval = 1.0 / target_fps
    started = time.monotonic()
    try:
        while True:
            loop_start = time.monotonic()
            elapsed = loop_start - started
            if elapsed >= duration_s + warmup_s:
                break

            ok, frame = capture.read()
            if not ok:
                time.sleep(frame_interval)
                continue

            frame_u8 = np.asarray(frame, dtype=np.uint8)
            result = detector.detect(frame_u8)
            if elapsed >= warmup_s and result.hands:
                samples.append(compute_joint_angle_vector(result.hands[0]))

            sleep_for = frame_interval - (time.monotonic() - loop_start)
            if sleep_for > 0:
                time.sleep(sleep_for)
    finally:
        capture.release()
        detector.close()

    if not samples:
        msg = "no hand samples captured during enrollment window"
        raise RuntimeError(msg)
    return np.stack(samples, axis=0)


def _extend_finger(
    points: npt.NDArray[np.float64],
    chain: tuple[int, ...],
    base: tuple[float, float, float],
    tip: tuple[float, float, float],
) -> None:
    _fill_chain(points, chain, base, tip)


def _curl_finger(
    points: npt.NDArray[np.float64],
    chain: tuple[int, ...],
    base: tuple[float, float, float],
) -> None:
    tip = (base[0], base[1] + 0.04, base[2] - 0.02)
    _fill_chain(points, chain, base, tip)


def _fill_chain(
    points: npt.NDArray[np.float64],
    chain: tuple[int, ...],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> None:
    start_arr = np.asarray(start, dtype=np.float64)
    end_arr = np.asarray(end, dtype=np.float64)
    span = max(len(chain) - 1, 1)
    for step, index in enumerate(chain):
        t = step / span
        points[index] = start_arr * (1.0 - t) + end_arr * t
