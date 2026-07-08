"""Tests for epic diff line budget tooling."""

from unmouse.utils.epic_size import (
    BudgetOverride,
    DiffStats,
    merge_parse_results,
    parse_numstat_output,
    parse_patch_text,
    resolve_override,
)


def test_parse_numstat_counts_additions_and_modifications() -> None:
    text = "10\t5\tsrc/foo.py\n3\t1\tREADME.md\n"
    result = parse_numstat_output(text)
    assert result.stats == DiffStats(additions=13, modifications=6)
    assert result.stats.total == 19
    assert result.excluded_files == ()


def test_parse_numstat_excludes_lockfile() -> None:
    text = "500\t0\tpoetry.lock\n2\t1\tsrc/a.py\n"
    result = parse_numstat_output(text)
    assert result.stats.total == 3
    assert result.excluded_files == ("poetry.lock",)


def test_parse_numstat_skips_binary_placeholder() -> None:
    text = "-\t-\tassets/icon.ico\n4\t0\tsrc/b.py\n"
    result = parse_numstat_output(text)
    assert result.stats == DiffStats(additions=4, modifications=0)


def test_parse_patch_text_unified_diff() -> None:
    patch = """--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,3 @@
 line
+added
-old
"""
    stats = parse_patch_text(patch)
    assert stats.additions == 1
    assert stats.modifications == 1
    assert stats.total == 2


def test_merge_parse_results_sums_totals() -> None:
    a = parse_numstat_output("2\t1\ta.py\n")
    b = parse_numstat_output("3\t0\tb.py\n")
    merged = merge_parse_results(a, b)
    assert merged.stats.total == 6


def test_resolve_override_allows_one_time_exception() -> None:
    stats = DiffStats(additions=1200, modifications=30)
    overrides = (
        BudgetOverride(
            id="playwright-e2e",
            commits=("e6842ba",),
            max_lines=1600,
            reason="One-time E2E infrastructure",
        ),
    )
    matched = resolve_override(
        "e6842ba1deadbeef",
        stats,
        overrides,
        range_commits=("e6842ba1deadbeef",),
    )
    assert matched is not None
    assert matched.id == "playwright-e2e"


def test_resolve_override_rejects_when_over_override_limit() -> None:
    stats = DiffStats(additions=1700, modifications=0)
    overrides = (
        BudgetOverride(
            id="playwright-e2e",
            commits=("e6842ba",),
            max_lines=1600,
            reason="One-time E2E infrastructure",
        ),
    )
    assert resolve_override("e6842ba", stats, overrides) is None


def test_resolve_override_rejects_when_range_includes_unlisted_commit() -> None:
    stats = DiffStats(additions=1200, modifications=30)
    overrides = (
        BudgetOverride(
            id="playwright-e2e",
            commits=("e6842ba",),
            max_lines=1600,
            reason="One-time E2E infrastructure",
        ),
    )
    assert (
        resolve_override(
            "ffffffff",
            stats,
            overrides,
            range_commits=("e6842ba", "ffffffff"),
        )
        is None
    )
