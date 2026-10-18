"""The local voice engine's worker process: ``python -m chisel.speech.kokoro_worker <model folder>``.

It runs apart from the app because the Kokoro package phonemizes with espeak-ng (GPL): the app talks to it over
pipes and never imports it. One JSON request per line on stdin ``{"id", "text", "voice", "speed", "lang"}``, one
JSON reply per line on stdout ``{"id", "ok": true, "wav": <base64>, "seconds"}`` or ``{"id", "ok": false,
"error"}``. The model is loaded on the first request. The process ends when stdin closes."""

from __future__ import annotations

import base64
import io
import json
import sys
import wave
from pathlib import Path


def to_wav(samples, rate: int) -> bytes:
    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


def main(argv: list[str]) -> int:
    folder = Path(argv[0]) if argv else None
    model = None
    out = sys.stdout
    sys.stdout = sys.stderr             # anything a library prints must not look like a reply
    for line in sys.stdin:
        if not line.strip():
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            if model is None:
                from kokoro_onnx import Kokoro

                if folder is None:
                    raise RuntimeError("no model folder")
                model = Kokoro(str(folder / "model.onnx"), str(folder / "voices.npz"))
            speed = min(2.0, max(0.5, float(req.get("speed") or 1.0)))
            samples, rate = model.create(str(req["text"]), voice=str(req["voice"]), speed=speed,
                                         lang=str(req.get("lang") or "en-us"))
            reply = {"id": req_id, "ok": True, "wav": base64.b64encode(to_wav(samples, rate)).decode("ascii"),
                     "seconds": round(len(samples) / rate, 2)}
        except Exception as exc:  # one bad request never ends the worker
            reply = {"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        out.write(json.dumps(reply) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
