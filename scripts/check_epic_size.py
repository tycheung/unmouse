"""CLI wrapper for epic diff line budget checks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from unmouse.utils.epic_size import (
    DEFAULT_EXCLUDE,
    DEFAULT_MAX_LINES,
    ParseResult,
    count_untracked_lines,
    is_within_budget,
    merge_parse_results,
    parse_numstat_output,
)


def run_git_diff(base_ref: str, repo_root: Path, cached: bool = False) -> str:
    cmd = ["git", "diff", "--numstat"]
    if cached:
        cmd.append("--cached")
    cmd.append(base_ref)
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git diff failed: {result.returncode}")
    return result.stdout


def collect_worktree_diff(base_ref: str, repo_root: Path, exclude: tuple[str, ...]) -> ParseResult:
    parts = [
        parse_numstat_output(run_git_diff(base_ref, repo_root), exclude=exclude),
        parse_numstat_output(run_git_diff(base_ref, repo_root, cached=True), exclude=exclude),
        count_untracked_lines(repo_root, exclude=exclude),
    ]
    return merge_parse_results(*parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce epic diff line budget.")
    parser.add_argument("--base-ref", default="main", help="Git ref to diff against")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Max additions + modifications (default: {DEFAULT_MAX_LINES})",
    )
    parser.add_argument("--exclude", action="append", default=[], help="Extra paths to exclude")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    exclude = DEFAULT_EXCLUDE + tuple(args.exclude)

    try:
        result = collect_worktree_diff(args.base_ref, args.repo_root, exclude)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    stats = result.stats
    print(
        f"Diff vs {args.base_ref}: +{stats.additions} / -{stats.modifications} "
        f"= {stats.total} changed lines (limit {args.max_lines})"
    )
    if result.excluded_files:
        print(f"Excluded: {', '.join(result.excluded_files)}")

    if not is_within_budget(stats, args.max_lines):
        print(
            f"FAIL: {stats.total} lines exceed budget of {args.max_lines}. "
            "Split this epic into smaller changes.",
            file=sys.stderr,
        )
        return 1

    print("OK: within epic line budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
