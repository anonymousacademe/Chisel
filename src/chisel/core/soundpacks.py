"""Typing-sound packs and ambience loops: folders in the user data dir (not in any project).

    <data dir>/sounds/<pack>/   key-*.wav|ogg|mp3|flac, space.*, return.*, backspace.*, pack.toml
    <data dir>/ambience/        loop files (wav/ogg/mp3/flac), listed beside the generated layers

The data dir is platformdirs.user_data_dir("chisel"); CHISEL_DATA_DIR overrides it (LOREWRITE_DATA_DIR is a deprecated alias)
(tests). Format and rules: docs/sound-packs.md. Every name that crosses the bridge goes
through ``_plain`` and every read through ``_inside`` (no path traversal, no symlinks).
"""

from __future__ import annotations

import base64
import io
import os
import re
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

import platformdirs

from .envvars import get_env

AUDIO_EXTS = (".wav", ".ogg", ".mp3", ".flac")
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_FILES = 200
MAX_LOOP_BYTES = 30 * 1024 * 1024
CLASSES = ("key", "space", "return", "backspace")
MIMES = {".wav": "audio/wav", ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".flac": "audio/flac"}
_PLAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,59}$")
_SOUND = re.compile(r"^(key[-_A-Za-z0-9]*|space[-_A-Za-z0-9]*|return[-_A-Za-z0-9]*|backspace[-_A-Za-z0-9]*)$")


def data_dir() -> Path:
    override = get_env("DATA_DIR")
    return Path(override) if override else Path(platformdirs.user_data_dir("chisel", appauthor=False))


def sounds_dir() -> Path:
    return data_dir() / "sounds"


def ambience_dir() -> Path:
    return data_dir() / "ambience"


def _plain(name: str) -> str:
    """A pack or file name that is one plain path component."""
    name = str(name or "")
    if not _PLAIN.match(name) or ".." in name or name.endswith("."):
        raise ValueError("not a valid name")
    return name


def _inside(base: Path, *parts: str) -> Path:
    """base/parts, refusing symlinks and anything that resolves outside *base*."""
    path = base.joinpath(*parts)
    if path.is_symlink():
        raise ValueError("not a valid name")
    root = base.resolve()
    resolved = path.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("not a valid name")
    return path


def audio_kind(head: bytes) -> str | None:
    """The audio format named by the first bytes of a file (never by its extension)."""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return ".wav"
    if head[:4] == b"OggS":
        return ".ogg"
    if head[:4] == b"fLaC":
        return ".flac"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return ".mp3"
    return None


def _data_url(path: Path, limit: int) -> str:
    if path.suffix.lower() not in AUDIO_EXTS or path.stat().st_size > limit:
        raise ValueError("not a usable sound file")
    raw = path.read_bytes()
    if audio_kind(raw[:16]) is None:
        raise ValueError("not a usable sound file")
    return f"data:{MIMES[path.suffix.lower()]};base64,{base64.b64encode(raw).decode('ascii')}"


def _meta(folder: Path) -> dict:
    try:
        data = tomllib.loads((folder / "pack.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    meta = {}
    if isinstance(data.get("name"), str) and data["name"].strip():
        meta["name"] = data["name"].strip()[:60]
    vol = data.get("volume")
    if isinstance(vol, (int, float)) and not isinstance(vol, bool):
        meta["volume"] = max(0.0, min(1.0, float(vol)))
    return meta


def klass(stem: str) -> str:
    """Which key class a file stem belongs to (key-1 -> key)."""
    for name in CLASSES[1:]:
        if stem.lower().startswith(name):
            return name
    return "key"


def _pack_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and not p.is_symlink() and p.suffix.lower() in AUDIO_EXTS
                  and _SOUND.match(p.stem))


def list_packs() -> list[dict]:
    root = sounds_dir()
    if not root.is_dir():
        return []
    rows = []
    for folder in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.is_symlink() or not _PLAIN.match(folder.name):
            continue
        files = _pack_files(folder)
        if files:
            meta = _meta(folder)
            rows.append({"id": folder.name, "name": meta.get("name", folder.name),
                         "volume": meta.get("volume", 1.0), "files": len(files)})
    return rows


def read_pack(pack: str) -> dict:
    """A pack's sounds as data URLs by class (missing classes are left out; the client falls
    back to ``key``)."""
    folder = _inside(sounds_dir(), _plain(pack))
    if not folder.is_dir():
        raise FileNotFoundError("no such sound pack")
    sounds: dict[str, list[str]] = {c: [] for c in CLASSES}
    for path in _pack_files(folder):
        sounds[klass(path.stem)].append(_data_url(path, MAX_TOTAL_BYTES))
    meta = _meta(folder)
    return {"id": folder.name, "name": meta.get("name", folder.name),
            "volume": meta.get("volume", 1.0), "sounds": {k: v for k, v in sounds.items() if v}}


def list_loops() -> list[dict]:
    root = ambience_dir()
    if not root.is_dir():
        return []
    return [{"id": p.name, "name": p.stem}
            for p in sorted(root.iterdir(), key=lambda p: p.name.lower())
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in AUDIO_EXTS
            and _PLAIN.match(p.name)]


def read_loop(name: str) -> str:
    return _data_url(_inside(ambience_dir(), _plain(name)), MAX_LOOP_BYTES)


def _slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9 _.\-]+", "", text).strip(" .-_")
    return text[:60].strip(" .-_")


