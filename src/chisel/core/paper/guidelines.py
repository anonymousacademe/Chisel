"""Guideline documents: a journal's or funder's instructions kept beside the paper (``guidelines/``).

Plain files, the author's data. They are only ever read by the author (the Guidelines panel) and are
NEVER part of an AI context: nothing in ``ai/`` imports this module. Text extracted from a PDF or a Word
file is a rebuildable cache under ``.chisel/guidelines/<sha256 of the file>.txt``.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from ..entities import slugify

GUIDELINES_DIR = "guidelines"
CACHE_SUBDIR = "guidelines"
MAX_BYTES = 25 * 1024 * 1024
MAX_TOTAL_CHARS = 2_000_000
MAX_PAGE_CHARS = 50_000
MAX_PDF_PAGES = 400
MAX_ZIP_ENTRIES = 2000
MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_XML_BYTES = 40 * 1024 * 1024
MAX_DEPTH = 8
NOTE_MARK = "<!-- pasted -->"
EXTENSIONS = ("pdf", "docx", "md", "txt")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class GuidelineError(ValueError):
    """A refusal with a message written for the author."""


def guidelines_dir(project) -> Path:
    return project.root / GUIDELINES_DIR


def _cache_dir(project) -> Path:
    from ..project import CACHE_DIR
    return project.root / CACHE_DIR / CACHE_SUBDIR


# -- names and doors ------------------------------------------------------------------------------------

def _check_name(name: str) -> str:
    """A plain file name (no folders, no dots-only, no control characters)."""
    if (not isinstance(name, str) or not name or name in (".", "..") or name != Path(name).name
            or "/" in name or "\\" in name or ":" in name or any(ord(c) < 32 for c in name)
            or name.startswith(".") or name.rsplit(".", 1)[-1].lower() not in EXTENSIONS):
        raise GuidelineError("That is not a guideline file name.")
    return name


def _path(project, name: str) -> Path:
    """The file ``guidelines/<name>``, only ever from inside the folder (no links out of it)."""
    folder = guidelines_dir(project)
    path = folder / _check_name(name)
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"No guideline file called {name}.")
    if path.resolve().parent != folder.resolve():
        raise GuidelineError("That is not a guideline file name.")
    return path


def sniff_kind(data: bytes, ext_hint: str = "") -> str:
    """pdf, docx, md or txt from the BYTES; a plain reason (GuidelineError) otherwise."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
        raise GuidelineError("This looks like an archive, not a Word document or a PDF.")
    if b"\x00" not in data:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise GuidelineError("This is not a PDF, a Word (.docx) document or UTF-8 text.") from None
        return "md" if ext_hint.lower().lstrip(".") in ("md", "markdown") else "txt"
    raise GuidelineError("This is not a PDF, a Word (.docx) document or UTF-8 text.")


# -- adding ----------------------------------------------------------------------------------------------

def _store(project, stem: str, ext: str, data: bytes) -> str:
    folder = guidelines_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    base = slugify(stem)[:60].strip("-") or "guideline"
    n = 1
    while True:
        name = f"{base}.{ext}" if n == 1 else f"{base}-{n}.{ext}"
        try:
            with open(folder / name, "xb") as fh:       # never overwrite: a taken name moves on
                fh.write(data)
            return name
        except FileExistsError:
            n += 1
            if n > 999:
                raise GuidelineError("Too many files with that name.") from None


def add_bytes(project, name: str, data: bytes) -> str:
    """Store *data* as a guideline document; returns the stored file name."""
    if len(data) > MAX_BYTES:
        raise GuidelineError(f"{name or 'This file'} is larger than 25 MB.")
    if not data:
        raise GuidelineError(f"{name or 'This file'} is empty.")
    raw = Path(str(name or "").replace("\\", "/")).name
    stem, _, ext_hint = raw.rpartition(".")
    if not stem:
        stem, ext_hint = raw, ""
    kind = sniff_kind(data, ext_hint)
    if ext_hint.lower() == "pdf" and kind != "pdf":
        raise GuidelineError(f"{raw} is not a real PDF file.")
    if ext_hint.lower() == "docx" and kind != "docx":
        raise GuidelineError(f"{raw} is not a real Word (.docx) document.")
    return _store(project, stem, kind, data)


def add_file(project, source_path) -> str:
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"{source.name} was not found.")
    if source.stat().st_size > MAX_BYTES:
        raise GuidelineError(f"{source.name} is larger than 25 MB.")
    return add_bytes(project, source.name, source.read_bytes())


def add_text(project, title: str, text: str) -> str:
    """Pasted text becomes a Markdown note ``guidelines/<slug>.md``."""
    title = (title or "").strip()
    body = (text or "").strip()
    if not body:
        raise GuidelineError("There is no text to save.")
    data = f"{NOTE_MARK}\n# {title or 'Guidelines'}\n\n{body}\n".encode("utf-8")
    if len(data) > MAX_BYTES:
        raise GuidelineError("That text is larger than 25 MB.")
    return _store(project, title or "guidelines", "md", data)


# -- extraction ------------------------------------------------------------------------------------------

