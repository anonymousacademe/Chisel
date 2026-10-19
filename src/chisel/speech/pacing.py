"""Even pacing between clips: each engine pads its clips with its own amount of silence (and a cloud service may
pad differently from one clip to the next), so every clip is trimmed to the same short lead-in and tail.

16-bit PCM WAV only (what the engines are asked for); anything else is returned unchanged."""

from __future__ import annotations

import array
import io
import sys
import wave

LEAD = 0.03          # seconds kept before the first sound
TAIL = 0.22          # seconds kept after the last: the pause before the next clip
THRESHOLD = 400      # of 32767: quieter than this counts as silence


def trim(data: bytes, lead: float = LEAD, tail: float = TAIL, threshold: int = THRESHOLD) -> bytes:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            params = w.getparams()
            frames = w.readframes(params.nframes)
    except (wave.Error, EOFError):
        return data
    if params.sampwidth != 2 or not frames:
        return data
    samples = array.array("h")
    samples.frombytes(frames[: len(frames) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    ch, rate = params.nchannels, params.framerate
    n = len(samples) // ch
    def sound(i: int) -> bool:
        return any(abs(samples[i * ch + c]) > threshold for c in range(ch))

    first = next((i for i in range(n) if sound(i)), None)
    if first is None:
        return data                                   # all silence: leave it to the engine
    last = next(i for i in range(n - 1, -1, -1) if sound(i))
    a = max(0, first - int(lead * rate))
    b = min(n, last + 1 + int(tail * rate))
    kept = samples[a * ch: b * ch]
    if b - (last + 1) < int(tail * rate):             # the engine left less tail than we want: add silence
        kept.extend([0] * ((int(tail * rate) - (b - (last + 1))) * ch))
    if sys.byteorder != "little":
        kept.byteswap()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(kept.tobytes())
    return out.getvalue()
