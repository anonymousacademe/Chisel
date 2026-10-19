"""Read aloud voices, bridge side (chisel/speech/): which engine reads, the natural voices download, and clips.

No project and no lock: these touch only the user's settings, data and state folders. The network is used only
when the author asks: Download (Hugging Face), choosing the speech server's voices, or Play with that engine."""

from __future__ import annotations

import base64
import itertools
import logging
import threading

from ..ai import client as ai_client
from ..speech import cache, endpoint, engine, models, openrouter
from ._bridge import bridge

log = logging.getLogger("chisel")


class SpeechDownloads:
    """At most one model download at a time; the UI polls it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def start(self, variant: str) -> str:
        with self._lock:
            if any(j["state"] == "running" for j in self._jobs.values()):
                raise RuntimeError("The voices are already downloading")
            job_id = f"v{next(self._ids)}"
            job = self._jobs[job_id] = {"state": "running", "stage": "Starting", "fraction": 0.0, "cancel": False}

        def progress(stage: str, fraction: float) -> None:
            job["stage"], job["fraction"] = stage, fraction

        def work() -> None:
            try:
                models.download(variant, progress, cancelled=lambda: job["cancel"])
            except Exception as exc:
                if not isinstance(exc, (ValueError, RuntimeError, OSError)):
                    log.warning("voice download failed", exc_info=True)
                job.update(state="cancelled" if job["cancel"] else "error", error=str(exc))
            else:
                job.update(state="done", fraction=1.0)

        threading.Thread(target=work, name=f"speech-{job_id}", daemon=True).start()
        return job_id

    def status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError("unknown download")
        return {k: v for k, v in job.items() if k != "cancel"}

    def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job["cancel"] = True


_downloads = SpeechDownloads()


class SpeechMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @bridge
    def speech_info(self) -> dict:
        """The chosen engine and server, whether a key is stored, what the local voices are, and the cost facts."""
        prefs = engine.get_prefs()
        return {"prefs": prefs, "hasKey": bool(endpoint.get_key()), "kokoro": models.status(),
                "endpoint": engine.describe(prefs), "openrouter": engine.describe_openrouter(prefs),
                "hasOpenRouterKey": bool(ai_client.get_api_key())}

    @bridge
    def speech_set(self, prefs: dict) -> dict:
        """Change the engine, the speech server's address or model, or the OpenRouter model."""
        saved = engine.set_prefs(prefs if isinstance(prefs, dict) else {})
        return {"prefs": saved, "endpoint": engine.describe(saved), "openrouter": engine.describe_openrouter(saved)}

    @bridge
    def speech_models(self, refresh: bool = False) -> dict:
        """OpenRouter's speech models with their voices and prices (one public request, then kept)."""
        return {"models": openrouter.catalogue(refresh=bool(refresh)),
                "openrouter": engine.describe_openrouter()}

    @bridge
    def speech_set_key(self, key: str = "") -> dict:
        """Store the speech server's key in the keyring (empty: remove it)."""
        if key.strip():
            endpoint.set_key(key.strip())
        else:
            endpoint.clear_key()
        return {"hasKey": bool(endpoint.get_key())}

    @bridge
    def speech_voices(self, engine_id: str = "") -> dict:
        """The voices of an engine: the downloaded local voices, or the speech server's list (one request)."""
        prefs = engine.get_prefs()
        which = engine_id or prefs["engine"]
        if which == "kokoro":
            return {"voices": models.status()["voices"]}
        if which == "openrouter":
            row = next((m for m in openrouter.catalogue() if m["id"] == prefs["orModel"]), None)
            if row is None:
                raise LookupError(f"OpenRouter does not list {prefs['orModel']} as a speech model now; choose another")
            return {"voices": [{"id": v, "name": v, "label": v, "lang": "", "rank": i} for i, v in enumerate(row["voices"])]}
        if which == "endpoint":
            names = endpoint.list_voices(prefs["baseUrl"], endpoint.get_key())
            return {"voices": [{"id": n, "name": n, "label": n, "lang": "", "rank": i} for i, n in enumerate(names)]}
        raise ValueError("the system voices are listed by the window")

    @bridge
    def speech_clip(self, text: str, voice: str, rate: float = 1.0, engine_id: str = "") -> dict:
        """One clip as a WAV data URL, with whether it came from the cache and what it cost (an estimate)."""
        out = engine.render(text, voice, float(rate or 1.0), engine_id or None)
        mime = "audio/wav" if out["wav"][:4] == b"RIFF" else "audio/mpeg"
        return {"dataUrl": f"data:{mime};base64," + base64.b64encode(out["wav"]).decode("ascii"),
                "cached": out["cached"], "chars": out["chars"], "cost": out["cost"]}

    @bridge
    def speech_warm(self) -> dict:
        """Load the local voices' model ahead of the first Play (the reader calls it when it opens)."""
        return {"warmed": engine.warm()}

    @bridge
    def speech_download_start(self, variant: str = "standard") -> dict:
        return {"job": _downloads.start(variant)}

    @bridge
    def speech_download_status(self, job: str) -> dict:
        found = _downloads.status(job)
        if found["state"] == "done":
            found["kokoro"] = models.status()
        return found

    @bridge
    def speech_download_cancel(self, job: str) -> dict:
        _downloads.cancel(job)
        return {}

    @bridge
    def speech_remove(self) -> dict:
        """Delete the downloaded voices and the rendered clips (the voices can be downloaded again)."""
        engine.stop()
        removed = models.remove()
        cleared = cache.clear()
        return {"removed": removed, "clips": cleared, "kokoro": models.status()}
