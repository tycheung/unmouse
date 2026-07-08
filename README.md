# unmouse

Webcam-based gaze tracking and hand-gesture control for **Windows**. Move the cursor with your eyes, click and scroll with hand gestures, and calibrate per profile from a lightweight control panel.

## Features

- Gaze-to-cursor tracking powered by [eyeGestures](https://pypi.org/project/eyeGestures/) (calibration, fixation, saccade, and blink detection built in)
- Guided gaze calibration wizard with per-profile model persistence
- Hand-gesture recognition (V-sign click mode, pinch click, thumbs-up scroll)
- UI snapping via accessibility tree and window chrome targets
- Control panel (Alpine.js + pywebview): onboarding, settings, enrollment, launch
- System tray integration with pause/resume and gaze-only mode
- Optional git/release update checker

## Requirements

- **Windows 10/11** (64-bit)
- **Python 3.10–3.13** for development ([Poetry](https://python-poetry.org/))
- Webcam
- Poetry lockfile committed for reproducible installs
- Core tracking dependencies are **required**: [`eyeGestures`](https://pypi.org/project/eyeGestures/) (gaze), `mediapipe` (hand landmarks), and `pyautogui` (pointer). The engine has no silent fallbacks — a missing dependency fails loudly at startup.

> **License note:** unmouse and its core dependency `eyeGestures` are both licensed under GPL-3.0. Distributed builds must comply with the GPL.

## Quick start (development)

```powershell
git clone git@github.com:tycheung/unmouse.git
cd unmouse
poetry install --with dev
poetry run unmouse
```

| Command | Action |
|---------|--------|
| `poetry run unmouse` | Open control panel (default) |
| `poetry run unmouse-engine` | Run tracking engine only |
| `python -m unmouse --engine` | Engine subprocess entry (used by Launch) |
| `python -m unmouse --smoke` | Import and asset smoke check (no UI) |

User data is stored under `%APPDATA%/unmouse/` (profiles, calibration, logs, settings).

## Quality gates

```powershell
poetry run ruff check src tests
poetry run mypy src
poetry run pytest --ignore=tests/e2e
.\scripts\run_e2e.ps1          # Playwright panel + launch smoke (after playwright install)
```

CI runs the same checks on `windows-latest`, a PyInstaller smoke build, and Playwright E2E tests (see `.github/workflows/ci.yml`).

Coverage floor is **85%** (`pyproject.toml`). Unit tests use `--ignore=tests/e2e`; E2E runs with `--no-cov`.

## Build release executable

```powershell
.\scripts\build_exe.ps1
```

Output: `dist/unmouse.exe` (single-file, windowed). The launcher spawns the engine as `unmouse.exe --engine` when frozen.

To regenerate the app icon only:

```powershell
poetry run python scripts/generate_icon.py
```

## Architecture

```
Control panel (pywebview + Alpine.js)
  └─ PanelApi → engine service, gesture enrollment, settings
  └─ Launch spawns unmouse.main:run_engine_cli (--engine)

Engine (main.py)
  └─ Video broker → gaze worker (eyeGestures tracker) + gesture worker (MediaPipe + MLE)
  └─ Action controller (snap, PyAutoGUI, gaze indicator)

Backends
  └─ Core backends are required: eyeGestures (gaze), MediaPipe (hands), PyAutoGUI (pointer)
  └─ Windows-only enhancements degrade gracefully: uiautomation, pystray, Tk/Win32 overlays
  └─ Unit tests inject fakes explicitly; no-op/null doubles live in the test suite
```

## Project layout

```
assets/ui/              Control panel HTML/CSS/Alpine.js (+ panel.js)
assets/gestures/        Default gesture templates
src/unmouse/            Application package
  main.py               Engine orchestrator and --engine CLI entry
  persistence.py        Shared settings persistence
  platform.py           Platform detection helpers
  launcher/             Panel shell, calibration wizards, onboarding, tray
    api_helpers.py      Panel API helpers and ActionResult
    services/           Engine lifecycle and panel state
  overlay/              Gaze indicator + shared Tk overlay helpers
  broker/               Video fan-out and camera helpers
  gaze/                 eyeGestures tracker + display mapping
  gestures/             MediaPipe + MLE classifier
  arbitrator/           Snap, actions, controller
tests/                  Unit, integration, and E2E (Playwright) tests
  fakes/                Shared test doubles (MockFrameSource, etc.)
unmouse.spec            PyInstaller spec
scripts/                build_exe.ps1, run_e2e.ps1, generate_icon.py
docs/SMOKE_TEST.md      Manual release checklist
docs/E2E_TEST.md        Automated Playwright + launch smoke tests
```

## Release testing

Before tagging a release, run `.\scripts\run_e2e.ps1` and walk through [docs/SMOKE_TEST.md](docs/SMOKE_TEST.md) on dev and frozen builds. See [docs/E2E_TEST.md](docs/E2E_TEST.md) for automated coverage details.

## License

Copyright (C) Nimbus Labs LLC.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See [LICENSE](LICENSE) for the full text.
