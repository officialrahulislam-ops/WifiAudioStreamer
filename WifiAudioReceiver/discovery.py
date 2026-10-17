"""UDP discovery.

* The receiver broadcasts a small beacon once per second so phones can find it.
* Phones broadcast their own beacon while the app is open, so they show up in the
  'Available Devices' list.
* 'Connect' on a phone sends it a unicast invite (with the pairing code); the phone
  then asks Android for audio-capture consent and connects back over TCP.
"""
import json
import socket
import threading
import time

from PySide6.QtCore import QObject, Signal

from protocol import APP_ID, DISCOVERY_PORT, PROTOCOL_VERSION


def local_ipv4s():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))   # no packet is sent; just picks the default route
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.")))


class Discovery(QObject):
    devices_changed = Signal(list)   # [{"name": str, "ip": str}, ...]

    def __init__(self, name: str, tcp_port: int, parent=None):
        super().__init__(parent)
        self._name = name
        self._tcp_port = tcp_port
        self._devices = {}           # ip -> (name, last_seen)
        self._lock = threading.Lock()
        self._running = False
        self._sock = None
        self._wake = threading.Event()
        self._last_emitted = None

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("", DISCOVERY_PORT))
        s.settimeout(0.5)
        self._sock = s
        self._running = True
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._beacon, daemon=True).start()

    def stop(self):
        self._running = False
        self._wake.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def refresh(self):
        with self._lock:
            self._devices.clear()
        self._emit(force=True)
        self._wake.set()

    def invite(self, ip: str, code: str):
        msg = {"app": APP_ID, "v": PROTOCOL_VERSION, "role": "receiver", "type": "invite",
               "name": self._name, "port": self._tcp_port, "code": code}
        data = json.dumps(msg).encode()
        for _ in range(2):  # UDP can drop packets on Wi-Fi; the phone ignores duplicates
            try:
                self._sock.sendto(data, (ip, DISCOVERY_PORT))
            except OSError:
                pass
            time.sleep(0.2)

    # ---- threads --------------------------------------------------
    def _listen(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(2048)
            except socket.timeout:
                data = None
            except OSError:
                if not self._running:
                    break
                time.sleep(0.2)
                continue
            if data:
                self._handle(data, addr[0])
            self._emit()

    def _handle(self, data: bytes, ip: str):
        try:
            msg = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if msg.get("app") != APP_ID or msg.get("role") != "sender":
            return
        with self._lock:
            if msg.get("busy"):
                self._devices.pop(ip, None)
            else:
                self._devices[ip] = (str(msg.get("name") or ip)[:60], time.time())

    def _emit(self, force=False):
        now = time.time()
        with self._lock:
            for ip in [i for i, (_, seen) in self._devices.items() if now - seen > 6]:
                del self._devices[ip]
            snapshot = sorted((n, ip) for ip, (n, _) in self._devices.items())
        if force or snapshot != self._last_emitted:
            self._last_emitted = snapshot
            self.devices_changed.emit([{"name": n, "ip": ip} for n, ip in snapshot])

    def _beacon(self):
        payload = json.dumps({"app": APP_ID, "v": PROTOCOL_VERSION, "role": "receiver",
                              "name": self._name, "port": self._tcp_port}).encode()
        while self._running:
            for ip in local_ipv4s():           # one send per adapter so the right Wi-Fi is used
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.bind((ip, 0))
                    s.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))
                    s.close()
                except OSError:
                    pass
            self._wake.wait(1.0)
            self._wake.clear()
