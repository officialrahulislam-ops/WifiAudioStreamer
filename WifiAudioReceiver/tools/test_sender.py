"""Diagnostic: verifies the Windows half (TCP -> Opus decode -> speakers) without a phone.

    python tools\\test_sender.py 127.0.0.1 <pairing code> [seconds]

Sends a 440 Hz tone encoded with Opus (via PyAV's libopus encoder). If you hear it, the
Windows receiver works and any remaining problem is on the Android side.
"""
import math
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import av  # noqa: E402
import numpy as np  # noqa: E402

from protocol import FrameParser, T_AUDIO, T_HELLO, T_OK, pack, pack_json  # noqa: E402

host, code = sys.argv[1], sys.argv[2]
seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 5

enc = av.CodecContext.create("libopus", "w")
enc.sample_rate = 48000
enc.layout = "stereo"
enc.format = "s16"
enc.bit_rate = 128000
enc.open()

s = socket.create_connection((host, 48011), timeout=5)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
s.sendall(pack_json(T_HELLO, {"v": 1, "name": "Test tone", "code": code, "codec": "opus",
                              "rate": 48000, "ch": 2, "frame_ms": 20}))
parser, reply = FrameParser(), None
while reply is None:
    for t, p in parser.feed(s.recv(4096)):
        reply = (t, p)
print("reply:", reply)
if reply[0] != T_OK:
    sys.exit(1)

n, t0 = 0, time.time()
while time.time() - t0 < seconds:
    idx = np.arange(n * 960, (n + 1) * 960)
    tone = (0.3 * 32767 * np.sin(2 * math.pi * 440 * idx / 48000)).astype(np.int16)
    frame = av.AudioFrame.from_ndarray(np.repeat(tone, 2)[None, :], format="s16", layout="stereo")
    frame.sample_rate = 48000
    frame.pts = n * 960
    for pkt in enc.encode(frame):
        s.sendall(pack(T_AUDIO, bytes(pkt)))
    n += 1
    time.sleep(max(0, t0 + n * 0.02 - time.time()))
s.close()
