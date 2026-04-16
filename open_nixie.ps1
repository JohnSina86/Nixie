$ErrorActionPreference = "Stop"
$proj   = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv   = Join-Path $proj ".venv"
$pyExe  = Join-Path $venv "Scripts\python.exe"
$main   = Join-Path $proj "main.py"
$url    = "http://localhost:8765"
$flag   = Join-Path $proj ".setup_done"
$setup  = Join-Path $proj "setup.ps1"

if (-not (Test-Path $flag)) {
    & powershell -ExecutionPolicy Bypass -File $setup
    if (-not (Test-Path $flag)) { Read-Host "Setup failed. Press Enter to exit"; exit 1 }
}

if (-not (Test-Path $pyExe)) {
    Write-Host "ERROR: python not found in .venv" -ForegroundColor Red
    Read-Host "Press Enter to exit"; exit 1
}

$portInUse = (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) -ne $null
if ($portInUse) { Start-Process "http://localhost:8765"; exit 0 }

Write-Host "  Starting Nixie server..." -ForegroundColor Cyan
Start-Process -FilePath $pyExe -ArgumentList @($main) -WorkingDirectory $proj -WindowStyle Hidden

$maxWait = 10; $waited = 0; $ready = $false
do {
    Start-Sleep -Milliseconds 500; $waited += 0.5
    try { $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop; $ready = ($r.StatusCode -eq 200) } catch {}
} while (-not $ready -and $waited -lt $maxWait)

Write-Host "  Opening browser..." -ForegroundColor Green
Start-Process "http://localhost:8765"
