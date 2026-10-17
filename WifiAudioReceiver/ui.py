import random
import socket

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QSlider,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

import firewall
from app_icon import make_icon

COLORS = {"ok": "#3ecf8e", "warn": "#f5b83d", "err": "#ff6b6b"}

STYLE = """
#root { background:#17181d; }
#root QLabel { color:#e8eaf0; font-size:10pt; }
#root QLabel#title { font-size:15pt; font-weight:600; }
#root QLabel#muted { color:#8b90a0; }
#root QLabel#section { color:#8b90a0; font-weight:600; }
#root QFrame#card { background:#21232b; border-radius:10px; }
#root QPushButton { background:#2b2e39; color:#e8eaf0; border:none; border-radius:8px; padding:8px 14px; }
#root QPushButton:hover { background:#353948; }
#root QPushButton#primary { background:#2f6df6; color:white; }
#root QPushButton#primary:hover { background:#4a82ff; }
#root QPushButton#link { background:transparent; color:#8b90a0; padding:2px 6px; }
#root QPushButton#link:hover { color:#e8eaf0; }
#root QListWidget { background:#21232b; border:none; border-radius:10px; outline:0; }
#root QListWidget::item { border-bottom:1px solid #2b2e39; }
#root QSlider::groove:horizontal { height:6px; background:#2b2e39; border-radius:3px; }
#root QSlider::sub-page:horizontal { background:#2f6df6; border-radius:3px; }
#root QSlider::handle:horizontal { background:white; width:16px; margin:-5px 0; border-radius:8px; }
"""


class DeviceRow(QWidget):
    def __init__(self, name, ip, on_connect):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(QLabel(f"📱 {name}"))
        sub = QLabel(ip)
        sub.setObjectName("muted")
        col.addWidget(sub)
        btn = QPushButton("Connect")
        btn.setObjectName("primary")
        btn.clicked.connect(lambda: on_connect(ip, name))
        lay.addLayout(col, 1)
        lay.addWidget(btn)


