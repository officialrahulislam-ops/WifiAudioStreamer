"""Wire protocol shared with the Android sender (keep in sync with Protocol.kt).

Discovery  : UDP broadcast/unicast JSON datagrams on DISCOVERY_PORT.
Streaming  : one TCP connection on TCP_PORT, framed as
             [type: u8][length: u32 big-endian][payload]
"""
import json
import struct

APP_ID = "wifi-audio"
PROTOCOL_VERSION = 1
DISCOVERY_PORT = 48010
TCP_PORT = 48011
SAMPLE_RATE = 48000
CHANNELS = 2

T_HELLO = 1       # phone -> PC  json {v, name, code, codec, rate, ch, frame_ms}
T_OK = 2          # PC -> phone  json {name, v}
T_REJECT = 3      # PC -> phone  json {reason}   (code | version | decoder | audio | blocked | bad)
T_AUDIO = 4       # phone -> PC  one raw Opus packet
T_PING = 5        # phone -> PC  (sent only when no audio is flowing)
T_BYE = 6         # either way   clean disconnect, do not reconnect
T_KEEPALIVE = 7   # PC -> phone  once per second so the phone can detect a dead link

_HEADER = struct.Struct(">BI")
MAX_PAYLOAD = 65535


def pack(msg_type: int, payload: bytes = b"") -> bytes:
    return _HEADER.pack(msg_type, len(payload)) + payload


def pack_json(msg_type: int, obj) -> bytes:
    return pack(msg_type, json.dumps(obj).encode("utf-8"))


class FrameParser:
    """Incremental parser: feed() raw TCP bytes, get back complete frames."""

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data: bytes):
        self._buf += data
        frames = []
        while len(self._buf) >= _HEADER.size:
            msg_type, length = _HEADER.unpack_from(self._buf, 0)
            if length > MAX_PAYLOAD:
                raise ValueError("frame too large")
            if len(self._buf) < _HEADER.size + length:
                break
            payload = bytes(self._buf[_HEADER.size:_HEADER.size + length])
            del self._buf[:_HEADER.size + length]
            frames.append((msg_type, payload))
        return frames


def opus_head(channels: int = CHANNELS, rate: int = SAMPLE_RATE, pre_skip: int = 0) -> bytes:
    """19-byte OpusHead header, used as decoder 'extradata'."""
    return b"OpusHead" + struct.pack("<BBHIhB", 1, channels, pre_skip, rate, 0, 0)
