#!/usr/bin/env python3
"""Control del Yamaha RX-V4A desde el PC, con la cara del mando original.

Habla con la API de red del receptor (YamahaExtendedControl), la misma que usa
la app MusicCast. Uso:

    yamaha_control.py [--tray] [--host IP]

--tray arranca oculto en la bandeja. --host fija la IP del receptor y queda
guardada en ~/.config/yamaha-control/yamaha-control.conf; también vale la
variable de entorno YAMAHA_HOST.
"""
import os
import json
import math
import sys
from urllib.parse import urlencode

from PyQt6.QtCore import QByteArray, QPointF, QRectF, QSettings, QSize, QTimer, QUrl, Qt
from PyQt6.QtGui import (QAction, QColor, QFont, QIcon, QPainter, QPainterPath,
                         QPen, QPixmap, QPolygonF)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QMenu, QPushButton, QSlider,
    QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget,
)

DEFAULT_HOST = "192.168.18.46"


def load_host():
    prefs = QSettings("yamaha-control", "yamaha-control")
    if "--host" in sys.argv[:-1]:
        prefs.setValue("host", sys.argv[sys.argv.index("--host") + 1])
    return os.environ.get("YAMAHA_HOST") or prefs.value("host", DEFAULT_HOST)


HOST = load_host()
BASE = f"http://{HOST}/YamahaExtendedControl/v1/"
POLL_MS = 2000

PHYSICAL = ["hdmi1", "hdmi2", "hdmi3", "hdmi4", "tv", "audio1", "audio2",
            "audio3", "audio4", "audio5", "tuner", "usb"]
NET = ["bluetooth", "airplay", "spotify", "net_radio", "server", "tidal",
       "deezer", "qobuz", "amazon_music", "napster", "mc_link"]
NETUSB = set(NET) | {"usb"}
NET_CYCLE = ["server", "net_radio", "spotify", "airplay", "tidal", "deezer",
             "qobuz", "amazon_music", "napster", "mc_link"]
DECODERS = {"toggle": "Auto", "dolby_pl2x_movie": "Dolby PLIIx Movie",
            "dolby_pl2x_music": "Dolby PLIIx Music",
            "dolby_pl2x_game": "Dolby PLIIx Game",
            "dts_neo6_cinema": "DTS Neo:6 Cinema",
            "dts_neo6_music": "DTS Neo:6 Music"}
DELAYS = {"audio_sync": "Prioridad audio", "balanced": "Equilibrado",
          "lip_sync": "Sincronía labial"}
SLEEPS = [0, 30, 60, 90, 120]
SLEEP_CYCLE = {0: 120, 120: 90, 90: 60, 60: 30, 30: 0}  # como el botón SLEEP