def _docx_text(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise GuidelineError("This Word document is damaged.") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
            raise GuidelineError("This Word document is too large to read safely.")
        try:
            info = zf.getinfo("word/document.xml")
        except KeyError:
            raise GuidelineError("This is not a Word document.") from None
        if info.file_size > MAX_XML_BYTES:
            raise GuidelineError("This Word document is too large to read safely.")
        with zf.open(info) as fh:
            xml = fh.read(MAX_XML_BYTES + 1)
    if len(xml) > MAX_XML_BYTES:
        raise GuidelineError("This Word document is too large to read safely.")
    head = xml.lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise GuidelineError("This Word document has an unsafe structure and was not read.")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise GuidelineError("This Word document is damaged.") from None
    body = root.find(f"{_W}body")
    if body is None:
        return ""
    lines: list[str] = []

    def para(p) -> str:
        out = []
        for el in p.iter():
            if el.tag == f"{_W}t" and el.text:
                out.append(el.text)
            elif el.tag == f"{_W}tab":
                out.append("\t")
            elif el.tag == f"{_W}br":
                out.append("\n")
        return "".join(out)

    def walk(parent, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise GuidelineError("This Word document has an unusual structure and was not read.")
        for child in parent:
            if child.tag == f"{_W}p":
                lines.append(para(child))
            elif child.tag == f"{_W}tbl":
                for row in child.findall(f"{_W}tr"):
                    cells = []
                    for cell in row.findall(f"{_W}tc"):
                        mark = len(lines)
                        walk(cell, depth + 1)
                        sub = lines[mark:]
                        del lines[mark:]
                        cells.append(" ".join(s for s in sub if s.strip()))
                    lines.append(" | ".join(cells))
            elif child.tag == f"{_W}sdt":
                content = child.find(f"{_W}sdtContent")
                if content is not None:
                    walk(content, depth + 1)

    walk(body, 0)
    return "\n".join(lines)


def _pdf_text(data: bytes) -> str:
    try:
        import pypdf
    except ImportError:
        raise GuidelineError("Reading PDFs needs the optional pypdf package. Paste the text instead, "
                             "or install it (pip install pypdf).") from None
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise GuidelineError("This PDF is password protected. Paste its text instead.")
        parts: list[str] = []
        total = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = (page.extract_text() or "")[:MAX_PAGE_CHARS]
            parts.append(text)
            total += len(text)
            if total > MAX_TOTAL_CHARS:
                break
    except GuidelineError:
        raise
    except Exception:
        raise GuidelineError("This PDF could not be read. Paste its text instead.") from None
    text = "\n\n".join(parts)
    if not text.strip():
        raise GuidelineError("This looks like a scanned document; paste its text instead.")
    return text


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return re.sub(r"\n{4,}", "\n\n\n", text)


def _kind_of(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _text_of(project, path: Path) -> tuple[str, bool]:
    """(text, truncated) of a guideline file, through the cache. Raises GuidelineError for a file that
    cannot be read (scanned PDF, no pypdf, hostile Word file)."""
    data = path.read_bytes()
    kind = _kind_of(path)
    if kind in ("md", "txt"):
        text = _clean(data.decode("utf-8", errors="replace"))
        if text.startswith(NOTE_MARK):
            text = text[len(NOTE_MARK):].lstrip("\n")
    else:
        digest = hashlib.sha256(data).hexdigest()
        cached = _cache_dir(project) / f"{digest}.txt"
        text = None
        if cached.is_file():
            try:
                text = cached.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = None
        if text is None:
            text = _clean(_docx_text(data) if kind == "docx" else _pdf_text(data))[:MAX_TOTAL_CHARS]
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(text, encoding="utf-8", newline="\n")
            except OSError:
                pass                        # a cache that cannot be written is only slower
    if len(text) > MAX_TOTAL_CHARS:
        return text[:MAX_TOTAL_CHARS], True
    return text, len(text) >= MAX_TOTAL_CHARS


# -- the listing and the doors ---------------------------------------------------------------------------

def list_files(project) -> list[dict]:
    folder = guidelines_dir(project)
    if not folder.is_dir():
        return []
    rows = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        try:
            _check_name(path.name)
        except GuidelineError:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        kind = _kind_of(path)
        row = {"name": path.name, "type": kind, "size": path.stat().st_size, "chars": 0,
               "extracted": False, "message": ""}
        try:
            text, _ = _text_of(project, path)
            row["chars"] = len(text)
            row["extracted"] = True
            if kind == "md" and path.read_bytes().startswith(NOTE_MARK.encode()):
                row["type"] = "note"
        except GuidelineError as exc:
            row["message"] = str(exc)
        except OSError:
            row["message"] = "This file could not be read."
        rows.append(row)
    return rows


def read_text(project, name: str, limit: int = 20000) -> dict:
    path = _path(project, name)
    text, truncated = _text_of(project, path)
    chars = len(text)
    limit = max(1, min(int(limit or 20000), MAX_TOTAL_CHARS))
    if chars > limit:
        text, truncated = text[:limit], True
    return {"name": path.name, "text": text, "truncated": truncated, "chars": chars}


def remove(project, name: str) -> None:
    path = _path(project, name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if _kind_of(path) in ("pdf", "docx") else ""
    path.unlink()
    if digest:
        try:
            (_cache_dir(project) / f"{digest}.txt").unlink(missing_ok=True)
        except OSError:
            pass
