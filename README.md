# Nixie

A retro-styled local system dashboard served at `http://localhost:8765`.

Displays real-time stats: CPU, RAM, disk, network speed, ping, swap, TCP connections, IP addresses and more — all in a sleek amber-on-black Nixie-tube aesthetic.

---

## Screenshot

![Nixie Dashboard](https://raw.githubusercontent.com/JohnSina86/Nixie/feature/installer/screenshot.jpg)

---

## Requirements

- **Windows** 10 / 11
- **Python 3.x** — download from [python.org](https://www.python.org/downloads/)
  - ✅ Make sure to check **"Add Python to PATH"** during install

---

## First-Time Setup (run once)

Right-click `setup.ps1` → **Run with PowerShell**

This will automatically:
1. Check that Python is installed
2. Create a local virtual environment (`.venv`)
3. Upgrade `pip`
4. Install all dependencies from `requirements.txt`

> ⚠️ You only need to run `setup.ps1` **once**. After that, use `open_nixie.ps1` every time.

---

## Running Nixie

Right-click `open_nixie.ps1` → **Run with PowerShell**

- On **first launch** it will automatically trigger `setup.ps1` if setup hasn't been done yet
- Starts the server silently in the background
- Waits until the server is ready, then opens your default browser at `http://localhost:8765`
- If Nixie is already running, it just opens the browser — no duplicate processes

---

## Manual Run (advanced)

```powershell
.\.venv\Scripts\python.exe .\main.py
```

Then open: http://localhost:8765

Stream endpoint: http://localhost:8765/stream

---

## What's Monitored

| Metric | Details |
|---|---|
| **Network** | Download & upload speed (Mbps), live graph |
| **Ping** | Latency to google.com (ms) |
| **CPU** | Usage % + frequency (GHz) + sparkline |
| **RAM** | Used / Total (GB) |
| **Disk** | Space used (%), read/write speed (MB/s) |
| **Swap** | Used / Total (GB) |
| **IP** | Local IPv4 + Public (external) IP |
| **Processes** | Number of running processes |
| **TCP** | Established connections |
| **Date/Time** | Live clock |

---

## File Overview

| File | Purpose |
|---|---|
| `setup.ps1` | One-time installer — run this first |
| `open_nixie.ps1` | Daily launcher — run this every time |
| `main.py` | Python backend (HTTP server + SSE stream) |
| `index.html` | Frontend dashboard UI |
| `requirements.txt` | Python dependencies (`psutil`) |
