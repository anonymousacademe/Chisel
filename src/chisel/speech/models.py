"""Downloading the local voice model from Hugging Face, and knowing what is installed.

Only ever on the author's click. The files go to ``<user data>/speech/kokoro/`` (``CHISEL_DATA_DIR`` in tests):
the model, the voices packed into one ``voices.npz`` and a ``manifest.json`` (source, revision, licence,
voices). A download goes into a ``.partial`` folder that is renamed when complete, so a cancelled or failed
download never leaves a half-installed model; the model file is checked against its SHA-256 from Hugging Face."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from ..core import fsutil, soundpacks
from . import catalogue

Progress = Callable[[str, float], None]
API = "https://huggingface.co/api/models/"
RESOLVE = "https://huggingface.co/{repo}/resolve/{rev}/{path}"
UA = {"User-Agent": "chisel-writer (read aloud)"}


def model_dir() -> Path:
    return soundpacks.data_dir() / "speech" / "kokoro"


def manifest() -> dict | None:
    try:
        data = json.loads((model_dir() / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def status() -> dict:
    """What the reader shows: installed or not, its size, voices and licence, and what a download would be."""
    m = manifest()
    folder = model_dir()
    installed = bool(m) and (folder / "model.onnx").is_file() and (folder / "voices.npz").is_file()
    size = sum(p.stat().st_size for p in folder.glob("*") if p.is_file()) if installed else 0
    return {
        "installed": installed, "variant": (m or {}).get("variant", ""), "bytes": size,
        "voices": [catalogue.describe_voice(v) for v in (m or {}).get("voices", [])] if installed else [],
        "licence": catalogue.LICENCE, "source": catalogue.HF_URL, "revision": (m or {}).get("revision", ""),
        "variants": [{"id": k, "bytes": b + 55 * catalogue.VOICE_BYTES, "label": label}
                     for k, (_f, b, label) in catalogue.VARIANTS.items()],
        "engine": engine_available(),
        "hint": "" if engine_available() else ENGINE_HINT_FROZEN if getattr(sys, "frozen", False) else ENGINE_HINT,
    }


ENGINE_HINT = ('The natural voices need the local voice engine. In a terminal: pip install "chisel-writer[speech-local]", '
               "then restart Chisel.")
ENGINE_HINT_FROZEN = ("The natural voices are not in this installer yet. Run Chisel from source with the speech-local "
                      "extra, or use a speech server.")


def engine_available() -> bool:
    """Is the local engine's Python package installed (the ``speech-local`` extra)? The worker runs as
    ``python -m``, which a frozen app cannot do yet (packaging follow-up)."""
    import importlib.util
    if getattr(sys, "frozen", False):
        return False
    try:
        return importlib.util.find_spec("kokoro_onnx") is not None and importlib.util.find_spec("numpy") is not None
    except (ImportError, ValueError):
        return False


def _json(url: str, opener) -> object:
    with opener(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch(url: str, dest: Path, opener, expect_bytes: int | None, sha256: str | None,
           note: Callable[[int], None]) -> None:
    h = hashlib.sha256()
    got = 0
    with opener(urllib.request.Request(url, headers=UA), timeout=60) as r, dest.open("wb") as f:
        while True:
            block = r.read(1 << 16)
            if not block:
                break
            f.write(block)
            h.update(block)
            got += len(block)
            note(got)
    if expect_bytes is not None and got != expect_bytes:
        raise RuntimeError(f"{dest.name}: expected {expect_bytes} bytes, got {got}")
    if sha256 and h.hexdigest() != sha256:
        raise RuntimeError(f"{dest.name} did not match its published checksum; nothing was installed")


def download(variant: str = "standard", progress: Progress | None = None, opener=urllib.request.urlopen,
             cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Download the model *variant* and every voice, verify them and install. Raises ValueError for an unknown
    variant, RuntimeError (a message for the author) when anything fails; nothing is installed then."""
    if variant not in catalogue.VARIANTS:
        raise ValueError(f"unknown model variant: {variant}")
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(ENGINE_HINT) from exc
    note = progress or (lambda stage, fraction: None)
    repo = catalogue.HF_REPO
    try:
        info = _json(API + repo, opener)
        rev = str(info.get("sha") or "main") if isinstance(info, dict) else "main"
        onnx_tree = _json(f"{API}{repo}/tree/{rev}/onnx", opener)
        voice_tree = _json(f"{API}{repo}/tree/{rev}/voices", opener)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not reach Hugging Face: {exc}") from exc

    path, size, _label = catalogue.VARIANTS[variant]
    entry = next((e for e in onnx_tree if isinstance(e, dict) and e.get("path") == path), None) if isinstance(onnx_tree, list) else None
    if entry is None:
        raise RuntimeError(f"{path} is no longer in {repo}")
    size = int(entry.get("size") or size)
    sha = (entry.get("lfs") or {}).get("oid") if isinstance(entry.get("lfs"), dict) else None
    voices = sorted(e["path"].rsplit("/", 1)[-1][:-4] for e in voice_tree
                    if isinstance(e, dict) and str(e.get("path", "")).endswith(".bin")) if isinstance(voice_tree, list) else []
    if not voices:
        raise RuntimeError(f"No voices were listed in {repo}")

    final = model_dir()
    work = final.with_name(final.name + ".partial")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    total = size + len(voices) * catalogue.VOICE_BYTES
    done = 0
    try:
        def tick(got: int, base: int) -> None:
            if cancelled():
                raise RuntimeError("Download cancelled")
            note("Downloading the model", min(0.99, (base + got) / total))
        _fetch(RESOLVE.format(repo=repo, rev=rev, path=path), work / "model.onnx", opener, size, sha,
               lambda got: tick(got, 0))
        done = size
        styles = {}
        for i, voice in enumerate(voices):
            dest = work / f"{voice}.bin"
            _fetch(RESOLVE.format(repo=repo, rev=rev, path=f"voices/{voice}.bin"), dest, opener, None, None,
                   lambda got, base=done: tick(got, base))
            done += catalogue.VOICE_BYTES
            raw = np.fromfile(dest, dtype=np.float32)
            if raw.size % 256:
                raise RuntimeError(f"The voice {voice} is not in the expected format")
            styles[voice] = raw.reshape(-1, 1, 256)
            dest.unlink()
            note(f"Voices {i + 1} of {len(voices)}", min(0.99, done / total))
        np.savez(work / "voices.npz", **styles)
        (work / "manifest.json").write_text(json.dumps({
            "source": catalogue.HF_URL, "repo": repo, "revision": rev, "variant": variant, "file": path,
            "sha256": sha or "", "licence": catalogue.LICENCE, "voices": voices}, indent=2),
            encoding="utf-8", newline="\n")
        if final.exists():
            shutil.rmtree(final)
        fsutil.replace(work, final)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    note("Installed", 1.0)
    return status()


def remove() -> bool:
    """Delete the downloaded model and voices (they can be downloaded again)."""
    folder = model_dir()
    if not folder.exists():
        return False
    shutil.rmtree(folder)
    return True
