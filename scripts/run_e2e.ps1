# Run automated end-to-end tests (Playwright + launch smoke).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Installing Playwright Chromium if needed..."
poetry run playwright install chromium

Write-Host "Running E2E suite..."
poetry run pytest tests/e2e -m e2e --no-cov @args
