"""Low-latency playback with a tiny jitter buffer and an app-level volume/mute.

Volume is applied inside this app's own audio callback, so the Windows system
volume is never touched (the app gets its own entry in the Windows volume mixer).
"""
import collections
import threading

import numpy as np
import sounddevice as sd

from protocol import CHANNELS, SAMPLE_RATE

PREBUFFER_MS = 80    # audio collected before playback starts / resumes after an underrun
TARGET_MS = 100      # when the buffer overflows it is trimmed back to this
MAX_MS = 220         # overflow threshold (caps end-to-end latency after Wi-Fi stalls)


MAX_GAIN = 3.0       # slider goes to 300 %: a software booster on top of the Windows volume
CAPTURE_NET_MS = 40  # assumed phone capture + encode + Wi-Fi time (cannot be measured from the PC)


def _soft_limit(x, thr=0.85):
    """Smoothly squeezes peaks above thr into +-1 so boosted audio distorts far less than hard clipping."""
    a = np.abs(x)
    over = a > thr
    if over.any():
        k = 1.0 - thr
        x[over] = np.sign(x[over]) * (thr + k * np.tanh((a[over] - thr) / k))


def _frames(ms):
    return int(SAMPLE_RATE * ms / 1000)


class AudioPlayer:
    def __init__(self):
        self._lock = threading.Lock()
        self._q = collections.deque()
        self._off = 0
        self._queued = 0
        self._prebuf = True
        self._stream = None
        self._volume = 1.0
        self._muted = False
        self._gain = 0.0
        self.underruns = 0
        self.trimmed = 0

    # ---- controls -------------------------------------------------
    def set_volume(self, v: float):
        self._volume = max(0.0, min(MAX_GAIN, float(v)))

    def set_muted(self, muted: bool):
        self._muted = bool(muted)

    def latency_ms(self):
        """Estimated one-way latency in ms: (jitter buffer, output device, phone+network)."""
        with self._lock:
            buffered = self._queued * 1000.0 / SAMPLE_RATE
        out = 0.0
        try:
            if self._stream is not None:
                out = float(self._stream.latency) * 1000.0
        except Exception:
            pass
        return buffered, out, float(CAPTURE_NET_MS)

    # ---- lifecycle ------------------------------------------------
    def start(self):
        self.stop()
        with self._lock:
            self._q.clear()
            self._off = 0
            self._queued = 0
            self._prebuf = True
        try:  # re-enumerate devices so the *current* Windows default output is used
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        last = None
        for kwargs in self._candidates():
            try:
                stream = sd.OutputStream(**kwargs)
                stream.start()
                self._stream = stream
                return
            except Exception as exc:  # try the next configuration
                last = exc
        raise RuntimeError(f"Could not open the audio output: {last}")

    def stop(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _candidates(self):
        base = dict(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", callback=self._callback)
        out = []
        try:  # WASAPI shared mode = lowest latency without taking exclusive control
            for api in sd.query_hostapis():
                if "WASAPI" in api["name"] and api["default_output_device"] >= 0:
                    out.append(dict(base, device=api["default_output_device"], latency="low",
                                    extra_settings=sd.WasapiSettings(auto_convert=True)))
        except Exception:
            pass
        out.append(dict(base, latency="low"))
        out.append(dict(base))
        return out

    # ---- data in --------------------------------------------------
    def push(self, pcm: np.ndarray):
        with self._lock:
            self._q.append(pcm)
            self._queued += len(pcm)
            if self._queued > _frames(MAX_MS):
                target = _frames(TARGET_MS)
                while self._q and self._queued > target:
                    chunk = self._q.popleft()
                    self._queued -= len(chunk) - self._off
                    self._off = 0
                    self.trimmed += 1

    # ---- data out (audio thread) ---------------------------------
    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if self._prebuf:
                if self._queued >= _frames(PREBUFFER_MS):
                    self._prebuf = False
                else:
                    outdata.fill(0)
                    return
            pos = 0
            while pos < frames and self._q:
                chunk = self._q[0]
                n = min(len(chunk) - self._off, frames - pos)
                outdata[pos:pos + n] = chunk[self._off:self._off + n]
                pos += n
                self._off += n
                self._queued -= n
                if self._off >= len(chunk):
                    self._q.popleft()
                    self._off = 0
            if pos < frames:
                outdata[pos:] = 0
                self._prebuf = True
                self.underruns += 1

        target = 0.0 if self._muted else self._volume
        start = self._gain
        self._gain = target
        if start == target:
            if target != 1.0:
                outdata *= target
        else:  # short ramp avoids clicks when the slider moves / mute toggles
            outdata *= np.linspace(start, target, frames, dtype=np.float32)[:, None]
        if max(start, target) > 1.0:
            _soft_limit(outdata)
