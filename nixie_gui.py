# nixie_gui.py — full PySide6 native rewrite of Nixie dashboard
# Drop-in replacement for main.py + index.html
# Requirements: pip install PySide6 psutil

import sys, re, socket, time, asyncio, threading, urllib.request
from datetime import datetime
from collections import deque

import psutil
from PySide6.QtCore import (Qt, QTimer, QThread, Signal, QObject,
                             QPointF, QRectF, QSize)
from PySide6.QtGui  import (QPainter, QPen, QColor, QFont, QFontDatabase,
                             QLinearGradient, QPainterPath, QBrush,
                             QPalette, QPolygonF)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                                QGridLayout, QVBoxLayout, QHBoxLayout,
                                QLabel, QSizePolicy, QFrame)

AMBER      = QColor("#ff6600")
AMBER_DIM  = QColor("#7a3300")
AMBER_GLOW = QColor("#ff4400")
BG         = QColor("#050505")
TUBE_BG    = QColor("#0d0d0d")
BORDER     = QColor("#1e0a00")
PING_HOST  = "google.com"
GRAPH_LEN  = 60


def detect_interface():
    SKIP = {"lo","loopback","tailscale","tun","tap","veth","docker","wsl","virtual"}
    stats = psutil.net_if_stats()
    io    = psutil.net_io_counters(pernic=True)
    for name in io:
        lower = name.lower()
        if any(s in lower for s in SKIP): continue
        if name in stats and stats[name].isup:
            if any(k in lower for k in ("ethernet","eth","wi-fi","wifi","wlan","en0","en1")):
                return name
    for name in io:
        lower = name.lower()
        if any(s in lower for s in SKIP): continue
        if name in stats and stats[name].isup: return name
    return next(iter(io)) if io else "unknown"

IFACE = detect_interface()


class MetricsWorker(QObject):
    updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._running   = True
        self._prev_net  = psutil.net_io_counters(pernic=True).get(IFACE)
        self._prev_disk = psutil.disk_io_counters()
        self._public_ip = "fetching..."
        self._ping_ms   = -1.0
        self._last_pub  = 0.0
        self._last_ping = 0.0

    def _do_ping(self):
        args = (["ping","-n","1","-w","1000", PING_HOST]
                if sys.platform=="win32"
                else ["ping","-c","1","-W","1", PING_HOST])
        try:
            import subprocess
            r = subprocess.run(args, capture_output=True, timeout=3,
                               creationflags=0x08000000 if sys.platform=="win32" else 0)
            m = re.search(r"time[=<]([\d.]+)", r.stdout.decode(errors="ignore"))
            self._ping_ms = round(float(m.group(1)),1) if m else -1.0
        except Exception:
            self._ping_ms = -1.0

    def _do_public_ip(self):
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=8) as r:
                self._public_ip = r.read().decode().strip()
        except Exception:
            self._public_ip = "unavailable"

    def run(self):
        threading.Thread(target=self._do_ping,      daemon=True).start()
        threading.Thread(target=self._do_public_ip, daemon=True).start()

        while self._running:
            now = time.monotonic()
            if now - self._last_ping >= 5:
                self._last_ping = now
                threading.Thread(target=self._do_ping, daemon=True).start()
            if now - self._last_pub >= 300:
                self._last_pub = now
                threading.Thread(target=self._do_public_ip, daemon=True).start()

            d = {}
            d["cpu"] = psutil.cpu_percent(interval=None)
            try:
                freq = psutil.cpu_freq()
                d["cpu_freq"] = round(freq.current/1000, 2) if freq else 0.0
            except Exception:
                d["cpu_freq"] = 0.0

            try:
                mem = psutil.virtual_memory()
                d["ram_used"]  = round(mem.used  / (1024**3), 1)
                d["ram_total"] = round(mem.total / (1024**3), 1)
            except Exception:
                d["ram_used"] = d["ram_total"] = 0.0

            try:
                sw = psutil.swap_memory()
                d["swap_used"]  = round(sw.used  / (1024**3), 1)
                d["swap_total"] = round(sw.total / (1024**3), 1)
            except Exception:
                d["swap_used"] = d["swap_total"] = 0.0

            try:
                d["disk_space"] = psutil.disk_usage("C:\\").percent
            except Exception:
                d["disk_space"] = -1.0

            curr = psutil.net_io_counters(pernic=True).get(IFACE)
            if curr and self._prev_net:
                d["down"] = max(round((curr.bytes_recv - self._prev_net.bytes_recv)*8/1e6, 2), 0)
                d["up"]   = max(round((curr.bytes_sent - self._prev_net.bytes_sent)*8/1e6, 2), 0)
            else:
                d["down"] = d["up"] = 0.0
            if curr: self._prev_net = curr

            disk = psutil.disk_io_counters()
            if disk and self._prev_disk:
                d["disk_read"]  = max(round((disk.read_bytes  - self._prev_disk.read_bytes)  / (1024**2), 1), 0)
                d["disk_write"] = max(round((disk.write_bytes - self._prev_disk.write_bytes) / (1024**2), 1), 0)
            else:
                d["disk_read"] = d["disk_write"] = 0.0
            if disk: self._prev_disk = disk

            try:
                for addr in psutil.net_if_addrs().get(IFACE, []):
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        d["local_ip"] = addr.address; break
            except Exception:
                d["local_ip"] = "?.?.?.?"

            try:    d["processes"] = len(psutil.pids())
            except: d["processes"] = 0

            try:
                conns = psutil.net_connections(kind="tcp")
                d["tcp_conns"] = len([c for c in conns if c.status=="ESTABLISHED"])
            except Exception:
                d["tcp_conns"] = -1

            d["ping"]      = self._ping_ms
            d["public_ip"] = self._public_ip
            d["ts"]        = datetime.now()

            self.updated.emit(d)
            time.sleep(1)

    def stop(self):
        self._running = False


