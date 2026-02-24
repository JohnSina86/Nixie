import asyncio
import json
import re
import sys
import psutil
import time
import socket
import urllib.request
from datetime import datetime

PORT       = 8765
PING_HOST  = "google.com"
PING_EVERY = 5
HTML_FILE  = "index.html"


def detect_interface():
    SKIP = {"lo", "loopback", "tailscale", "tun", "tap", "veth", "docker", "wsl", "virtual"}
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters(pernic=True)

    for name in io:
        lower = name.lower()
        if any(s in lower for s in SKIP):
            continue
        if name in stats and stats[name].isup:
            if any(k in lower for k in ("ethernet", "eth", "wi-fi", "wifi", "wlan", "en0", "en1")):
                return name

    for name in io:
        lower = name.lower()
        if any(s in lower for s in SKIP):
            continue
        if name in stats and stats[name].isup:
            return name

    return next(iter(io)) if io else "unknown"


IFACE = detect_interface()
print(f"[nixie] Interface: {IFACE}")


# ── Globals ──────────────────────────────────────────────────────
_ping_ms    = -1.0
_cpu_pct    = 0.0
_cpu_freq   = 0.0
_ram_used   = 0.0
_ram_total  = 0.0
_disk_space = -1.0
_disk_read  = 0.0
_disk_write = 0.0
_local_ip   = "?.?.?.?"
_public_ip  = "?.?.?.?"
_down       = 0.0
_up         = 0.0
_processes  = 0
_swap_used  = 0.0
_swap_total = 0.0
_tcp_conns  = 0

_prev_net = psutil.net_io_counters(pernic=True).get(IFACE)
_prev_disk = psutil.disk_io_counters()


# ── Ping ─────────────────────────────────────────────────────────
async def ping_loop():
    global _ping_ms

    args = (
        ["ping", "-n", "1", "-w", "1000", PING_HOST]
        if sys.platform == "win32"
        else ["ping", "-c", "1", "-W", "1", PING_HOST]
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        m = re.search(r"time[=<]([\d.]+)", out.decode(errors="ignore"))
        _ping_ms = round(float(m.group(1)), 1) if m else -1.0
    except Exception:
        _ping_ms = -1.0

    while True:
        try:
            if sys.platform == "win32":
                CREATE_NO_WINDOW = 0x08000000
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )

            out, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
            m = re.search(r"time[=<]([\d.]+)", out.decode(errors="ignore"))
            _ping_ms = round(float(m.group(1)), 1) if m else -1.0
        except Exception:
            _ping_ms = -1.0

        await asyncio.sleep(PING_EVERY)


# ── Public IP ────────────────────────────────────────────────────
async def public_ip_loop():
    global _public_ip

    def _fetch():
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=8) as r:
                return r.read().decode().strip()
        except Exception:
            return None

    while True:
        result = await asyncio.to_thread(_fetch)
        if result:
            _public_ip = result
        await asyncio.sleep(300)


# ── System metrics ───────────────────────────────────────────────
async def metrics_loop():
    global _cpu_pct, _cpu_freq, _ram_used, _ram_total
    global _disk_space, _local_ip
    global _processes, _swap_used, _swap_total, _tcp_conns

    def _collect():
        d = {}

        # CPU
        d["cpu_pct"] = psutil.cpu_percent(interval=None)
        try:
            freq = psutil.cpu_freq()
            d["cpu_freq"] = round(freq.current / 1000, 2) if freq else 0.0
        except Exception:
            d["cpu_freq"] = 0.0

        # RAM
        try:
            mem = psutil.virtual_memory()
            d["ram_used"] = round(mem.used / (1024**3), 1)
            d["ram_total"] = round(mem.total / (1024**3), 1)
        except Exception:
            pass

        # Swap
        try:
            swap = psutil.swap_memory()
            d["swap_used"] = round(swap.used / (1024**3), 1)
            d["swap_total"] = round(swap.total / (1024**3), 1)
        except Exception:
            d["swap_used"] = 0.0
            d["swap_total"] = 0.0

        # Disk space
        try:
            d["disk_space"] = psutil.disk_usage("C:\\").percent
        except Exception:
            d["disk_space"] = -1.0

        # Local IP
        try:
            for addr in psutil.net_if_addrs().get(IFACE, []):
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    d["local_ip"] = addr.address
                    break
        except Exception:
            pass

        # Processes
        try:
            d["processes"] = len(psutil.pids())
        except Exception:
            d["processes"] = 0

        # TCP connections
        try:
            conns = psutil.net_connections(kind="tcp")
            d["tcp_conns"] = len([c for c in conns if c.status == "ESTABLISHED"])
        except (psutil.AccessDenied, PermissionError):
            d["tcp_conns"] = -1  # show '--' in UI, not a crash
        except Exception:
            d["tcp_conns"] = 0

        return d

    while True:
        d = await asyncio.to_thread(_collect)
        _cpu_pct = d.get("cpu_pct", _cpu_pct)
        _cpu_freq = d.get("cpu_freq", _cpu_freq)
        _ram_used = d.get("ram_used", _ram_used)
        _ram_total = d.get("ram_total", _ram_total)
        _swap_used = d.get("swap_used", _swap_used)
        _swap_total = d.get("swap_total", _swap_total)
        _disk_space = d.get("disk_space", _disk_space)
        _local_ip = d.get("local_ip", _local_ip)
        _processes = d.get("processes", _processes)
        _tcp_conns = d.get("tcp_conns", _tcp_conns)
        await asyncio.sleep(1)


