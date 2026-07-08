from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
README = REPO_ROOT / "README.md"
SMOKE_TEST = REPO_ROOT / "docs" / "SMOKE_TEST.md"


def test_ci_workflow_runs_quality_gates() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "windows-latest" in text
    for step in (
        "ruff check",
        "mypy",
        "pytest",
        "pyinstaller",
        "playwright",
        "e2e",
    ):
        assert step in text.lower()


def test_readme_documents_entry_points_and_build() -> None:
    text = README.read_text(encoding="utf-8")
    assert "poetry run unmouse" in text
    assert "unmouse.exe" in text
    assert "build_exe.ps1" in text
    assert "SMOKE_TEST.md" in text


def test_smoke_test_documents_automated_e2e() -> None:
    text = SMOKE_TEST.read_text(encoding="utf-8")
    assert "run_e2e.ps1" in text
    assert "E2E_TEST.md" in text


def test_smoke_test_covers_v1_flows() -> None:
    text = SMOKE_TEST.read_text(encoding="utf-8")
    for topic in (
        "onboarding",
        "polynomial",
        "offset",
        "gesture",
        "Pause",
        "gaze-only",
        "multi-monitor",
        "unmouse.exe",
    ):
        assert topic.lower() in text.lower()
