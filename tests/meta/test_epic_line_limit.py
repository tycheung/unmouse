"""Tests for epic diff line budget tooling."""

from unmouse.utils.epic_size import (
    DiffStats,
    merge_parse_results,
    parse_numstat_output,
    parse_patch_text,
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