class MainWindow(QWidget):
    def __init__(self, settings, receiver, discovery, discovery_ok=True):
        super().__init__()
        self.setObjectName("root")
        self.settings, self.receiver, self.discovery = settings, receiver, discovery
        self._quitting = False
        self._connected = False
        self._invite_name = None
        self._icon = make_icon()
        self.setWindowTitle("Wi-Fi Audio Receiver")
        self.setWindowIcon(self._icon)
        self.setFixedWidth(380)
        self.setStyleSheet(STYLE)

        self._invite_timer = QTimer(self, singleShot=True, interval=45000)
        self._invite_timer.timeout.connect(self._invite_timeout)
        self._lat_timer = QTimer(self, interval=500)
        self._lat_timer.timeout.connect(self._update_latency)
        self._lat_smooth = None

        self._build_ui()
        self._build_tray()

        vol = int(settings.value("gain", 100))
        muted = settings.value("muted", False, type=bool)
        self.slider.setValue(vol)
        self._on_volume(vol)
        self._set_muted(muted)

        receiver.state_changed.connect(self._on_state)
        discovery.devices_changed.connect(self._on_devices)
        self._on_state("idle", "", "Waiting for phone" if discovery_ok else
                       "Waiting for phone (discovery unavailable — enter this PC's IP on the phone)",
                       "warn" if discovery_ok else "err")
        self._on_devices([])
        QTimer.singleShot(700, self._first_run)

    # ---- layout ---------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("Wi-Fi Audio Receiver")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        # pairing code (idle only)
        self.code_row = QWidget()
        h = QHBoxLayout(self.code_row)
        h.setContentsMargins(0, 0, 0, 0)
        self.code_label = QLabel()
        self.code_label.setObjectName("muted")
        new_code = QPushButton("New code")
        new_code.setObjectName("link")
        new_code.clicked.connect(self._new_code)
        h.addWidget(self.code_label)
        h.addStretch(1)
        h.addWidget(new_code)
        root.addWidget(self.code_row)
        self._refresh_code_label()

        # idle: available devices
        self.idle_box = QWidget()
        v = QVBoxLayout(self.idle_box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        sec = QLabel("Available Devices")
        sec.setObjectName("section")
        self.list = QListWidget()
        self.list.setFixedHeight(130)
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.empty = QLabel("No phones found yet.\nOpen Wi-Fi Audio Sender on your phone,\nor enter this PC's address there.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        v.addWidget(sec)
        v.addWidget(self.list)
        v.addWidget(self.empty)
        root.addWidget(self.idle_box)

        # connected card
        self.conn_box = QFrame()
        self.conn_box.setObjectName("card")
        c = QVBoxLayout(self.conn_box)
        c.setContentsMargins(16, 12, 16, 12)
        self.conn_name = QLabel()
        self.conn_name.setStyleSheet("font-size:12pt; font-weight:600;")
        self.conn_sub = QLabel()
        self.conn_sub.setTextFormat(Qt.RichText)
        c.addWidget(self.conn_name)
        c.addWidget(self.conn_sub)
        self.lat_label = QLabel()
        self.lat_label.setTextFormat(Qt.RichText)
        c.addWidget(self.lat_label)
        root.addWidget(self.conn_box)

        # volume
        vol_lbl = QLabel("Volume")
        vol_lbl.setObjectName("section")
        root.addWidget(vol_lbl)
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 300)
        self.slider.valueChanged.connect(self._on_volume)
        self.vol_pct = QLabel("100%")
        self.vol_pct.setTextFormat(Qt.RichText)
        self.vol_pct.setMinimumWidth(48)
        row.addWidget(self.slider, 1)
        row.addWidget(self.vol_pct)
        root.addLayout(row)
        hint = QLabel("Booster: 100% = unchanged. Above 100% amplifies on top of the Windows volume.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:8pt;")
        root.addWidget(hint)

        # buttons
        btns = QHBoxLayout()
        self.btn_mute = QPushButton("🔊 Mute")
        self.btn_mute.setCheckable(True)
        self.btn_mute.clicked.connect(lambda: self._set_muted(self.btn_mute.isChecked()))
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.clicked.connect(self.receiver.disconnect)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.discovery.refresh)
        btns.addWidget(self.btn_mute)
        btns.addWidget(self.btn_disconnect)
        btns.addWidget(self.btn_refresh)
        root.addLayout(btns)

        bottom = QHBoxLayout()
        fw = QPushButton("Firewall help")
        fw.setObjectName("link")
        fw.clicked.connect(lambda: self._first_run(force=True))
        exit_btn = QPushButton("⏻ Exit app")
        exit_btn.setObjectName("link")
        exit_btn.setToolTip("Fully close the receiver (Ctrl+Q). The X button only hides it to the tray.")
        exit_btn.clicked.connect(self.quit_app)
        bottom.addWidget(fw)
        bottom.addStretch(1)
        bottom.addWidget(exit_btn)
        root.addLayout(bottom)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.quit_app)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self._icon, self)
        self.tray.setToolTip("Wi-Fi Audio Receiver")
        menu = QMenu()
        title = QAction("Wi-Fi Audio Receiver")
        title.setEnabled(False)
        self.act_status = QAction("● Waiting for phone")
        self.act_status.setEnabled(False)
        self.act_open = QAction("Open")
        self.act_open.triggered.connect(self.show_window)
        self.act_mute = QAction("Mute")
        self.act_mute.setCheckable(True)
        self.act_mute.triggered.connect(self._set_muted)
        self.act_disc = QAction("Disconnect")
        self.act_disc.triggered.connect(self.receiver.disconnect)
        act_exit = QAction("Exit")
        act_exit.triggered.connect(self.quit_app)
        for a in (title, self.act_status):
            menu.addAction(a)
        menu.addSeparator()
        for a in (self.act_open, self.act_mute, self.act_disc, act_exit):
            menu.addAction(a)
        self._menu = menu                       # keep a reference
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    # ---- state ----------------------------------------------------
    def _set_status(self, text, level):
        self.status.setText(f'<span style="color:{COLORS[level]}">●</span>&nbsp; {text}')

    def _on_state(self, state, name, message, level):
        connected = state == "connected"
        self._connected = connected
        self.idle_box.setVisible(not connected)
        self.code_row.setVisible(not connected)
        self.conn_box.setVisible(connected)
        self.btn_disconnect.setVisible(connected)
        self.btn_refresh.setVisible(not connected)
        if connected:
            self._invite_timer.stop()
            self._invite_name = None
            self.conn_name.setText(f"📱 {name}")
            self.conn_sub.setText(f'<span style="color:{COLORS["ok"]}">●</span>&nbsp; Receiving audio')
            self._set_status("Connected", "ok")
            self._lat_smooth = None
            self._update_latency()
            self._lat_timer.start()
            text = f"● {name} — Connected"
        else:
            self._lat_timer.stop()
            if self._invite_name and level != "err" and "lost" not in message.lower():
                message, level = f"Asking {self._invite_name} to connect… approve it on the phone.", "warn"
            self._set_status(message, level)
            text = f"● {message}"
        self.act_status.setText(text if len(text) < 60 else text[:57] + "…")
        self.act_disc.setEnabled(connected)
        self.tray.setToolTip(f"Wi-Fi Audio Receiver\n{self.act_status.text()}")
        QTimer.singleShot(0, self.adjustSize)

    def _on_devices(self, devices):
        self.list.clear()
        for d in devices:
            item = QListWidgetItem(self.list)
            row = DeviceRow(d["name"], d["ip"], self._connect_device)
            item.setSizeHint(row.sizeHint())
            self.list.setItemWidget(item, row)
        self.empty.setVisible(not devices)
        self.list.setVisible(bool(devices))

    def _connect_device(self, ip, name):
        self._invite_name = name
        self._on_state("idle", "", "", "warn")
        self._invite_timer.start()
        import threading
        threading.Thread(target=self.discovery.invite, args=(ip, str(self.settings.value("code"))), daemon=True).start()

    def _invite_timeout(self):
        if not self._connected:
            name, self._invite_name = self._invite_name, None
            self._set_status(f"{name} didn't respond. Open the app on the phone and try again.", "err")

    # ---- volume / mute / code ------------------------------------
    def _on_volume(self, value):
        color = COLORS["warn"] if value > 100 else "#e8eaf0"
        self.vol_pct.setText(f'<span style="color:{color}">{value}%</span>')
        self.receiver.set_volume(value / 100.0)
        self.settings.setValue("gain", value)

    @staticmethod
    def _fmt_time(ms):
        return f"{ms:.0f} ms ({ms / 1000:.2f} s)"

    def _update_latency(self):
        buf, out, net = self.receiver.player.latency_ms()
        total = buf + out + net
        self._lat_smooth = total if self._lat_smooth is None else self._lat_smooth * 0.7 + total * 0.3
        color = COLORS["ok"] if self._lat_smooth < 250 else COLORS["warn"]
        self.lat_label.setText(f'Latency ≈ <span style="color:{color}">{self._fmt_time(self._lat_smooth)}</span>')
        self.lat_label.setToolTip(f"Estimate: buffer {buf:.0f} ms + Windows output {out:.0f} ms + "
                                  f"phone capture/encode/Wi-Fi ~{net:.0f} ms")

    def _set_muted(self, muted):
        muted = bool(muted)
        self.receiver.set_muted(muted)
        self.btn_mute.setChecked(muted)
        self.btn_mute.setText("🔇 Unmute" if muted else "🔊 Mute")
        self.act_mute.setChecked(muted)
        self.settings.setValue("muted", muted)

    def _refresh_code_label(self):
        self.code_label.setText(f"Pairing code: <b>{self.settings.value('code')}</b>")

    def _new_code(self):
        self.settings.setValue("code", str(random.randint(1000, 9999)))
        self._refresh_code_label()

    # ---- window / tray behaviour ---------------------------------
    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self.settings.value("tray_hint_shown", False, type=bool):
            self.tray.showMessage("Wi-Fi Audio Receiver",
                                  "Still running in the system tray. Right-click the icon and choose Exit to quit.",
                                  QSystemTrayIcon.Information, 4000)
            self.settings.setValue("tray_hint_shown", True)

    def quit_app(self):
        self._quitting = True
        self.tray.hide()
        QApplication.quit()

    def _first_run(self, force=False):
        if not force:
            if self.settings.value("first_run_done", False, type=bool):
                return
            self.settings.setValue("first_run_done", True)
        box = QMessageBox()
        box.setWindowTitle("Allow network access")
        box.setWindowIcon(self._icon)
        box.setIcon(QMessageBox.Information)
        box.setText("Windows Firewall may ask for permission.")
        box.setInformativeText(
            "To receive audio from your phone, choose “Allow access” (Private networks) when Windows asks.\n\n"
            "Or let this app add a firewall rule now. It is limited to your local network and needs "
            "administrator approval.")
        add = box.addButton("Add firewall rule", QMessageBox.AcceptRole)
        box.addButton("Not now", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is add:
            firewall.add_rule()
