# unmouse v1 — Release Smoke Test

Manual checklist before tagging a release or shipping `dist/unmouse.exe` to testers.
Run on a **Windows 10/11** machine with a webcam. Prefer a second pass on a clean VM without Python installed when validating the frozen build.

**Automated coverage:** Run `.\scripts\run_e2e.ps1` (Playwright panel clicks, onboarding with mocked calibration, `--smoke` launch checks). See [`E2E_TEST.md`](E2E_TEST.md).

## Environment

- [ ] Windows 10 or 11, 64-bit
- [ ] Webcam connected and not in use by another app
- [ ] Single monitor pass completed
- [ ] Multi-monitor spot-check completed (secondary display if available)

## Dev install (`poetry run unmouse`)

- [ ] `poetry install` succeeds
- [ ] `poetry run pytest` passes locally
- [ ] Control panel opens (`poetry run unmouse`)

## First-run onboarding

- [ ] Fresh `%APPDATA%/unmouse` (or new profile) shows onboarding wizard
- [ ] Camera check step succeeds
- [ ] 9-point polynomial calibration completes and saves
- [ ] 16-point offset calibration completes and saves
- [ ] Gesture enrollment captures all three templates (`v_sign`, `pinch_close`, `thumbs_up`)
- [ ] Onboarding finish returns to main panel

## Settings & profiles

- [ ] Open Settings, adjust sensitivity / saccade / snap radius, Save
- [ ] Create, rename, activate, and delete a test profile
- [ ] Gaze mode toggle persists (`cursor_follow` vs `gaze_only`)

## Launch & tray

- [ ] **Launch** starts tracking and minimizes panel to tray
- [ ] Tray **Show Panel** restores the window
- [ ] Footer shows status after launch/stop and pause actions (refreshed on demand, not polled)
- [ ] **Stop Tracking** from panel stops the engine
- [ ] Tray **Stop** stops the engine

## Pause & gaze-only

- [ ] Tray **Pause / Resume** toggles paused state; cursor stops moving while paused
- [ ] Global pause hotkey toggles pause (default configured in settings)
- [ ] **Gaze-only mode**: indicator tracks gaze; OS cursor moves only in Click Mode
- [ ] Panel **Pause / Resume** button works while engine is running

## Calibration (post-onboarding)

- [ ] **Calibrate** runs offset wizard when polynomial exists
- [ ] **Calibrate** runs polynomial first when profile has no polynomial file
- [ ] Footer shows updated calibration date after save

## Gestures

- [ ] **Train Gestures** opens enrollment with camera preview
- [ ] Capture flow saves templates to active profile
- [ ] V-sign enters Click Mode; pinch click fires; thumbs-up scroll zone works in engine session

## Updates & diagnostics

- [ ] **Update Software** check returns a message (git dev install or release channel)
- [ ] `%APPDATA%/unmouse/logs/unmouse.log` receives entries after launch
- [ ] With `UNMOUSE_DEBUG=true`, `diagnostics.json` updates while engine runs

## Frozen executable (`dist/unmouse.exe`)

- [ ] `.\scripts\build_exe.ps1` produces `dist/unmouse.exe`
- [ ] Double-click opens control panel (no console flash)
- [ ] **Launch** spawns engine subprocess (`unmouse.exe --engine` internally)
- [ ] Calibrate and onboarding wizards work from the exe
- [ ] Copy exe to a machine **without Python** and repeat Launch + tray + pause checks

## Sign-off

| Tester | Date | Build (commit or exe) | Pass / Fail | Notes |
|--------|------|------------------------|-------------|-------|
|        |      |                        |             |       |