# Emblema de los tres diapasones
EMBLEM = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">{bg}
<g fill="none" stroke="{c}" stroke-width="3.8">
<circle cx="50" cy="50" r="45"/>
<path d="M43 10 V25 A7 7 0 0 0 57 25 V10 M50 32 V50"/>
<path d="M43 10 V25 A7 7 0 0 0 57 25 V10 M50 32 V50" transform="rotate(120 50 50)"/>
<path d="M43 10 V25 A7 7 0 0 0 57 25 V10 M50 32 V50" transform="rotate(240 50 50)"/>
</g></svg>"""

STYLE = """
QWidget#root { background: #151618; }
QWidget#body {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f2023,
                                stop:0.5 #2e2f33, stop:1 #1f2023);
    border: 2px solid #4a4c50; border-radius: 36px;
}
QFrame#sep { background: #46484c; max-height: 1px; min-height: 1px; }
QLabel { color: #f2f2f2; font-weight: bold; font-size: 8pt; background: transparent; }
QLabel#brand { font-size: 20pt; font-weight: 900; letter-spacing: 1px; }
QPushButton { color: white; font-weight: bold; font-size: 8pt; outline: none; }

QPushButton[kind="grey"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #b9bcc0, stop:1 #7c7f84);
    color: #151515; border: 1px solid #111; border-radius: 12px; min-height: 24px;
}
QPushButton[kind="grey"]:pressed { background: #5c5f63; }
QPushButton[kind="grey"][on="true"] { border: 2px solid #5cc8ff; }

QPushButton[kind="black"] {
    background: #18191b; border: 2px solid #9a9da2; border-radius: 13px;
    min-height: 22px; padding: 0 10px; font-size: 7pt;
}
QPushButton[kind="black"]:pressed, QPushButton[kind="round"]:pressed { background: #4a4c50; }
QPushButton[kind="black"][on="true"] { border-color: #ff6b5a; color: #ff9d90; }

QPushButton[kind="round"] {
    background: #18191b; border: 2px solid #9a9da2; border-radius: 23px;
    min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px; font-size: 7pt;
}
QPushButton[kind="scene"] {
    background: qradialgradient(cx:0.5, cy:0.35, radius:0.7, stop:0 #ffffff, stop:1 #cfcfcf);
    color: #111; border: 2px solid #777; border-radius: 23px; font-size: 13pt;
    min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px;
}
QPushButton[kind="scene"]:pressed { background: #a9a9a9; }

QPushButton[kind="power"] {
    background: #e2683f; border: 1px solid #111; border-radius: 14px;
    min-width: 56px; min-height: 28px; font-size: 13pt;
}
QPushButton[kind="power"][on="false"] { background: #7b3a26; color: #d9b3a6; }
QPushButton[kind="power"]:pressed { background: #b0482a; }

QPushButton[kind="rockTop"], QPushButton[kind="rockBottom"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b9bcc0, stop:1 #8a8d92);
    color: #151515; border: 1px solid #111; min-width: 52px; max-width: 52px;
    min-height: 64px; font-size: 18pt;
}
QPushButton[kind="rockTop"] { border-top-left-radius: 26px; border-top-right-radius: 26px;
    border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; }
QPushButton[kind="rockBottom"] { border-bottom-left-radius: 26px; border-bottom-right-radius: 26px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; }
QPushButton[kind="rockTop"]:pressed, QPushButton[kind="rockBottom"]:pressed { background: #5c5f63; }

QPushButton[kind="seg"] {
    background: #3a3c40; color: #aaa; border: 1px solid #111; min-width: 24px;
    min-height: 16px; font-size: 7pt; border-radius: 3px;
}
QPushButton[kind="seg"]:checked { background: #e8e8e8; color: #111; }

QPushButton[kind="color"] { border: 1px solid #111; border-radius: 11px; min-height: 22px; font-size: 7pt; }
QPushButton[kind="color"]:pressed { background: #444; }

QFrame#lcd { background: #050708; border: 2px solid #3c3e42; border-radius: 10px; }
QFrame#lcd QLabel, QFrame#lcd QPushButton {
    color: #aee6ff; font-family: "DejaVu Sans Mono", monospace; background: transparent;
    border: none; text-align: left; padding: 0;
}
QFrame#lcd QPushButton::menu-indicator { image: none; width: 0; }
QPushButton#lcdInput { font-size: 17pt; }
QPushButton#lcdProgram { font-size: 10pt; }
QLabel#lcdSmall { font-size: 9pt; font-weight: normal; }
"""


def db(volume):
    return -80.5 + volume / 2


def svg_icon(color="white", bg=True, size=64):
    back = '<circle cx="50" cy="50" r="50" fill="#4b1f7a"/>' if bg else ""
    r = QSvgRenderer(QByteArray(EMBLEM.format(c=color, bg=back).encode()))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    return QIcon(pm)


def button(text, kind, cb=None, repeat=False, tip=None):
    b = QPushButton(text)
    b.setProperty("kind", kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if repeat:
        b.setAutoRepeat(True)
        b.setAutoRepeatDelay(350)
        b.setAutoRepeatInterval(110)
    if cb:
        b.clicked.connect(lambda: cb())
    if tip:
        b.setToolTip(tip)
    return b


def set_on(widget, on):
    widget.setProperty("on", "true" if on else "false")
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def caption(text, size=8):
    lab = QLabel(text)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if size != 8:
        lab.setStyleSheet(f"font-size: {size}pt;")
    return lab


def titled(text, widget):
    """Etiqueta encima del botón, como en el mando."""
    box = QVBoxLayout()
    box.setSpacing(2)
    box.addWidget(caption(text, 7))
    box.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
    return box


def section_title(text):
    row = QHBoxLayout()
    for part in ("l", text, "r"):
        if part in ("l", "r"):
            line = QFrame()
            line.setObjectName("sep")
            row.addWidget(line, 1)
        else:
            row.addWidget(caption(part, 9))
    return row


class Api:
    """Peticiones asíncronas a la API; cb recibe el JSON (o None si falla)."""

    def __init__(self):
        self.net = QNetworkAccessManager()

    def get(self, path, params=None, cb=None):
        url = BASE + path + ("?" + urlencode(params) if params else "")
        req = QNetworkRequest(QUrl(url))
        req.setTransferTimeout(4000)
        reply = self.net.get(req)

        def done():
            data = None
            if reply.error() == reply.NetworkError.NoError:
                try:
                    data = json.loads(bytes(reply.readAll()))
                except ValueError:
                    pass
            reply.deleteLater()
            if cb:
                cb(data)
        reply.finished.connect(done)


class DPad(QWidget):
    """Cruceta en anillo con ENTER en el centro."""
    SEGMENTS = ["right", "up", "left", "down"]

    def __init__(self, on_press, size=176):
        super().__init__()
        self.on_press = on_press
        self.down = None
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def radii(self):
        c = self.width() / 2
        return c, c - 3, c * 0.47

    def hit(self, pos):
        c, outer, inner = self.radii()
        dx, dy = pos.x() - c, pos.y() - c
        d = math.hypot(dx, dy)
        if d <= inner - 6:
            return "select"
        if d > outer or d < inner:
            return None
        ang = math.degrees(math.atan2(-dy, dx)) % 360
        return self.SEGMENTS[int(((ang + 45) % 360) // 90)]

    def mousePressEvent(self, e):
        self.down = self.hit(e.position())
        self.update()

    def mouseReleaseEvent(self, e):
        if self.down and self.hit(e.position()) == self.down:
            self.on_press(self.down)
        self.down = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, R, r = self.radii()
        outer = QRectF(c - R, c - R, 2 * R, 2 * R)
        inner = QRectF(c - r, c - r, 2 * r, 2 * r)
        p.setPen(QPen(QColor("#a8abb0"), 2))
        for i, name in enumerate(self.SEGMENTS):
            start = i * 90 - 45
            path = QPainterPath()
            path.arcMoveTo(outer, start + 2)
            path.arcTo(outer, start + 2, 86)
            path.arcTo(inner, start + 88, -86)
            path.closeSubpath()
            p.setBrush(QColor("#5a5d62" if self.down == name else "#38393d"))
            p.drawPath(path)
            mid = math.radians(start + 45)
            u = QPointF(math.cos(mid), -math.sin(mid))
            v = QPointF(math.sin(mid), math.cos(mid))
            ctr = QPointF(c, c) + u * ((R + r) / 2)
            p.save()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#f0f0f0"))
            p.drawPolygon(QPolygonF([ctr + u * 6, ctr - u * 4 + v * 6, ctr - u * 4 - v * 6]))
            p.restore()
        p.setBrush(QColor("#4a4c50" if self.down == "select" else "#1b1c1e"))
        p.drawEllipse(QPointF(c, c), r - 7, r - 7)
        f = QFont()
        f.setBold(True)
        f.setPointSize(8)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(c - r, c - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, "ENTER")


class Classic(QWidget):
    """Vista completa por pestañas (la disposición original)."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.dragging = False
        self.setWindowTitle("Yamaha RX-V4A")
        self.setWindowIcon(svg_icon())
        self.resize(560, 640)
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.power = QPushButton("⏻")
        self.power.setCheckable(True)
        self.power.setFixedWidth(48)
        self.power.setToolTip("Encender / standby")
        self.power.clicked.connect(lambda: win.cmd(
            "main/setPower", power="on" if self.power.isChecked() else "standby"))
        top.addWidget(self.power)
        info = QVBoxLayout()
        self.title = QLabel("Conectando…")
        self.title.setStyleSheet("font-size: 15pt; font-weight: bold;")
        self.signal = QLabel("")
        info.addWidget(self.title)
        info.addWidget(self.signal)
        top.addLayout(info, 1)
        remote = QPushButton("🎛 Mando")
        remote.setToolTip("Cambiar a la vista de mando")
        remote.clicked.connect(lambda: win.switch_view("remote"))
        top.addWidget(remote, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)

        vol = QHBoxLayout()
        self.mute = QPushButton("🔇")
        self.mute.setCheckable(True)
        self.mute.setFixedWidth(48)
        self.mute.setToolTip("Silencio")
        self.mute.clicked.connect(lambda: win.cmd(
            "main/setMute", enable=str(self.mute.isChecked()).lower()))
        vol.addWidget(self.mute)
        down = QPushButton("−")
        down.setFixedWidth(36)
        down.setAutoRepeat(True)
        down.clicked.connect(lambda: self.volume.setValue(self.volume.value() - 1))
        vol.addWidget(down)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 161)
        self.volume.sliderPressed.connect(lambda: setattr(self, "dragging", True))
        self.volume.sliderReleased.connect(self.volume_released)
        self.volume.valueChanged.connect(self.volume_moved)
        vol.addWidget(self.volume, 1)
        up = QPushButton("+")
        up.setFixedWidth(36)
        up.setAutoRepeat(True)
        up.clicked.connect(lambda: self.volume.setValue(self.volume.value() + 1))
        vol.addWidget(up)
        self.vol_label = QLabel("")
        self.vol_label.setMinimumWidth(80)
        self.vol_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vol.addWidget(self.vol_label)
        root.addLayout(vol)
        self.vol_timer = QTimer(singleShot=True, interval=120)
        self.vol_timer.timeout.connect(
            lambda: win.cmd("main/setVolume", volume=self.volume.value()))

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self.build_inputs(), "Entradas")
        self.tabs.addTab(self.build_sound(), "Sonido")
        self.tabs.addTab(self.build_remote(), "Mando")
        self.tabs.addTab(self.build_playback(), "Reproducción")

    # ---- pestañas ----
    def build_inputs(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.input_buttons = {}
        for title, ids in (("Físicas", PHYSICAL), ("Red y streaming", NET)):
            box = QGroupBox(title)
            grid = QGridLayout(box)
            for i, inp in enumerate(ids):
                b = QPushButton(inp.upper())
                b.setCheckable(True)
                b.clicked.connect(lambda _, x=inp: self.win.cmd("main/setInput", input=x))
                grid.addWidget(b, i // 3, i % 3)
                self.input_buttons[inp] = b
            lay.addWidget(box)
        scenes = QGroupBox("Escenas")
        sl = QHBoxLayout(scenes)
        for n in range(1, 5):
            b = QPushButton(f"Escena {n}")
            b.clicked.connect(lambda _, x=n: self.win.cmd("main/recallScene", num=x))
            sl.addWidget(b)
        lay.addWidget(scenes)
        lay.addStretch()
        return w

    def build_sound(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        cmd = self.win.cmd

        prog = QGroupBox("Programa de sonido")
        pl = QGridLayout(prog)
        self.program = QComboBox()
        self.program.activated.connect(lambda: cmd(
            "main/setSoundProgram", program=self.program.currentData()))
        pl.addWidget(QLabel("Programa"), 0, 0)
        pl.addWidget(self.program, 0, 1)
        self.decoder = QComboBox()
        for k, v in DECODERS.items():
            self.decoder.addItem(v, k)
        self.decoder.activated.connect(lambda: cmd(
            "main/setSurroundDecoderType", type=self.decoder.currentData()))
        pl.addWidget(QLabel("Decodificador"), 1, 0)
        pl.addWidget(self.decoder, 1, 1)
        lay.addWidget(prog)

        toggles = QGroupBox("Modos")
        tl = QGridLayout(toggles)
        self.checks = {}
        for i, (key, label, path) in enumerate((
                ("pure_direct", "Pure Direct", "main/setPureDirect"),
                ("enhancer", "Compressed Music Enhancer", "main/setEnhancer"),
                ("extra_bass", "Extra Bass", "main/setExtraBass"),
                ("adaptive_drc", "Adaptive DRC (modo noche)", "main/setAdaptiveDrc"))):
            c = QCheckBox(label)
            c.clicked.connect(lambda on, p=path: cmd(p, enable=str(on).lower()))
            tl.addWidget(c, i // 2, i % 2)
            self.checks[key] = c
        lay.addWidget(toggles)

        levels = QGroupBox("Niveles")
        ll = QGridLayout(levels)
        self.sliders = {}
        for row, (key, label, lo, hi) in enumerate((
                ("bass", "Graves", -12, 12), ("treble", "Agudos", -12, 12),
                ("subwoofer", "Subwoofer", -12, 12), ("dialogue", "Diálogo", 0, 3))):
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setPageStep(1)
            val = QLabel("0")
            val.setMinimumWidth(50)
            s.valueChanged.connect(lambda v, l=val, k=key: l.setText(self.level_text(k, v)))
            s.sliderReleased.connect(lambda k=key: self.send_level(k))
            s.actionTriggered.connect(lambda _, k=key, sl=s: None if sl.isSliderDown()
                                      else QTimer.singleShot(0, lambda: self.send_level(k)))
            ll.addWidget(QLabel(label), row, 0)
            ll.addWidget(s, row, 1)
            ll.addWidget(val, row, 2)
            self.sliders[key] = (s, val)
        lay.addWidget(levels)

        other = QGroupBox("Otros")
        ol = QGridLayout(other)
        self.delay = QComboBox()
        for k, v in DELAYS.items():
            self.delay.addItem(v, k)
        self.delay.activated.connect(lambda: cmd(
            "main/setLinkAudioDelay", delay=self.delay.currentData()))
        ol.addWidget(QLabel("Retardo audio (HDMI)"), 0, 0)
        ol.addWidget(self.delay, 0, 1)
        self.sleep = QComboBox()
        for m in SLEEPS:
            self.sleep.addItem("Desactivado" if m == 0 else f"{m} min", m)
        self.sleep.activated.connect(lambda: cmd(
            "main/setSleep", sleep=self.sleep.currentData()))
        ol.addWidget(QLabel("Apagado automático"), 1, 0)
        ol.addWidget(self.sleep, 1, 1)
        lay.addWidget(other)
        lay.addStretch()
        return w

    def build_remote(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Navega por el menú en pantalla del receptor (se ve en la TV)."))
        pad = QGridLayout()
        for label, cur, r, c in (("▲", "up", 0, 1), ("◀", "left", 1, 0),
                                 ("ENTER", "select", 1, 1), ("▶", "right", 1, 2),
                                 ("▼", "down", 2, 1)):
            b = QPushButton(label)
            b.setMinimumSize(80, 56)
            b.clicked.connect(lambda _, x=cur: self.win.cmd("main/controlCursor", cursor=x))
            pad.addWidget(b, r, c)
        back = QPushButton("↩ RETURN")
        back.setMinimumHeight(40)
        back.clicked.connect(lambda: self.win.cmd("main/controlCursor", cursor="return"))
        pad.addWidget(back, 3, 0, 1, 3)
        lay.addLayout(pad)
        menus = QGridLayout()
        for i, (label, m) in enumerate((
                ("SETUP", "on_screen"), ("OPTION", "option"), ("DISPLAY", "display"),
                ("HOME", "home"), ("MENU", "menu"), ("TOP MENU", "top_menu"),
                ("MODE", "mode"), ("HELP", "help"))):
            b = QPushButton(label)
            b.clicked.connect(lambda _, x=m: self.win.menu(x))
            menus.addWidget(b, i // 4, i % 4)
        colors = QHBoxLayout()
        for m, col in (("red", "#c62828"), ("green", "#2e7d32"),
                       ("yellow", "#f9a825"), ("blue", "#1565c0")):
            b = QPushButton()
            b.setStyleSheet(f"background: {col}; min-height: 20px;")
            b.clicked.connect(lambda _, x=m: self.win.menu(x))
            colors.addWidget(b)
        lay.addLayout(menus)
        lay.addLayout(colors)
        lay.addStretch()
        return w

    def build_playback(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.np_title = QLabel("—")
        self.np_title.setStyleSheet("font-size: 13pt; font-weight: bold;")
        self.np_title.setWordWrap(True)
        self.np_sub = QLabel("")
        self.np_sub.setWordWrap(True)
        lay.addWidget(self.np_title)
        lay.addWidget(self.np_sub)
        row = QHBoxLayout()
        for label, act in (("⏮", "previous"), ("⏯", "play_pause"),
                           ("⏹", "stop"), ("⏭", "next")):
            b = QPushButton(label)
            b.setMinimumHeight(48)
            b.clicked.connect(lambda _, x=act: self.win.playback(x))
            row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(QLabel("Para Spotify, AirPlay, Bluetooth, radio por internet, USB…"))
        lay.addStretch()
        return w

    # ---- acciones ----
    def volume_moved(self, v):
        self.vol_label.setText(f"{db(v):+.1f} dB")
        if not self.dragging:
            self.vol_timer.start()

    def volume_released(self):
        self.dragging = False
        self.vol_timer.start()

    def level_text(self, key, v):
        return str(v) if key == "dialogue" else f"{v:+d}"

    def send_level(self, key):
        v = self.sliders[key][0].value()
        if key in ("bass", "treble"):
            self.win.cmd("main/setToneControl", mode="manual",
                         bass=self.sliders["bass"][0].value(),
                         treble=self.sliders["treble"][0].value())
        elif key == "subwoofer":
            self.win.cmd("main/setSubwooferVolume", volume=v)
        else:
            self.win.cmd("main/setDialogueLevel", value=v)

    # ---- estado ----
    def apply(self):
        win, d = self.win, self.win.status
        if self.program.count() != len(win.programs):
            self.program.clear()
            for k, v in win.programs.items():
                self.program.addItem(v, k)
        for inp, b in self.input_buttons.items():
            b.setText(win.names.get(inp, inp.upper()))
            b.setChecked(inp == d.get("input"))
        if not d:
            self.title.setText("Sin conexión con el receptor")
            self.signal.setText(HOST)
            return
        on = d.get("power") == "on"
        self.power.setChecked(on)
        inp = d.get("input", "")
        self.title.setText(win.names.get(inp, d.get("input_text", inp)) if on else "Apagado")
        self.signal.setText(f"Señal: {win.signal}" if on and win.signal else
                            ("" if on else "En standby"))
        self.mute.setChecked(d.get("mute", False))
        if not self.dragging and not self.vol_timer.isActive():
            self.volume.blockSignals(True)
            self.volume.setValue(d.get("volume", 0))
            self.volume.blockSignals(False)
            self.vol_label.setText(f"{db(self.volume.value()):+.1f} dB")
        for combo, key in ((self.program, "sound_program"), (self.decoder, "surr_decoder_type"),
                           (self.delay, "link_audio_delay"), (self.sleep, "sleep")):
            i = combo.findData(d.get(key))
            if i >= 0 and not combo.view().isVisible():
                combo.setCurrentIndex(i)
        for k, c in self.checks.items():
            c.setChecked(bool(d.get(k)))
        tone = d.get("tone_control", {})
        for key, val in (("bass", tone.get("bass")), ("treble", tone.get("treble")),
                         ("subwoofer", d.get("subwoofer_volume")),
                         ("dialogue", d.get("dialogue_level"))):
            s, lbl = self.sliders[key]
            if val is not None and not s.isSliderDown():
                s.blockSignals(True)
                s.setValue(val)
                s.blockSignals(False)
                lbl.setText(self.level_text(key, val))
        play = win.play if inp in NETUSB else {}
        self.np_title.setText(play.get("track") or win.names.get(inp, "—"))
        self.np_sub.setText(" · ".join(x for x in (play.get("artist"), play.get("album")) if x))

    def closeEvent(self, e):
        if QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()
            self.hide()


class Remote(QWidget):
    def __init__(self):
        super().__init__()
        self.api = Api()
        self.status = {}     # main
        self.zstatus = {}    # zone2 (ZONE B)
        self.signal = ""
        self.play = {}
        self.tuner = {}
        self.names = {}
        self.programs = {}
        self.zone = "main"
        self.message = ""
        self.prefs = QSettings("yamaha-control", "yamaha-control")
        self.setObjectName("root")
        self.setWindowTitle("Yamaha RX-V4A")
        self.setWindowIcon(svg_icon())
        self.setStyleSheet(STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        body = QWidget()
        body.setObjectName("body")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(12)

        lay.addWidget(self.build_display())
        lay.addLayout(self.build_top())
        lay.addLayout(section_title("SCENE"))
        lay.addLayout(self.build_scenes())
        lay.addLayout(self.build_program())
        lay.addLayout(self.build_input_volume())
        lay.addWidget(self.separator())
        lay.addLayout(self.build_navigation())
        lay.addLayout(self.build_menus())
        lay.addLayout(self.build_transport())
        lay.addLayout(self.build_preset())
        lay.addStretch()
        lay.addLayout(self.build_brand())

        self.msg_timer = QTimer(singleShot=True, interval=2500)
        self.msg_timer.timeout.connect(lambda: (setattr(self, "message", ""), self.render()))
        self.classic = Classic(self)
        self.api.get("system/getNameText", cb=self.got_names)
        self.timer = QTimer(interval=POLL_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    # ---- construcción ----
    def separator(self):
        s = QFrame()
        s.setObjectName("sep")
        return s

    def build_display(self):
        lcd = QFrame()
        lcd.setObjectName("lcd")
        v = QVBoxLayout(lcd)
        v.setContentsMargins(14, 8, 14, 8)
        v.setSpacing(1)
        self.lcd_input = QPushButton("CONECTANDO")
        self.lcd_input.setObjectName("lcdInput")
        self.lcd_input.setToolTip("Elegir entrada")
        self.input_menu = QMenu(self)
        self.lcd_input.setMenu(self.input_menu)
        self.lcd_program = QPushButton("")
        self.lcd_program.setObjectName("lcdProgram")
        self.lcd_program.setToolTip("Elegir programa de sonido")
        self.program_menu = QMenu(self)
        self.lcd_program.setMenu(self.program_menu)
        self.lcd_line = QLabel("")
        self.lcd_line.setObjectName("lcdSmall")
        self.lcd_extra = QLabel("")
        self.lcd_extra.setObjectName("lcdSmall")
        for w in (self.lcd_input, self.lcd_program, self.lcd_line, self.lcd_extra):
            v.addWidget(w)
        return lcd

    def build_top(self):
        row = QHBoxLayout()
        zone = QVBoxLayout()
        zone.setSpacing(2)
        zone.addWidget(caption("ZONE A  ·  ZONE B", 6))
        seg = QHBoxLayout()
        seg.setSpacing(0)
        group = QButtonGroup(self)
        for z, label in (("main", "A"), ("zone2", "B")):
            b = button(label, "seg", tip="Zona a la que van encendido, volumen y mute")
            b.setCheckable(True)
            b.setChecked(z == "main")
            b.clicked.connect(lambda _, x=z: self.set_zone(x))
            group.addButton(b)
            seg.addWidget(b)
        zone.addLayout(seg)
        row.addLayout(zone)
        row.addStretch()
        self.sleep_btn = button("SLEEP", "black", self.cycle_sleep, tip="Apagado automático")
        row.addWidget(self.sleep_btn)
        row.addStretch()
        self.power_btn = button("⏻", "power", self.toggle_power, tip="Encender / standby")
        row.addWidget(self.power_btn)
        return row

    def build_scenes(self):
        row = QHBoxLayout()
        for n in range(1, 5):
            row.addWidget(button(str(n), "scene",
                                 lambda x=n: self.cmd("main/recallScene", num=x)))
        return row

    def build_program(self):
        box = QVBoxLayout()
        box.setSpacing(6)
        row = QHBoxLayout()
        self.straight_btn = button("", "grey", lambda: self.cmd(
            "main/setSoundProgram", program="straight"))
        self.pure_btn = button("", "grey", lambda: self.cmd(
            "main/setPureDirect", enable=str(not self.status.get("pure_direct")).lower()))
        self.enh_btn = button("", "grey", lambda: self.cmd(
            "main/setEnhancer", enable=str(not self.status.get("enhancer")).lower()))
        self.dec_btn = button("", "grey", lambda: self.cmd(
            "main/setSoundProgram", program="surr_decoder"))
        for label, b in (("STRAIGHT", self.straight_btn), ("PURE DIRECT", self.pure_btn),
                         ("ENHANCER", self.enh_btn), ("SUR.DECODE", self.dec_btn)):
            b.setMinimumWidth(56)
            row.addLayout(titled(label, b))
        box.addLayout(row)
        box.addWidget(caption("PROGRAM", 9))
        prog = QHBoxLayout()
        for arrow, d in (("◀", -1), ("▶", 1)):
            b = button(arrow, "grey", lambda x=d: self.step_program(x), repeat=True)
            b.setMinimumHeight(30)
            prog.addWidget(b)
        box.addLayout(prog)
        return box

    def rocker(self, top, bottom, label, top_cb, bottom_cb):
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(button(top, "rockTop", top_cb, repeat=True), 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(caption(label, 9))
        col.addWidget(button(bottom, "rockBottom", bottom_cb, repeat=True), 0,
                      Qt.AlignmentFlag.AlignHCenter)
        return col

    def build_input_volume(self):
        row = QHBoxLayout()
        row.addLayout(self.rocker("▲", "▼", "INPUT",
                                  lambda: self.step_input(-1), lambda: self.step_input(1)))
        quick = QVBoxLayout()
        quick.setSpacing(8)
        for label, cb in (("TUNER", lambda: self.cmd("main/setInput", input="tuner")),
                          ("USB", lambda: self.cmd("main/setInput", input="usb")),
                          ("NET", self.next_net),
                          ("BLUETOOTH", lambda: self.cmd("main/setInput", input="bluetooth"))):
            quick.addWidget(button(label, "black", cb))
        row.addLayout(quick)
        row.addStretch()
        vol = QVBoxLayout()
        vol.addLayout(self.rocker("+", "−", "VOLUME",
                                  lambda: self.volume("up"), lambda: self.volume("down")))
        self.mute_btn = button("MUTE", "black", self.toggle_mute)
        vol.addWidget(self.mute_btn)
        row.addLayout(vol)
        return row

    def build_navigation(self):
        grid = QGridLayout()
        grid.setSpacing(0)
        corner = Qt.AlignmentFlag
        grid.addWidget(button("SETUP", "round", lambda: self.menu("on_screen")),
                       0, 0, corner.AlignLeft | corner.AlignTop)
        grid.addWidget(button("OPTION", "round", lambda: self.menu("option")),
                       0, 2, corner.AlignRight | corner.AlignTop)
        grid.addWidget(DPad(lambda c: self.cmd("main/controlCursor", cursor=c)),
                       0, 1, 2, 1, corner.AlignCenter)
        grid.addWidget(button("RETURN", "round",
                              lambda: self.cmd("main/controlCursor", cursor="return")),
                       1, 0, corner.AlignLeft | corner.AlignBottom)
        grid.addWidget(button("DISPLAY", "round", lambda: self.menu("display")),
                       1, 2, corner.AlignRight | corner.AlignBottom)
        return grid

    def build_menus(self):
        box = QVBoxLayout()
        row = QHBoxLayout()
        for label, m in (("TOP MENU", "top_menu"), ("HOME", "home"), ("POP-UP/MENU", "menu")):
            b = button("", "round", lambda x=m: self.menu(x))
            b.setStyleSheet("min-width: 34px; max-width: 34px; min-height: 34px;"
                            "max-height: 34px; border-radius: 17px;")
            row.addLayout(titled(label, b))
        box.addLayout(row)
        colors = QHBoxLayout()
        for m, bg, fg in (("red", "#d32f2f", "white"), ("green", "#2e7d32", "white"),
                          ("yellow", "#f4d03f", "#111"), ("blue", "#1e6fd9", "white")):
            b = button(m.upper(), "color", lambda x=m: self.menu(x))
            b.setStyleSheet(f"background: {bg}; color: {fg};")
            colors.addWidget(b)
        box.addLayout(colors)
        return box

    def build_transport(self):
        box = QVBoxLayout()
        box.setSpacing(6)
        box.addWidget(self.separator())
        row = QHBoxLayout()
        row.addLayout(titled("", button("⏮", "black", lambda: self.playback("previous"))))
        play = button("▶", "black", lambda: self.playback("play_pause"), tip="Play / pausa")
        play.setMinimumWidth(110)
        row.addLayout(titled("MEMORY", play))
        row.addLayout(titled("", button("⏭", "black", lambda: self.playback("next"))))
        box.addLayout(row)
        row = QHBoxLayout()
        for label, text, cb in (("TUNING", "◀◀", lambda: self.tuning(-1)),
                                ("MODE", "■", lambda: self.menu("mode")),
                                ("BAND", "▮▮", self.next_band),
                                ("TUNING", "▶▶", lambda: self.tuning(1))):
            b = button(text, "black", cb)
            b.setMinimumWidth(58)
            row.addLayout(titled(label, b))
        box.addLayout(row)
        return box

    def build_preset(self):
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(caption("PRESET", 7))
        row = QHBoxLayout()
        row.addStretch()
        for text, d in (("‹", -1), ("›", 1)):
            b = button(text, "black", lambda x=d: self.preset(x))
            b.setMinimumWidth(52)
            row.addWidget(b)
        row.addStretch()
        box.addLayout(row)
        return box

    def build_brand(self):
        row = QHBoxLayout()
        row.addStretch()
        logo = QSvgWidget()
        logo.load(QByteArray(EMBLEM.format(c="#e8e8e8", bg="").encode()))
        logo.setFixedSize(QSize(30, 30))
        row.addWidget(logo)
        brand = QLabel("YAMAHA")
        brand.setObjectName("brand")
        row.addWidget(brand)
        row.addStretch()
        gear = button("☰", "black", lambda: self.switch_view("classic"),
                      tip="Vista completa: pestañas, graves, subwoofer, diálogo…")
        gear.setStyleSheet("font-size: 11pt; padding: 0 6px; border-radius: 12px;")
        wrap = QVBoxLayout()
        wrap.addStretch()
        wrap.addWidget(gear)
        row.addLayout(wrap)
        return row

    # ---- acciones ----
    def cmd(self, path, **params):
        self.api.get(path, params, cb=lambda _: QTimer.singleShot(250, self.refresh))

    def flash(self, text):
        self.message = text
        self.msg_timer.start()
        self.render()

    def zs(self):
        return self.status if self.zone == "main" else self.zstatus

    def set_zone(self, z):
        self.zone = z
        self.flash("ZONE B" if z == "zone2" else "ZONE A")
        self.refresh()

    def toggle_power(self):
        on = self.zs().get("power") == "on"
        self.cmd(f"{self.zone}/setPower", power="standby" if on else "on")

    def toggle_mute(self):
        self.cmd(f"{self.zone}/setMute", enable=str(not self.zs().get("mute")).lower())

    def volume(self, direction):
        s = self.zs()
        if "volume" in s:
            s["volume"] = max(0, min(161, s["volume"] + (1 if direction == "up" else -1)))
            s.pop("actual_volume", None)
            self.render()
        self.cmd(f"{self.zone}/setVolume", volume=direction, step=1)

    def cycle_sleep(self):
        nxt = SLEEP_CYCLE.get(self.status.get("sleep", 0), 0)
        self.flash(f"SLEEP {nxt} min" if nxt else "SLEEP OFF")
        self.cmd("main/setSleep", sleep=nxt)

    def menu(self, m):
        self.cmd("main/controlMenu", menu=m)

    def step_input(self, d):
        order = PHYSICAL + NET
        cur = self.status.get("input")
        i = order.index(cur) if cur in order else -1
        nxt = order[(i + d) % len(order)]
        self.status["input"] = nxt
        self.render()
        self.cmd("main/setInput", input=nxt)

    def next_net(self):
        cur = self.status.get("input")
        i = NET_CYCLE.index(cur) + 1 if cur in NET_CYCLE else 0
        self.cmd("main/setInput", input=NET_CYCLE[i % len(NET_CYCLE)])

    def step_program(self, d):
        progs = [p for p in self.programs if p not in ("straight", "surr_decoder")]
        if not progs:
            return
        cur = self.status.get("sound_program")
        i = progs.index(cur) + d if cur in progs else (0 if d > 0 else -1)
        nxt = progs[i % len(progs)]
        self.status["sound_program"] = nxt
        self.render()
        self.cmd("main/setSoundProgram", program=nxt)

    def playback(self, act):
        if self.status.get("input") not in NETUSB:
            return self.flash("Solo en red / USB / Bluetooth")
        if act == "play_pause":
            act = "pause" if self.play.get("playback") == "play" else "play"
        self.cmd("netusb/setPlayback", playback=act)

    def tuning(self, d):
        if self.status.get("input") != "tuner":
            return self.flash("Solo con TUNER")
        if self.tuner.get("band") == "dab":
            self.cmd("tuner/setDabService", dir="next" if d > 0 else "previous")
        else:
            self.cmd("tuner/setFreq", band="fm", tuning="up" if d > 0 else "down")

    def next_band(self):
        if self.status.get("input") != "tuner":
            return self.flash("Solo con TUNER")
        self.cmd("tuner/setBand", band="fm" if self.tuner.get("band") == "dab" else "dab")

    def preset(self, d):
        inp = self.status.get("input")
        if inp == "tuner":
            self.cmd("tuner/switchPreset", dir="next" if d > 0 else "previous")
        elif inp in NETUSB:
            self.api.get("netusb/getPresetInfo", cb=lambda r: self.recall_preset(r, d))
        else:
            self.flash("Sin presintonías en esta entrada")

    def recall_preset(self, r, d):
        nums = [i + 1 for i, p in enumerate((r or {}).get("preset_info", []))
                if p.get("input") not in (None, "", "unknown")]
        if not nums:
            return self.flash("No hay presintonías guardadas")
        self.preset_idx = (getattr(self, "preset_idx", -1 if d > 0 else 0) + d) % len(nums)
        self.flash(f"PRESET {nums[self.preset_idx]}")
        self.cmd("netusb/recallPreset", zone="main", num=nums[self.preset_idx])

    # ---- vistas ----
    def current_view(self):
        return self.classic if self.prefs.value("view", "remote") == "classic" else self

    def show_view(self):
        w = self.current_view()
        if w is self.classic:
            self.classic.apply()
        w.show()
        w.raise_()
        w.activateWindow()

    def switch_view(self, name):
        self.current_view().hide()
        self.prefs.setValue("view", name)
        self.show_view()

    def toggle_visible(self):
        if self.isVisible() or self.classic.isVisible():
            self.hide()
            self.classic.hide()
        else:
            self.show_view()

    # ---- estado ----
    def got_names(self, d):
        if not d:
            QTimer.singleShot(5000, lambda: self.api.get("system/getNameText", cb=self.got_names))
            return
        self.names = {i["id"]: i["text"] for i in d.get("input_list", [])}
        self.programs = {p["id"]: p["text"] for p in d.get("sound_program_list", [])}
        self.input_menu.clear()
        for ids in (PHYSICAL, NET):
            for inp in ids:
                self.input_menu.addAction(self.names.get(inp, inp.upper()),
                                          lambda x=inp: self.cmd("main/setInput", input=x))
            self.input_menu.addSeparator()
        self.program_menu.clear()
        for k, v in self.programs.items():
            self.program_menu.addAction(v, lambda x=k: self.cmd("main/setSoundProgram", program=x))
        self.render()

    def refresh(self):
        self.api.get("main/getStatus", cb=self.got_status)
        if self.zone == "zone2":
            self.api.get("zone2/getStatus", cb=self.got_zstatus)

    def got_zstatus(self, d):
        if d and d.get("response_code") == 0:
            self.zstatus = d
            self.render()

    def got_status(self, d):
        if not d or d.get("response_code") != 0:
            self.status = {}
            self.render()
            return
        self.status = d
        if d.get("power") == "on":
            self.api.get("main/getSignalInfo", cb=self.got_signal)
            if d.get("input") in NETUSB:
                self.api.get("netusb/getPlayInfo", cb=self.got_play)
            elif d.get("input") == "tuner":
                self.api.get("tuner/getPlayInfo", cb=self.got_tuner)
        self.render()

    def got_signal(self, d):
        a = (d or {}).get("audio", {})
        fmt = a.get("format", "")
        self.signal = "SIN SEÑAL" if not fmt or fmt == "---" else f"{fmt} {a.get('fs', '')}".strip()
        self.render()

    def got_play(self, d):
        self.play = d or {}
        self.render()

    def got_tuner(self, d):
        self.tuner = d or {}
        self.render()

    def volume_text(self, s):
        av = s.get("actual_volume") or {}
        if av.get("mode") == "db":
            return f"{av['value']:+.1f} dB"
        return f"{db(s.get('volume', 0)):+.1f} dB"

    def render(self):
        d = self.status
        z = self.zs()
        if not d:
            self.lcd_input.setText("SIN CONEXIÓN")
            self.lcd_program.setText(HOST)
            self.lcd_line.setText("")
            self.lcd_extra.setText("")
            self.tray_update()
            if self.classic.isVisible():
                self.classic.apply()
            return
        on = d.get("power") == "on"
        set_on(self.power_btn, z.get("power") == "on")
        set_on(self.mute_btn, z.get("mute", False))
        set_on(self.pure_btn, d.get("pure_direct", False))
        set_on(self.enh_btn, d.get("enhancer", False))
        set_on(self.straight_btn, d.get("sound_program") == "straight")
        set_on(self.dec_btn, d.get("sound_program") == "surr_decoder")
        set_on(self.sleep_btn, d.get("sleep", 0) > 0)

        if self.zone == "zone2":
            self.lcd_input.setText("ZONE B")
            self.lcd_program.setText("ENCENDIDA" if z.get("power") == "on" else "STANDBY")
            self.lcd_line.setText(f"VOL {self.volume_text(z)}" + ("   MUTE" if z.get("mute") else ""))
            self.lcd_extra.setText(self.message)
        elif not on:
            self.lcd_input.setText("STANDBY")
            self.lcd_program.setText("")
            self.lcd_line.setText("")
            self.lcd_extra.setText(self.message)
        else:
            inp = d.get("input", "")
            self.lcd_input.setText(self.names.get(inp, d.get("input_text", inp)).upper())
            prog = self.programs.get(d.get("sound_program"), d.get("sound_program", ""))
            if d.get("pure_direct"):
                prog = "Pure Direct"
            elif d.get("sound_program") == "surr_decoder":
                prog = DECODERS.get(d.get("surr_decoder_type"), prog)
            self.lcd_program.setText(prog)
            flags = [x for x, k in (("MUTE", "mute"), ("ENH", "enhancer"),
                                    ("XBASS", "extra_bass")) if d.get(k)]
            if d.get("sleep"):
                flags.append(f"SLP{d['sleep']}")
            self.lcd_line.setText(f"VOL {self.volume_text(d)}   {self.signal}   {' '.join(flags)}")
            self.lcd_extra.setText(self.message or self.now_playing(inp))
        self.tray_update()
        if self.classic.isVisible():
            self.classic.apply()

    def now_playing(self, inp):
        if inp in NETUSB and self.play:
            parts = [self.play.get("track"), self.play.get("artist")]
            return " · ".join(x for x in parts if x)
        if inp == "tuner" and self.tuner:
            if self.tuner.get("band") == "dab":
                return (self.tuner.get("dab") or {}).get("service_label", "DAB")
            freq = (self.tuner.get("fm") or {}).get("freq", 0)
            rds = (self.tuner.get("rds") or {}).get("program_service", "")
            return f"FM {freq / 1000:.2f} MHz  {rds}".strip()
        return ""

    # ---- bandeja ----
    def attach_tray(self, tray, mute_action, power_action):
        self.tray, self.tray_mute, self.tray_power = tray, mute_action, power_action

    def tray_update(self):
        if not hasattr(self, "tray"):
            return
        d = self.status
        on = d.get("power") == "on"
        if on:
            name = self.names.get(d.get("input"), d.get("input_text", ""))
            tip = f"{name} · {self.volume_text(d)}" + (" · silencio" if d.get("mute") else "")
        else:
            tip = "Apagado" if d else "Sin conexión"
        self.tray.setToolTip(f"Yamaha RX-V4A\n{tip}")
        self.tray_mute.setChecked(d.get("mute", False))
        self.tray_power.setText("Apagar (standby)" if on else "Encender")

    def closeEvent(self, e):
        if QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()
            self.hide()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Yamaha RX-V4A")
    app.setDesktopFileName("yamaha-control")
    app.setQuitOnLastWindowClosed(False)
    w = Remote()

    tray = QSystemTrayIcon(svg_icon(), app)
    menu = QMenu()
    menu.addAction("Mostrar", w.show_view)
    menu.addAction("Vista mando", lambda: w.switch_view("remote"))
    menu.addAction("Vista completa", lambda: w.switch_view("classic"))
    menu.addSeparator()
    power = QAction("Encender", menu)
    power.triggered.connect(lambda: w.cmd(
        "main/setPower", power="standby" if w.status.get("power") == "on" else "on"))
    menu.addAction(power)
    mute = QAction("Silencio", menu, checkable=True)
    mute.triggered.connect(lambda on: w.cmd("main/setMute", enable=str(on).lower()))
    menu.addAction(mute)
    menu.addAction("Subir volumen", lambda: w.cmd("main/setVolume", volume="up", step=2))
    menu.addAction("Bajar volumen", lambda: w.cmd("main/setVolume", volume="down", step=2))
    inputs = menu.addMenu("Entrada")
    for inp in ("hdmi1", "hdmi2", "hdmi3", "hdmi4", "tv", "bluetooth", "airplay", "spotify"):
        a = inputs.addAction(inp.upper(), lambda x=inp: w.cmd("main/setInput", input=x))
        a.setData(inp)
    inputs.aboutToShow.connect(lambda: [a.setText(w.names.get(a.data(), a.text()))
                                        for a in inputs.actions()])
    menu.addSeparator()
    menu.addAction("Salir", app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda r: w.toggle_visible()
                           if r == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()
    w.attach_tray(tray, mute, power)

    if "--tray" not in sys.argv:
        w.show_view()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
