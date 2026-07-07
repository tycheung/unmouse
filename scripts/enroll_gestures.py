"""CLI for gesture template enrollment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from unmouse.config import get_settings
from unmouse.gestures.enrollment import (
    DEFAULT_GESTURE_NAMES,
    capture_angle_samples,
    default_gestures_dir,
    enroll_from_samples,
    generate_default_templates,
    profile_gestures_dir,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enroll MLE gesture templates for unmouse.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate-defaults",
        help="Write bundled default templates to assets/gestures",
    )
    generate.add_argument(
        "--output",
        type=Path,
        default=default_gestures_dir(),
        help="Directory for default gesture JSON files",
    )

    enroll = subparsers.add_parser("enroll", help="Enroll a gesture template")
    enroll.add_argument("--gesture", required=True, choices=DEFAULT_GESTURE_NAMES)
    enroll.add_argument(
        "--output-dir",
        type=Path,
        help="Profile gestures directory (defaults to active profile)",
    )
    enroll.add_argument("--camera", type=int, default=0)
    enroll.add_argument("--duration", type=float, default=1.0)
    enroll.add_argument(
        "--samples-file",
        type=Path,
        help="Optional .npy file with shape (N, FEATURE_DIM) instead of live capture",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "generate-defaults":
        paths = generate_default_templates(args.output)
        for path in paths:
            print(f"wrote {path}")
        return 0

    output_dir = args.output_dir
    if output_dir is None:
        settings = get_settings()
        output_dir = profile_gestures_dir(settings.profile_dir)

    if args.samples_file is not None:
        samples = np.load(args.samples_file)
        if samples.ndim != 2:
            print("samples file must contain a 2D array", file=sys.stderr)
            return 1
    else:
        try:
            samples = capture_angle_samples(
                camera_index=args.camera,
                duration_s=args.duration,
            )
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    path = enroll_from_samples(args.gesture, samples, output_dir)
    print(f"enrolled {args.gesture} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
