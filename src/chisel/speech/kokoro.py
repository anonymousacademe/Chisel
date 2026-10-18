"""The local voice engine: one long-lived worker process (kokoro_worker.py) that renders text to WAV.

Started on the first clip the author asks for and kept for the session (loading the model takes a few seconds);
``stop()`` ends it. Requests are answered one at a time."""

from __future__ import annotations

import base64
import itertools
import json
import subprocess
import sys
import threading
from pathlib import Path

from ..core import desktop
from . import catalogue, models


def worker_command(folder: Path) -> list[str]:
    return [sys.executable, "-m", "chisel.speech.kokoro_worker", str(folder)]


class KokoroEngine:
    def __init__(self, command: list[str] | None = None) -> None:
        self._command = command
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def _start(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        command = self._command
        if command is None:
            if not models.engine_available():
                raise RuntimeError(models.status()["hint"] or models.ENGINE_HINT)
            if not models.status()["installed"]:
                raise RuntimeError("Download the natural voices first (Read aloud > Voices)")
            command = worker_command(models.model_dir())
        self._proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                      **desktop.NO_CONSOLE)
        return self._proc

    def render(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        """WAV bytes for *text* in *voice*. Raises RuntimeError with a message for the author."""
        with self._lock:
            proc = self._start()
            req_id = next(self._ids)
            request = {"id": req_id, "text": text, "voice": voice, "speed": speed,
                       "lang": catalogue.language_of(voice)}
            try:
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(json.dumps(request) + "\n")      # ASCII: json escapes the rest
                proc.stdin.flush()
                reply = None
                for _ in range(100):                               # skip anything a native library printed
                    line = proc.stdout.readline()
                    if not line:
                        break
                    try:
                        found = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(found, dict) and found.get("id") == req_id:
                        reply = found
                        break
            except (OSError, ValueError) as exc:
                self._kill()
                raise RuntimeError(f"The local voice engine stopped: {exc}") from exc
            if reply is None:
                self._kill()
                raise RuntimeError("The local voice engine stopped unexpectedly")
        if not reply.get("ok"):
            raise RuntimeError(f"The local voice could not read this: {reply.get('error') or 'unknown error'}")
        return base64.b64decode(reply["wav"])

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    def stop(self) -> None:
        """End the worker (it is started again on the next clip)."""
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None