class NixieLabel(QLabel):
    def __init__(self, text="--", size=36, parent=None):
        super().__init__(text, parent)
        font = QFont("Courier New", size, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("color: #ff6600; background: transparent;")


class NixieSmallLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        font = QFont("Courier New", 9, QFont.Weight.Normal)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("color: #7a3300; background: transparent;")


class Sparkline(QWidget):
    def __init__(self, maxlen=60, color=AMBER, parent=None):
        super().__init__(parent)
        self._data  = deque([0.0]*maxlen, maxlen=maxlen)
        self._color = color
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def push(self, value: float):
        self._data.append(value)
        self.update()

    def paintEvent(self, _):
        if not self._data: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mx = max(self._data) or 1.0
        pts = []
        for i, v in enumerate(self._data):
            x = i * w / (len(self._data)-1)
            y = h - (v / mx) * h * 0.85
            pts.append(QPointF(x, y))
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]: path.lineTo(pt)
        path.lineTo(QPointF(w, h))
        path.lineTo(QPointF(0, h))
        path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(255, 102, 0, 70))
        grad.setColorAt(1, QColor(255, 102, 0, 5))
        p.fillPath(path, QBrush(grad))
        pen = QPen(self._color, 1.5)
        p.setPen(pen)
        for i in range(len(pts)-1):
            p.drawLine(pts[i], pts[i+1])


class NetGraph(QWidget):
    def __init__(self, maxlen=60, parent=None):
        super().__init__(parent)
        self._down  = deque([0.0]*maxlen, maxlen=maxlen)
        self._up    = deque([0.0]*maxlen, maxlen=maxlen)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def push(self, down, up):
        self._down.append(down)
        self._up.append(up)
        self.update()

    def _draw_series(self, p, data, color, w, h, mx):
        pts = []
        for i, v in enumerate(data):
            x = i * w / (len(data)-1)
            y = h - (v/mx)*h*0.88
            pts.append(QPointF(x, y))
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]: path.lineTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(QPointF(w, h))
        fill.lineTo(QPointF(0, h))
        fill.closeSubpath()
        c_fill = QColor(color)
        c_fill.setAlpha(35)
        p.fillPath(fill, QBrush(c_fill))
        pen = QPen(QColor(color), 1.5)
        p.setPen(pen)
        for i in range(len(pts)-1):
            p.drawLine(pts[i], pts[i+1])

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QBrush(QColor(10,4,0)))
        w, h = self.width(), self.height()
        mx = max(max(self._down, default=0), max(self._up, default=0), 0.1)
        self._draw_series(p, self._down, "#ff6600", w, h, mx)
        self._draw_series(p, self._up,   "#cc3300", w, h, mx)
        p.setPen(QPen(QColor(50, 20, 0), 1, Qt.PenStyle.DotLine))
        for i in range(1, 4):
            y = int(h * i / 4)
            p.drawLine(0, y, w, y)
        p.setPen(QColor("#ff6600"))
        f = QFont("Courier New", 8)
        p.setFont(f)
        p.drawText(QRectF(0, 4, w-4, 16), Qt.AlignmentFlag.AlignRight,
                   f"down {self._down[-1]:.2f} Mbps")
        p.setPen(QColor("#cc3300"))
        p.drawText(QRectF(0, 18, w-4, 16), Qt.AlignmentFlag.AlignRight,
                   f"up   {self._up[-1]:.2f} Mbps")


class TubeCard(QWidget):
    def __init__(self, label_text, value_text="--", unit_text="", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 28, 10, 8)
        lay.setSpacing(2)
        self._label = NixieSmallLabel(label_text.upper())
        self._value = NixieLabel(value_text, 30)
        self._unit  = NixieSmallLabel(unit_text.upper())
        lay.addWidget(self._label)
        lay.addWidget(self._value)
        lay.addWidget(self._unit)

    def set_value(self, v, unit=None):
        self._value.setText(str(v))
        if unit is not None:
            self._unit.setText(str(unit).upper())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QBrush(TUBE_BG))
        p.setPen(QPen(BORDER, 1))
        p.drawRoundedRect(r, 10, 10)
        glow = QLinearGradient(0, 0, 0, self.height())
        glow.setColorAt(0, QColor(255, 80, 0, 8))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 10, 10)
        super().paintEvent(event)


