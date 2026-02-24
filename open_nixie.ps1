# run_nixie_background.ps1
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
$py   = Join-Path $proj ".venv\Scripts\python.exe"
$main = Join-Path $proj "main.py"
$url  = "http://localhost:8765"

# Start the server in the background (hidden window)
Start-Process -FilePath $py -ArgumentList @($main) -WorkingDirectory $proj -WindowStyle Hidden | Out-Null  # starts detached [web:547]

# Give it a moment to bind the port, then open the UI manually in your default browser
Start-Sleep -Seconds 1
Start-Process $url  # opens default browser [web:547]
