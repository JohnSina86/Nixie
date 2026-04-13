# =============================================================
# Nixie — Launcher (run this every time you want to use Nixie)
# Right-click → "Run with PowerShell"  OR  double-click
# =============================================================

$ErrorActionPreference = "Stop"
$proj   = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv   = Join-Path $proj ".venv"
$pyExe  = Join-Path $venv "Scripts\python.exe"
$main   = Join-Path $proj "main.py"
$url    = "http://localhost:8765"
$flag   = Join-Path $proj ".setup_done"
$setup  = Join-Path $proj "setup.ps1"

# ── Guard: run setup first if not done ────────────────────────
if (-not (Test-Path $flag)) {
    Write-Host ""
    Write-Host "  First-time setup required." -ForegroundColor Yellow
    Write-Host "  Launching setup.ps1 now..." -ForegroundColor Yellow
    Write-Host ""
    & powershell -ExecutionPolicy Bypass -File $setup
    # Re-check after setup
    if (-not (Test-Path $flag)) {
        Write-Host "  Setup did not complete. Exiting." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── Guard: verify the venv python exists ──────────────────────
if (-not (Test-Path $pyExe)) {
    Write-Host "  ERROR: .venv\Scripts\python.exe not found." -ForegroundColor Red
    Write-Host "  Please delete the .setup_done file and re-run setup.ps1." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ── Check if Nixie is already running on the port ─────────────
$portInUse = (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) -ne $null
if ($portInUse) {
    Write-Host "  Nixie is already running — opening browser." -ForegroundColor Green
    Start-Process $url
    exit 0
}

# ── Start server in background (hidden window) ────────────────
Write-Host "  Starting Nixie server..." -ForegroundColor Cyan
Start-Process -FilePath $pyExe `
              -ArgumentList @($main) `
              -WorkingDirectory $proj `
              -WindowStyle Hidden | Out-Null

# ── Wait for server to be ready (up to 10 seconds) ────────────
$maxWait = 10
$waited  = 0
do {
    Start-Sleep -Milliseconds 500
    $waited += 0.5
    $ready = $false
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
        $ready = ($r.StatusCode -eq 200)
    } catch { }
} while (-not $ready -and $waited -lt $maxWait)

if ($ready) {
    Write-Host "  Nixie is up — opening browser." -ForegroundColor Green
    Start-Process $url
} else {
    Write-Host "  Server did not respond in time. Try opening $url manually." -ForegroundColor Yellow
    Start-Process $url
}