def import_pack(zip_path: Path | str) -> dict:
    """Validate a ``.zip`` and unpack it as a new pack; nothing is written when anything fails."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("that is not a readable zip file") from exc
    with zf:
        entries = [i for i in zf.infolist() if not i.is_dir()]
        if not entries:
            raise ValueError("the zip is empty")
        if len(entries) > MAX_FILES:
            raise ValueError(f"too many files (at most {MAX_FILES})")
        if sum(i.file_size for i in entries) > MAX_TOTAL_BYTES:
            raise ValueError("the pack is larger than 20 MB")
        names: dict[str, zipfile.ZipInfo] = {}
        for info in entries:
            raw = info.filename
            parts = PurePosixPath(raw).parts
            if "\\" in raw or raw.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
                raise ValueError(f"unsafe path in the zip: {raw}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"links are not allowed: {raw}")
            if len(parts) > 2:
                raise ValueError(f"files may sit at the top or in one folder only: {raw}")
            names[raw] = info
        tops = {PurePosixPath(n).parts[0] for n in names if len(PurePosixPath(n).parts) == 2}
        if tops and any(len(PurePosixPath(n).parts) == 1 for n in names):
            raise ValueError("put every file in one folder, or none in a folder")
        if len(tops) > 1:
            raise ValueError("a zip holds one pack only")
        files: dict[str, bytes] = {}
        total = 0
        for raw, info in names.items():
            leaf = PurePosixPath(raw).name
            stem, ext = os.path.splitext(leaf)
            if leaf.lower() == "pack.toml":
                allowed = True
            else:
                allowed = ext.lower() in AUDIO_EXTS and bool(_SOUND.match(stem)) and _PLAIN.match(leaf)
            if not allowed:
                raise ValueError(f"only sound files named key-*, space, return, backspace (wav/ogg/mp3/flac) "
                                 f"and pack.toml are allowed, not “{leaf}”")
            with zf.open(info) as fh:
                data = fh.read(MAX_TOTAL_BYTES + 1)  # the header size can lie
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("the pack is larger than 20 MB")
            if leaf.lower() != "pack.toml":
                kind = audio_kind(data[:16])
                if kind is None:
                    raise ValueError(f"“{leaf}” is not a wav, ogg, mp3 or flac file")
            files[leaf] = data
        if not any(Path(n).suffix.lower() in AUDIO_EXTS for n in files):
            raise ValueError("the pack has no sound files")
    meta: dict = {}
    if "pack.toml" in files:
        try:
            meta = tomllib.loads(files["pack.toml"].decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ValueError("pack.toml is not valid TOML") from exc
    base = _slug(str(meta.get("name") or "")) or _slug(next(iter(tops), "")) or _slug(Path(str(zip_path)).stem) or "Imported pack"
    root = sounds_dir()
    root.mkdir(parents=True, exist_ok=True)
    pack_id, n = base, 2
    while (root / pack_id).exists():
        pack_id = f"{base} {n}"
        n += 1
    folder = root / pack_id
    folder.mkdir()
    try:
        for leaf, data in files.items():
            (folder / leaf).write_bytes(data)
    except OSError:
        for p in folder.iterdir():
            p.unlink()
        folder.rmdir()
        raise
    return {"id": pack_id, "files": len(files)}


def export_pack(pack: str, dest: Path | str) -> Path:
    """Zip a pack to *dest* (a file path ending .zip, or a folder). Never overwrites."""
    folder = _inside(sounds_dir(), _plain(pack))
    if not folder.is_dir():
        raise FileNotFoundError("no such sound pack")
    dest = Path(dest)
    if dest.is_dir():
        dest = dest / f"{folder.name}.zip"
    if dest.suffix.lower() != ".zip":
        dest = dest.with_name(dest.name + ".zip")
    if dest.exists():
        raise FileExistsError(f"{dest.name} already exists")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.iterdir()):
            if path.is_file() and not path.is_symlink() and (
                    path.name.lower() == "pack.toml" or (path.suffix.lower() in AUDIO_EXTS and _SOUND.match(path.stem))):
                zf.writestr(f"{folder.name}/{path.name}", path.read_bytes())
    dest.write_bytes(buf.getvalue())
    return dest
