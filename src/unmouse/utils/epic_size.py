"""Parse git diff output and compute line-change totals for epic budgeting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_LINES = 600
DEFAULT_EXCLUDE = ("poetry.lock",)
DEFAULT_OVERRIDES_PATH = Path("scripts/epic_budget_overrides.json")


@dataclass(frozen=True)
class BudgetOverride:
    id: str
    commits: tuple[str, ...]
    max_lines: int
    reason: str


def load_budget_overrides(path: Path) -> tuple[BudgetOverride, ...]:
    if not path.is_file():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("overrides", [])
    overrides: list[BudgetOverride] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        overrides.append(
            BudgetOverride(
                id=str(entry["id"]),
                commits=tuple(str(c) for c in entry.get("commits", ())),
                max_lines=int(entry.get("max_lines", DEFAULT_MAX_LINES)),
                reason=str(entry.get("reason", "")),
            ),
        )
    return tuple(overrides)


def resolve_override(
    head_sha: str,
    stats: DiffStats,
    overrides: tuple[BudgetOverride, ...],
    *,
    range_commits: tuple[str, ...] = (),
) -> BudgetOverride | None:
    if not overrides:
        return None

    def commit_matches(sha: str, override: BudgetOverride) -> bool:
        normalized = sha.lower()
        return any(
            normalized == commit.lower() or normalized.startswith(commit.lower())
            for commit in override.commits
        )

    def override_for_commit(sha: str) -> BudgetOverride | None:
        for override in overrides:
            if commit_matches(sha, override):
                return override
        return None

    head_override = override_for_commit(head_sha)
    if head_override is not None and stats.total <= head_override.max_lines:
        return head_override

    if not range_commits:
        return None

    matched: BudgetOverride | None = None
    max_allowed = DEFAULT_MAX_LINES
    for sha in range_commits:
        entry = override_for_commit(sha)
        if entry is None:
            return None
        if entry.max_lines > max_allowed:
            max_allowed = entry.max_lines
            matched = entry
    if matched is not None and stats.total <= max_allowed:
        return matched
    return None


@dataclass(frozen=True)
class DiffStats:
    additions: int
    modifications: int

    @property
    def total(self) -> int:
        return self.additions + self.modifications


@dataclass(frozen=True)
class ParseResult:
    stats: DiffStats
    excluded_files: tuple[str, ...]


def parse_numstat_output(text: str, exclude: tuple[str, ...] = DEFAULT_EXCLUDE) -> ParseResult:
    additions = 0
    modifications = 0
    excluded: list[str] = []

    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_raw, removed_raw, path = parts
        if any(path.endswith(ex) or path == ex for ex in exclude):
            excluded.append(path)
            continue
        if added_raw == "-" or removed_raw == "-":
            continue
        additions += int(added_raw)
        modifications += int(removed_raw)

    return ParseResult(
        stats=DiffStats(additions=additions, modifications=modifications),
        excluded_files=tuple(excluded),
    )


def parse_patch_text(patch: str) -> DiffStats:
    """Count added/removed lines in unified diff text (for unit tests)."""
    additions = 0
    modifications = 0
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            modifications += 1
    return DiffStats(additions=additions, modifications=modifications)


def is_within_budget(stats: DiffStats, max_lines: int = DEFAULT_MAX_LINES) -> bool:
    return stats.total <= max_lines


def merge_parse_results(*results: ParseResult) -> ParseResult:
    additions = sum(r.stats.additions for r in results)
    modifications = sum(r.stats.modifications for r in results)
    excluded = tuple(dict.fromkeys(f for r in results for f in r.excluded_files))
    return ParseResult(
        stats=DiffStats(additions=additions, modifications=modifications),
        excluded_files=excluded,
    )


def count_untracked_lines(
    repo_root: Path, exclude: tuple[str, ...] = DEFAULT_EXCLUDE
) -> ParseResult:
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    additions = 0
    paths: list[str] = []
    for rel in result.stdout.splitlines():
        if any(rel.endswith(ex) or rel == ex for ex in exclude):
            paths.append(rel)
            continue
        file_path = repo_root / rel
        if file_path.is_file():
            additions += sum(1 for _ in file_path.open(encoding="utf-8", errors="ignore"))
    return ParseResult(
        stats=DiffStats(additions=additions, modifications=0),
        excluded_files=tuple(paths),
    )
