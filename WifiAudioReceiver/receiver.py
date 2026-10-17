"""TCP server: authenticates the phone, decodes Opus packets and feeds the player."""
import json
import socket
import threading
import time

from PySide6.QtCore import QObject, Signal

from decoder import OpusDecoder
from player import AudioPlayer
from protocol import (FrameParser, PROTOCOL_VERSION, TCP_PORT, T_AUDIO, T_BYE, T_HELLO,
                      T_KEEPALIVE, T_OK, T_REJECT, pack, pack_json)


class _Done(Exception):
    pass


class _Conn:
    def __init__(self, sock, ip, name):
        self.sock, self.ip, self.name = sock, ip, name
        self.user_closed = False
        self.remote_bye = False
        self.replaced = False
        self._send_lock = threading.Lock()

    def send(self, data: bytes):
        with self._send_lock:
            self.sock.sendall(data)

    def kill(self):
        for fn in (lambda: self.sock.shutdown(socket.SHUT_RDWR), self.sock.close):
            try:
                fn()
            except OSError:
                pass


class Receiver(QObject):
    # state ("idle"|"connected"), device name, status message, level ("ok"|"warn"|"err")
    state_changed = Signal(str, str, str, str)

    def __init__(self, get_code, parent=None):
        super().__init__(parent)
        self._get_code = get_code
        self.player = AudioPlayer()
        self._server = None
        self._running = False
        self._conn = None
        self._lock = threading.Lock()
        self._fails = {}   # ip -> (count, first_time)  (light brute-force protection)

    # ---- public ---------------------------------------------------
    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("", TCP_PORT))      # raises OSError if another instance owns the port
        srv.listen(4)
        self._server = srv
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self._running = False
        self.disconnect()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        self.player.stop()

    def disconnect(self):
        with self._lock:
            conn = self._conn
        if conn:
            conn.user_closed = True
            try:
                conn.send(pack(T_BYE))
            except OSError:
                pass
            conn.kill()

    def set_volume(self, v: float):
        self.player.set_volume(v)

    def set_muted(self, muted: bool):
        self.player.set_muted(muted)

    # ---- internals ------------------------------------------------
    def _accept_loop(self):
        while self._running:
            try:
                sock, addr = self._server.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(sock, addr[0]), daemon=True).start()

    def _handle(self, sock, ip):
        parser = FrameParser()
        conn = decoder = None
        started = last_rx = time.time()
        last_ka = 0.0
        sock.settimeout(1.0)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        try:
            while self._running:
                try:
                    data = sock.recv(65536)
                    if not data:
                        break
                    last_rx = time.time()
                    frames = parser.feed(data)
                except socket.timeout:
                    frames = []
                for msg_type, payload in frames:
                    if conn is None:
                        if msg_type != T_HELLO:
                            return
                        conn, decoder = self._authenticate(sock, ip, payload)
                        if conn is None:
                            return
                    elif msg_type == T_AUDIO:
                        try:
                            pcm = decoder.decode(payload)
                        except Exception:
                            pcm = None        # skip a bad packet, keep streaming
                        if pcm is not None:
                            self.player.push(pcm)
                    elif msg_type == T_BYE:
                        conn.remote_bye = True
                        raise _Done
                now = time.time()
                if conn is None:
                    if now - started > 5:
                        return
                else:
                    if now - last_ka >= 1.0:
                        conn.send(pack(T_KEEPALIVE))
                        last_ka = now
                    if now - last_rx > 5:
                        break                  # nothing for 5 s: link is dead
        except (OSError, ValueError, _Done):
            pass
        finally:
            self._finish(conn, sock)

    def _blocked(self, ip):
        count, first = self._fails.get(ip, (0, 0.0))
        if time.time() - first > 60:
            self._fails.pop(ip, None)
            return False
        return count >= 5

    def _note_failure(self, ip):
        count, first = self._fails.get(ip, (0, time.time()))
        self._fails[ip] = (count + 1, first)

    def _reject(self, sock, reason):
        try:
            sock.sendall(pack_json(T_REJECT, {"reason": reason}))
        except OSError:
            pass

    def _authenticate(self, sock, ip, payload):
        try:
            hello = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._reject(sock, "bad")
            return None, None
        if self._blocked(ip):
            self._reject(sock, "blocked")
            return None, None
        if hello.get("v") != PROTOCOL_VERSION:
            self._reject(sock, "version")
            return None, None
        if str(hello.get("code", "")).strip() != str(self._get_code()):
            self._note_failure(ip)
            self._reject(sock, "code")
            return None, None
        try:
            decoder = OpusDecoder()
        except Exception:
            self._reject(sock, "decoder")
            self.state_changed.emit("idle", "", "Opus decoder unavailable (reinstall the 'av' package).", "err")
            return None, None

        conn = _Conn(sock, ip, str(hello.get("name") or ip)[:60])
        with self._lock:
            old, self._conn = self._conn, conn
        if old:
            old.replaced = True
            old.kill()
        try:
            self.player.start()
        except Exception:
            with self._lock:
                if self._conn is conn:
                    self._conn = None
            self._reject(sock, "audio")
            self.state_changed.emit("idle", "", "Couldn't open the Windows audio output.", "err")
            return None, None
        conn.send(pack_json(T_OK, {"name": socket.gethostname(), "v": PROTOCOL_VERSION}))
        self.state_changed.emit("connected", conn.name, "Receiving audio", "ok")
        return conn, decoder

    def _finish(self, conn, sock):
        if conn is not None:
            with self._lock:
                current = self._conn is conn
                if current:
                    self._conn = None
            if current:
                self.player.stop()
                if conn.user_closed:
                    self.state_changed.emit("idle", "", "Disconnected", "warn")
                elif conn.remote_bye:
                    self.state_changed.emit("idle", "", "Phone disconnected", "warn")
                else:
                    self.state_changed.emit("idle", "", "Connection lost. Waiting for the phone to reconnect…", "warn")
        try:
            sock.close()
        except OSError:
            pass