# ── Network + Disk I/O ───────────────────────────────────────────
async def net_loop():
    global _prev_net, _down, _up, _prev_disk, _disk_read, _disk_write

    def _collect():
        return (
            psutil.net_io_counters(pernic=True).get(IFACE),
            psutil.disk_io_counters()
        )

    while True:
        curr, disk = await asyncio.to_thread(_collect)

        if curr and _prev_net:
            _down = max(round((curr.bytes_recv - _prev_net.bytes_recv) * 8 / 1_000_000, 2), 0)
            _up = max(round((curr.bytes_sent - _prev_net.bytes_sent) * 8 / 1_000_000, 2), 0)

        if curr:
            _prev_net = curr

        if disk and _prev_disk:
            _disk_read = max(round((disk.read_bytes - _prev_disk.read_bytes) / (1024**2), 1), 0)
            _disk_write = max(round((disk.write_bytes - _prev_disk.write_bytes) / (1024**2), 1), 0)

        _prev_disk = disk
        await asyncio.sleep(1)


# ── Sample snapshot ──────────────────────────────────────────────
def sample() -> dict:
    return {
        "down": _down,
        "up": _up,
        "ping": _ping_ms,
        "cpu": max(_cpu_pct, 0),
        "cpu_freq": _cpu_freq,
        "ram_used": _ram_used,
        "ram_total": _ram_total,
        "swap_used": _swap_used,
        "swap_total": _swap_total,
        "disk_space": max(_disk_space, 0),
        "disk_read": _disk_read,
        "disk_write": _disk_write,
        "local_ip": _local_ip,
        "public_ip": _public_ip,
        "processes": _processes,
        "tcp_conns": _tcp_conns,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── HTTP server ──────────────────────────────────────────────────
_SSE_HEADER = (
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: text/event-stream\r\n"
    "Cache-Control: no-cache\r\n"
    "Connection: keep-alive\r\n"
    "Access-Control-Allow-Origin: *\r\n\r\n"
).encode()


async def handle_sse(writer: asyncio.StreamWriter):
    writer.write(_SSE_HEADER)
    await writer.drain()
    try:
        while True:
            writer.write(f"data: {json.dumps(sample())}\n\n".encode())
            await writer.drain()
            await asyncio.sleep(1)
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle_html(writer: asyncio.StreamWriter):
    try:
        with open(HTML_FILE, "rb") as f:
            body = f.read()

        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode()

        writer.write(header + body)
    except FileNotFoundError:
        writer.write(b"HTTP/1.1 404 Not Found\r\n\r\nindex.html not found")

    await writer.drain()
    writer.close()


async def dispatch(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        raw = await asyncio.wait_for(reader.read(2048), timeout=5)
        first = raw.decode(errors="ignore").split("\r\n")[0]
        path = first.split(" ")[1] if len(first.split(" ")) > 1 else "/"
        await (handle_sse(writer) if path == "/stream" else handle_html(writer))
    except Exception:
        writer.close()


async def main():
    asyncio.create_task(ping_loop())
    asyncio.create_task(public_ip_loop())
    asyncio.create_task(metrics_loop())
    asyncio.create_task(net_loop())

    server = await asyncio.start_server(dispatch, "0.0.0.0", PORT)
    print(f"[nixie] Running at http://localhost:{PORT}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
