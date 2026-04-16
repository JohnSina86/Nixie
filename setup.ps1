# =============================================================
# Nixie — One-Time Setup Installer
# Run this once: Right-click -> "Run with PowerShell"
# =============================================================

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Nixie Setup - First-Time Installation  " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/4] Checking for Python..." -ForegroundColor Yellow
try {
    $pyVer = & py --version 2>&1
    Write-Host "      Found: $pyVer" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "  ERROR: Python not found." -ForegroundColor Red
    Write-Host "  Please install Python 3.x from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "  Make sure to check 'Add Python to PATH' during install." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

$venv = Join-Path $proj ".venv"
if (Test-Path $venv) {
    Write-Host "[2/4] Virtual environment already exists - skipping creation." -ForegroundColor Green
}
else {
    Write-Host "[2/4] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    & py -m venv $venv
    Write-Host "      Done." -ForegroundColor Green
}

Write-Host "[3/4] Upgrading pip..." -ForegroundColor Yellow
$pipExe = Join-Path $venv "Scripts\\pip.exe"
& $pipExe install --upgrade pip --quiet
Write-Host "      Done." -ForegroundColor Green

Write-Host "[4/4] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
$reqFile = Join-Path $proj "requirements.txt"
if (-not (Test-Path $reqFile)) {
    Write-Host "  ERROR: requirements.txt not found in $proj" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

& $pipExe install -r $reqFile --quiet
Write-Host "      Done." -ForegroundColor Green

$flagFile = Join-Path $proj ".setup_done"
"Setup completed" | Out-File $flagFile -Encoding utf8

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Cyan
Write-Host "  Run 'open_nixie.ps1' to start Nixie." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"