class SparkCard(TubeCard):
    def __init__(self, label_text, unit_text="", parent=None):
        super().__init__(label_text, "--", unit_text, parent)
        self._spark = Sparkline()
        self.layout().addWidget(self._spark)

    def push(self, value, unit=None):
        self.set_value(value, unit)
        try: self._spark.push(float(value))
        except: pass


class NixieWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NIXIE  |  System Dashboard")
        self.setMinimumSize(1050, 620)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, BG)
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        title = QLabel("N  E  T  W  O  R  K     M  O  N  I  T  O  R")
        tf = QFont("Courier New", 11, QFont.Weight.Normal)
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        title.setFont(tf)
        title.setStyleSheet("color: #7a3300; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root.addWidget(title)

        self.net_graph = NetGraph()
        self.net_graph.setFixedHeight(120)
        root.addWidget(self.net_graph)

        grid = QGridLayout()
        grid.setSpacing(8)
        root.addLayout(grid)

        self.c_down  = TubeCard("Download", "--", "Mbps")
        self.c_up    = TubeCard("Upload",   "--", "Mbps")
        self.c_ping  = SparkCard("Ping",        "ms · google.com")
        self.c_cpu   = SparkCard("CPU",          "%")
        self.c_ram   = TubeCard("RAM",      "--", "Used / Total")
        self.c_disk  = TubeCard("Disk Space","--", "%")
        self.c_dread = TubeCard("Disk Read", "--", "MB/s")
        self.c_dwrit = TubeCard("Disk Write","--", "MB/s")
        self.c_lip   = TubeCard("Local IP",  "--", "IPv4")
        self.c_pip   = TubeCard("Public IP", "--", "External")
        self.c_freq  = TubeCard("CPU Freq",  "--", "GHz")
        self.c_procs = TubeCard("Processes", "--", "Running")
        self.c_swap  = TubeCard("Swap",      "--", "Used / Total")
        self.c_tcp   = TubeCard("TCP Conns", "--", "Established")
        self.c_dt    = TubeCard("Date",      "--", "")
        self.c_tm    = TubeCard("Time",      "--", "HH : MM : SS")

        rows = [
            [self.c_down, self.c_up,   self.c_ping, self.c_cpu],
            [self.c_ram,  self.c_disk, self.c_dread,self.c_dwrit],
            [self.c_lip,  self.c_pip,  self.c_freq, self.c_procs],
            [self.c_swap, self.c_tcp,  self.c_dt,   self.c_tm],
        ]
        for r, row in enumerate(rows):
            for c, card in enumerate(row):
                grid.addWidget(card, r, c)
        for c in range(4): grid.setColumnStretch(c, 1)

        self._thread = QThread()
        self._worker = MetricsWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.updated.connect(self._on_data)
        self._thread.start()

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start()

    def _tick_clock(self):
        now = datetime.now()
        self.c_dt.set_value(now.strftime("%Y · %m · %d"), "Year · Mon · Day")
        self.c_tm.set_value(now.strftime("%H : %M : %S"), "HR  :  MIN  :  SEC")

    def _on_data(self, d: dict):
        self.net_graph.push(d.get("down", 0), d.get("up", 0))
        self.c_down.set_value(f"{d.get('down',0):.2f}", "Mbps")
        self.c_up.set_value(f"{d.get('up',0):.2f}",    "Mbps")
        ping = d.get("ping", -1)
        self.c_ping.push("--" if ping < 0 else int(ping), "ms · google.com")
        self.c_cpu.push(f"{d.get('cpu',0):.1f}", "%")
        self.c_ram.set_value(f"{d.get('ram_used',0)} / {d.get('ram_total',0)} GB", "Used / Total")
        self.c_disk.set_value(f"{d.get('disk_space',0):.0f}", "%")
        self.c_dread.set_value(f"{d.get('disk_read',0):.1f}", "MB/s")
        self.c_dwrit.set_value(f"{d.get('disk_write',0):.1f}", "MB/s")
        self.c_lip.set_value(d.get("local_ip","?.?.?.?"), "IPv4")
        self.c_pip.set_value(d.get("public_ip","..."), "External")
        self.c_freq.set_value(f"{d.get('cpu_freq',0):.2f}", "GHz")
        self.c_procs.set_value(str(d.get("processes",0)), "Running")
        self.c_swap.set_value(f"{d.get('swap_used',0)} / {d.get('swap_total',0)} GB", "Used / Total")
        tcp = d.get("tcp_conns", -1)
        self.c_tcp.set_value("--" if tcp < 0 else tcp, "Established")

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setOpacity(0.04)
        pen = QPen(QColor(0, 0, 0), 1)
        p.setPen(pen)
        for y in range(0, self.height(), 4):
            p.drawLine(0, y, self.width(), y)

    def closeEvent(self, event):
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(2000)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget  { background: #050505; color: #ff6600; }
        QToolTip { background: #0d0d0d; color: #ff6600; border: 1px solid #3a1500; }
    """)
    win = NixieWindow()
    win.show()
    sys.exit(app.exec())