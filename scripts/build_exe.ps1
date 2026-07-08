# Release build — run from repo root
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot\..

try {
    poetry install --extras gaze
    poetry run python scripts/generate_icon.py
    poetry run pytest -q
    poetry run pyinstaller unmouse.spec --noconfirm --clean
    Write-Host "Built: dist/unmouse.exe"
}
finally {
    Pop-Location
}
