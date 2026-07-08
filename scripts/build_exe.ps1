# Release build — run from repo root
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot\..

try {
    poetry install
    poetry run python scripts/generate_icon.py
    poetry run pytest -q
    poetry run pyinstaller mggist.spec --noconfirm --clean
    Write-Host "Built: dist/MGGIST.exe"
}
finally {
    Pop-Location
}
