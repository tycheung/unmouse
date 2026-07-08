# Automated E2E Tests

Playwright and subprocess smoke tests complement the manual checklist in [`SMOKE_TEST.md`](SMOKE_TEST.md).

## What is covered

| Suite | File | Coverage |
|-------|------|----------|
| Panel UI | `tests/e2e/test_panel_playwright.py` | Launch/Stop, Pause, Settings save, profile create, Update check, Calibrate, Train Gestures |
| Onboarding & calibration | `tests/e2e/test_onboarding_calibration.py` | Full onboarding wizard, skip step, gesture enrollment hook, polynomial→offset calibrate chain |
| Launch smoke | `tests/e2e/test_launch_smoke.py` | `--smoke` entry point (Python + `MGGIST.exe`), harness HTTP bridge, build script presence |

Camera-heavy wizards (9-point overlay, 16-point overlay) are **mocked** in automated tests so CI does not require a webcam. Manual validation remains in `SMOKE_TEST.md`.

## Architecture

The control panel normally runs inside pywebview (`file://` + `js_api`). Playwright cannot drive that shell directly, so tests use an HTTP harness:

```
Playwright (Chromium)
    → http://127.0.0.1:<port>/  (Alpine UI + injected pywebview bridge)
    → POST /api/<method>        (JSON-RPC to PanelApi)
    → real PanelApi + mocked engine/camera/calibration where needed
```

Implementation: `tests/e2e/harness.py`

## Run locally

```powershell
poetry install --with dev
poetry run playwright install chromium
poetry run pytest tests/e2e -m e2e
```

Or use the helper script:

```powershell
.\scripts\run_e2e.ps1
```

Build the frozen exe first to include `MGGIST.exe` smoke tests:

```powershell
.\scripts\build_exe.ps1
poetry run pytest tests/e2e -m e2e
```

## Smoke entry point

`python -m unmouse --smoke` (and `MGGIST.exe --smoke`) verify imports, UI assets, and version without opening a window. CI runs this after PyInstaller builds the exe.

## CI

GitHub Actions installs Chromium, builds `MGGIST.exe`, then runs `pytest tests/e2e -m e2e`.

The Playwright E2E merge (`e6842ba`, `bae8f20`) has a **one-time** epic line-budget exception in [`scripts/epic_budget_overrides.json`](../scripts/epic_budget_overrides.json) (limit 1600). Later changes still use the 600-line cap.
