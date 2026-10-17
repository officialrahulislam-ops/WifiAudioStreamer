"""Opus decoding through PyAV (FFmpeg's built-in Opus decoder, bundled in the pip wheel)."""
import numpy as np

from protocol import CHANNELS, SAMPLE_RATE, opus_head


class OpusDecoder:
    def __init__(self, rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        import av  # imported here so a missing install gives a clean error

        self._av = av
        ctx = av.CodecContext.create("opus", "r")
        for attr, value in (("sample_rate", rate),):
            try:
                setattr(ctx, attr, value)
            except Exception:
                pass
        try:
            ctx.layout = "stereo" if channels == 2 else "mono"
        except Exception:
            pass
        ctx.extradata = opus_head(channels, rate)
        ctx.open()
        self._ctx = ctx

    def decode(self, packet: bytes):
        """Returns float32 array shaped (samples, 2) or None."""
        chunks = []
        for frame in self._ctx.decode(self._av.Packet(packet)):
            chunks.append(_frame_to_stereo(frame))
        if not chunks:
            return None
        return chunks[0] if len(chunks) == 1 else np.concatenate(chunks)


def _frame_to_stereo(frame) -> np.ndarray:
    arr = frame.to_ndarray()
    try:
        ch = len(frame.layout.channels)
    except Exception:
        ch = 2
    if frame.format.is_planar:
        arr = arr.T                      # (channels, n) -> (n, channels)
    else:
        arr = arr.reshape(-1, ch)        # packed: (1, n*ch) -> (n, ch)
    if arr.dtype == np.int16:
        arr = arr.astype(np.float32) / 32768.0
    else:
        arr = arr.astype(np.float32, copy=False)
    if arr.shape[1] == 1:
        arr = np.repeat(arr, 2, axis=1)
    elif arr.shape[1] > 2:
        arr = arr[:, :2]
    return np.ascontiguousarray(arr)
