"""Source notes and Zotero sync (contract "Source notes and sync"; plan sections 4.3, 5.1-5.2).

A source is an entity of type ``source`` in ``entities/sources/<slugify(key)>.md``. The note keeps the item's
full CSL JSON in its frontmatter; Zotero notes and highlights live in the block between the zotero markers
and nothing else is ever regenerated::

    <!-- zotero:begin -->
    ## From Zotero
    ...
    <!-- zotero:end -->

    ## My notes
    (the author's text: sync never touches it)

Sync is pull only and goes plan -> author ticks rows -> apply:

- ``plan_sync`` never writes. Rows: ``new``, ``changed``, ``missing`` (the item left Zotero; the note is kept
  and only marked ``zotero_status: missing``) and ``key-mismatch`` (the citation key in Zotero differs from
  the one stored in the note: reported, never applied).
- ``apply_sync`` takes only ticked ids, refuses files changed since the plan (before writing anything), writes
  each note atomically (temp file + rename), splices only the zotero block into the raw text when the
  frontmatter did not change (so the author's text is byte-identical), and records the library version of the
  producing backend only after every note was written and nothing was left unticked.

Sync state (``{state_key: library_version}``) is per user and per project, in
``<state dir>/sources/<project-id>.json`` (``CHISEL_STATE_DIR`` honoured), never in the project.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import entities as ent
from . import fsutil, recents
from .paper.citefmt import csl_year
from .paper.types import ZItem
from .zotero.base import FetchResult, Scope
from .zotero.html2md import _escape as _escape_md
from .zotero.html2md import annotation_to_markdown, html_to_markdown

BEGIN = "<!-- zotero:begin -->"
END = "<!-- zotero:end -->"
MY_NOTES = "## My notes"

# frontmatter keys owned by sync: compared to decide "changed", rewritten on apply
SYNC_KEYS = ("key", "key_source", "zotero_key", "zotero_status", "web_version", "csl", "title", "authors",
             "year")

_FM_RE = re.compile(r"\A(\ufeff?)---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


# -- the zotero block ------------------------------------------------------------------------------

def _marker_spans(body: str) -> tuple[int, int] | None:
    """(index of the begin marker, index of the end marker) when the block is intact, None when there is
    no marker at all; ValueError when the markers are damaged (one missing, repeated or out of order)."""
    nb, ne = body.count(BEGIN), body.count(END)
    if nb == 0 and ne == 0:
        return None
    b, e = body.find(BEGIN), body.find(END)
    if nb != 1 or ne != 1 or e < b:
        raise ValueError("the zotero markers in this note are damaged: fix them by hand")
    return b, e


def replace_block(body: str, md: str) -> str:
    """Replace only the text between the zotero markers with *md*; every other character is returned
    unchanged. Without markers the block is added in front of the author's text. Idempotent."""
    inner = "\n" + md.strip("\n") + "\n" if md.strip("\n") else "\n"
    spans = _marker_spans(body)
    if spans is not None:
        b, e = spans
        return body[:b + len(BEGIN)] + inner + body[e:]
    block = BEGIN + inner + END
    if not body.strip():
        return block + "\n\n" + MY_NOTES + "\n"
    return block + "\n\n" + body


def _block_text(body: str) -> str | None:
    spans = _marker_spans(body)
    if spans is None:
        return None
    return body[spans[0] + len(BEGIN):spans[1]]


def _ann_id(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", raw)


def _safe_url(url: str) -> str:
    """An http(s) URL that is safe inside a Markdown link target, else ""."""
    url = url.strip()
    if not re.match(r"https?://", url, re.IGNORECASE) or re.search(r"[\s<>]", url):
        return ""
    return url.replace("(", "%28").replace(")", "%29")


def _csl_header(csl: dict) -> list[str]:
    """Title line, authors line, venue/year/DOI/URL line (each omitted when the CSL has nothing for it)."""
    out = []
    title = " ".join(str(csl.get("title") or "").split())
    if title:
        out.append("**" + _escape_md(title) + "**")
    authors = _authors(csl)
    if authors:
        out.append(_escape_md("; ".join(authors)))
    venue = csl.get("container-title") or csl.get("publisher") or ""
    if isinstance(venue, list):
        venue = venue[0] if venue else ""
    bits = []
    if str(venue).strip():
        bits.append("*" + _escape_md(" ".join(str(venue).split())) + "*")
    year = _year(csl)
    if year is not None:
        bits.append(str(year))
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", str(csl.get("DOI") or "").strip(), flags=re.IGNORECASE)
    if doi and not re.search(r"[\s<>]", doi):
        bits.append(f"[DOI](https://doi.org/{doi.replace('(', '%28').replace(')', '%29')})")
    url = _safe_url(str(csl.get("URL") or ""))
    if url:
        bits.append(f"[URL]({url})")
    if bits:
        out.append(" · ".join(bits))
    return out


_HTML_TAGS = re.compile(r"</?(?:p|br|b|i|em|strong|sup|sub|a|ul|ol|li)\b[^<>]*>", re.IGNORECASE)


def _abstract_markdown(text: str) -> str:
    """A CSL abstract is usually plain text; only text with real HTML tags goes through the converter.
    Plain text keeps its paragraph breaks and is escaped, never stripped."""
    if _HTML_TAGS.search(text):
        return html_to_markdown(text).strip()
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n"))]
    return "\n\n".join(_escape_md(p) for p in paras if p).strip()


def block_markdown(item: ZItem) -> str:
    """The text of the zotero block for *item*, as readable Markdown: a title line, an authors line, a
    venue/year/DOI/URL line, "### Abstract", "### Notes" and "### Highlights" (each only when present).
    ``source_card`` counts the highlight markers and the Notes section, so those headings stay as they are."""
    csl = item.csl if isinstance(item.csl, dict) else {}
    out = ["## From Zotero"]
    header = _csl_header(csl)
    if header:
        out.append("\n\n".join(header))
    abstract = _abstract_markdown(str(csl.get("abstract") or ""))
    if abstract:
        out += ["### Abstract", abstract]
    out += _notes_and_highlights(item)
    return "\n\n".join(out) if len(out) > 1 else out[0]


def legacy_block_markdown(item: ZItem) -> str:
    """The block as versions before the readable layout wrote it (only to recognise an old note)."""
    return "\n\n".join(["## From Zotero"] + _notes_and_highlights(item))


def _notes_and_highlights(item: ZItem) -> list[str]:
    out: list[str] = []
    notes = [n for n in (html_to_markdown(h).strip() for h in item.notes) if n]
    if notes:
        out += ["### Notes", "\n\n".join(notes)]
    if item.annotations:
        rows = []
        for a in item.annotations:
            md = annotation_to_markdown(a.text, a.comment, a.page)
            lines = (md or "(empty highlight)").split("\n")
            row = "- " + lines[0] + "\n" + "\n".join(("  " + ln) if ln else "" for ln in lines[1:])
            rows.append(row.rstrip("\n") + f"\n  <!--zotero-ann:{_ann_id(a.id)}-->")
        out += ["### Highlights", "\n".join(rows)]
    return out


# -- note content ----------------------------------------------------------------------------------

def _authors(csl: dict) -> list[str]:
    names = []
    for a in csl.get("author") or []:
        if not isinstance(a, dict):
            continue
        fam, giv = str(a.get("family") or "").strip(), str(a.get("given") or "").strip()
        lit = str(a.get("literal") or a.get("name") or "").strip()
        if fam and giv:
            names.append(f"{fam}, {giv}")
        elif fam or lit:
            names.append(fam or lit)
    return names


def _year(csl: dict) -> int | None:
    return csl_year(csl)


def _family(author: str) -> str:
    return author.split(",", 1)[0].strip()


def _alias_for(authors: list[str], year: int | None) -> str | None:
    if not authors or year is None:
        return None
    first = _family(authors[0])
    if len(authors) == 1:
        return f"{first} {year}"
    if len(authors) == 2:
        return f"{first} and {_family(authors[1])} {year}"
    return f"{first} et al. {year}"


def _derived(item: ZItem) -> dict:
    csl = item.csl if isinstance(item.csl, dict) else {}
    out: dict = {"title": str(csl.get("title") or "")}
    authors = _authors(csl)
    out["authors"] = authors
    year = _year(csl)
    if year is not None:
        out["year"] = year
    return out


def item_to_note(item: ZItem, existing: ent.Entity | None) -> ent.Entity:
    """The source note for *item*. With *existing*, everything the author owns (name, aliases, body outside
    the zotero markers, unknown frontmatter keys and their order) is kept and only the sync keys and the
    zotero block change; the stored citation key is never changed here (a different key is a key-mismatch
    that the author resolves). Raises ValueError when *existing* has damaged markers."""
    new_md = block_markdown(item)
    derived = _derived(item)
    if existing is None:
        key = item.citation_key or item.key
        source = "zotero" if item.citation_key else "none"
        extra: dict = {"key": key, "key_source": source, "zotero_key": item.key,
                       "zotero_status": "current", "csl": item.csl}
        extra.update(derived)
        alias = _alias_for(derived["authors"], derived.get("year"))
        return ent.Entity(name=key, type="source", aliases=[alias] if alias else [],
                          body=replace_block("", new_md), extra=extra)
    extra = dict(existing.extra)
    extra.setdefault("key", ent.source_key(existing))
    extra.setdefault("key_source", "zotero" if item.citation_key else "none")
    extra["zotero_key"] = item.key
    extra["zotero_status"] = "current"
    extra["csl"] = item.csl
    for k, v in derived.items():
        extra[k] = v
    if "year" not in derived:
        extra.pop("year", None)
    return replace(existing, type="source", extra=extra, aliases=list(existing.aliases),
                   body=replace_block(existing.body, new_md))


# -- sync state (per user, per project) --------------------------------------------------------------

def _state_path(project) -> Path:
    from .stats import project_id  # same project-id hash as the writing stats
    return recents.default_state_dir() / "sources" / f"{project_id(project.root)}.json"


def load_sync_state(project) -> dict:
    """``{state_key: library_version}`` for ``chain_fetch``; empty when nothing was recorded."""
    try:
        data = json.loads(_state_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, int) and not isinstance(v, bool)}


def record_version(project, state_key: str, version: int) -> None:
    state = load_sync_state(project)
    state[state_key] = int(version)
    path = _state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def cached_items(project) -> list[ZItem]:
    """The project's source notes as ZItems, for the cache backend (citations and export keep working)."""
    out = []
    for e in project.load_entities():
        if not e.is_source:
            continue
        csl = e.extra.get("csl")
        if not isinstance(csl, dict):
            continue
        key = ent.source_key(e)
        out.append(ZItem(key=str(e.extra.get("zotero_key") or key), version=None, csl=csl, citation_key=key))
    return out


# -- plan and apply ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class SyncRow:
    id: str                 # project-relative path of the note (planned path for a new one)
    key: str                # the citation key
    action: str             # new | changed | missing | key-mismatch
    summary: str
    blocked: str = ""       # why a ticked row would still be skipped (damaged markers, key-mismatch)


@dataclass
class SyncPlan:
    rows: list[SyncRow]
    backend: str = ""
    library_version: int | None = None
    state_key: str = ""     # "" when no version may be recorded (limited scope, file, cache, unknown)
    digests: dict = field(default_factory=dict)   # id -> sha256 of the file at plan time, None for new
    items: dict = field(default_factory=dict)     # id -> ZItem (None for missing rows)
    warnings: list = field(default_factory=list)

    @property
    def actionable(self) -> list[SyncRow]:
        return [r for r in self.rows if not r.blocked]


def _rel(project, path: Path) -> str:
    return path.relative_to(project.root).as_posix()


def _digest_bytes(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _synced(e: ent.Entity) -> dict:
    return {k: e.extra.get(k) for k in SYNC_KEYS if k != "web_version"}


def _title(e: ent.Entity, item: ZItem | None = None) -> str:
    t = e.extra.get("title") or (item.csl.get("title") if item and isinstance(item.csl, dict) else "")
    return str(t or "").strip()


def plan_sync(project, result: FetchResult, *, scope: Scope | None = None, state_key: str = "") -> SyncPlan:
    """Compare *result* with the project's source notes. Read-only. *scope* and *state_key* (the
    ``Status.state_key`` of the backend) only decide whether ``apply_sync`` may record a library version:
    never for a limited scope, never without a state key (for the local API it is derived from the
    server id)."""
    web = result.backend == "web"
    if not state_key and result.backend == "local" and result.server_id:
        state_key = f"local:{result.server_id}"
    plan = SyncPlan([], result.backend, result.library_version,
                    state_key if (result.backend in ("web", "local") and not (scope and scope.limited)
                                  and result.library_version is not None) else "")
    sources = [e for e in project.load_entities() if e.is_source and e.path is not None]
    by_zkey = {str(e.extra["zotero_key"]): e for e in sources if e.extra.get("zotero_key")}
    by_key = {ent.source_key(e): e for e in sources}
    used: set[Path] = set()
    seen: set[str] = set()
    claimed: set[Path] = set()      # existing notes already taken by an earlier item
    new_keys: set[str] = set()      # citation keys already given to a planned new note

    def new_path(key: str) -> Path:
        probe = ent.Entity(name=key, type="source", extra={"key": key})
        path = project.entity_path(probe)
        n = 1
        while path.exists() or path in used:
            n += 1
            path = path.with_name(f"{ent.slugify(key)}-{n}.md")
        return path

    def add(row: SyncRow, digest, item):
        plan.rows.append(row)
        plan.digests[row.id] = digest
        plan.items[row.id] = item

    def blocked_dup(rid: str, key: str, summary: str, digest, item):
        """A blocked key-mismatch row; its id must be unique, so a clash gets the would-be file name."""
        if rid in plan.digests:
            path = new_path(key)
            used.add(path)
            rid, digest = _rel(project, path), None
        add(SyncRow(rid, key, "key-mismatch", summary, blocked="key-mismatch"), digest, item)

    def mark_missing(e: ent.Entity):
        if e.extra.get("zotero_status") == "missing":
            return
        rid = _rel(project, e.path)
        add(SyncRow(rid, ent.source_key(e), "missing",
                    f"No longer in Zotero; the note is kept and marked missing ({_title(e) or 'untitled'})"),
            _digest_bytes(e.path), None)

    for item in result.items:
        seen.add(item.key)
        e = by_zkey.get(item.key)
        if item.deleted:
            if e is not None:
                mark_missing(e)
            continue
        if e is None:
            other = by_key.get(item.citation_key) if item.citation_key else None
            if other is not None and other.extra.get("zotero_key") in (None, ""):
                e = other  # a note made by hand under this key: adopt it
            elif other is not None:
                blocked_dup(_rel(project, other.path), ent.source_key(other),
                            f"The key {item.citation_key} is already used by another Zotero item "
                            f"({other.extra.get('zotero_key')}); nothing was changed",
                            _digest_bytes(other.path), item)
                continue
        if e is not None and e.path in claimed:
            key = item.citation_key or item.key
            blocked_dup(_rel(project, e.path), key,
                        f"Two Zotero items share the key {key}; this one was not applied. "
                        "Give one of them a different citation key in Zotero", None, item)
            continue
        if e is not None:
            claimed.add(e.path)
        if e is None:
            note = item_to_note(item, None)
            nkey = ent.source_key(note)
            if nkey.casefold() in new_keys:
                blocked_dup(_rel(project, new_path(nkey)), nkey,
                            f"Two Zotero items share the key {nkey}; this one was not applied. "
                            "Give one of them a different citation key in Zotero", None, item)
                continue
            new_keys.add(nkey.casefold())
            path = new_path(nkey)
            used.add(path)
            title = _title(note, item) or "untitled"
            warn = "" if item.citation_key else " (no citation key in Zotero: set one there, then sync again)"
            add(SyncRow(_rel(project, path), ent.source_key(note), "new", f"New source: {title}{warn}"),
                None, item)
            continue
        stored = ent.source_key(e)
        rid = _rel(project, e.path)
        if item.citation_key and item.citation_key != stored:
            blocked_dup(rid, stored,
                        f"Zotero now has the key {item.citation_key}, the note has {stored}; "
                        "the key is not changed by a sync", _digest_bytes(e.path), item)
            continue
        try:
            note = item_to_note(item, e)
        except ValueError as exc:
            add(SyncRow(rid, stored, "changed", str(exc), blocked="damaged markers"),
                _digest_bytes(e.path), item)
            continue
        what = []
        if _synced(note) != _synced(e) or e.extra.get("zotero_status") != "current":
            what.append("details")
        old_block, new_block = _block_text(e.body), _block_text(note.body)
        if old_block != new_block:
            if old_block is not None and old_block.strip() == _block_text(
                    replace_block("", legacy_block_markdown(item))).strip():
                what.append("reformatted")   # an old-layout block with nothing new in it
            else:
                what.append("notes and highlights")
        if web and item.version is not None and e.extra.get("web_version") != item.version:
            what.append("version")
        if not what:
            continue
        if e.extra.get("zotero_status") == "missing":
            what.insert(0, "back in Zotero")
        said = {"details": "details changed", "notes and highlights": "notes and highlights changed",
                "version": "version changed", "reformatted": "reformatted to the readable layout"}
        text = "; ".join(said.get(w, w) for w in what)
        add(SyncRow(rid, stored, "changed", f"{_title(note, item) or stored}: {text}"),
            _digest_bytes(e.path), item)

    for zkey in result.deleted_keys:
        e = by_zkey.get(zkey)
        if e is not None and zkey not in seen:
            mark_missing(e)
    return plan


def _atomic_write(path: Path, text: str, *, exclusive: bool = False) -> None:
    """Write via a temp file + rename. *exclusive* (a new note) first claims the name with O_EXCL, so a file
    that appeared after the plan raises FileExistsError instead of being overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    claimed = False
    try:
        if exclusive:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
            claimed = True
        tmp.write_text(text, encoding="utf-8", newline="\n")
        fsutil.replace(tmp, path)
    except BaseException:
        for p in (tmp, path if claimed else None):
            if p is not None:
                try:
                    p.unlink()
                except OSError:
                    pass
        raise


def _splice(raw: str, new: ent.Entity, old: ent.Entity, *, frontmatter_only: bool = False) -> str:
    """The new file text for an existing note: the raw text with only what changed replaced. The frontmatter
    is re-serialised only when a managed value changed (keeping a leading BOM and the file's newline style);
    the body changes only between the markers, and not at all with *frontmatter_only*."""
    m = _FM_RE.match(raw)
    head_raw = raw[:m.end()] if m else ""
    body_raw = raw[m.end():] if m else raw
    if frontmatter_only:
        body = body_raw
    else:
        block = _block_text(new.body)
        body = replace_block(body_raw, block) if block is not None else body_raw
    same_head = (new.name == old.name and new.aliases == old.aliases and new.extra == old.extra
                 and m is not None)
    if same_head:
        return head_raw + body
    head = replace(new, body="").to_markdown()  # ends with "---\n\n"
    head = head[:-1]
    if "\r\n" in head_raw:
        head = head.replace("\n", "\r\n")
    return (m.group(1) if m else "") + head + body


def apply_sync(project, plan: SyncPlan, ticked_ids: list[str]) -> dict:
    """Write the ticked rows. Raises ValueError, before writing anything, for an unknown id or a file that
    changed since the plan. Rows that cannot be applied (key-mismatch, damaged markers, a file that changed
    or appeared after the plan, an unreadable file) are skipped and reported; one bad row never stops the
    others. Returns ``{"changed": [ids], "skipped": [{"id", "reason"}], "recorded": bool}``."""
    rows = {r.id: r for r in plan.rows}
    ids = list(dict.fromkeys(ticked_ids))
    if any(i not in rows for i in ids):
        raise ValueError("the preview is out of date; preview again")
    for i in ids:
        path = project.root / i
        if plan.digests.get(i) != _digest_bytes(path):
            raise ValueError(f"{path.name} changed since the preview; preview again")
    skipped = [{"id": i, "reason": rows[i].blocked} for i in ids if rows[i].blocked]
    todo = [rows[i] for i in ids if not rows[i].blocked]
    changed: list[str] = []
    web = plan.backend == "web"
    for row in todo:
        path = project.root / row.id
        item = plan.items.get(row.id)
        try:
            if plan.digests.get(row.id) != _digest_bytes(path):   # re-check right before writing
                raise ValueError(f"{path.name} changed since the preview; preview again")
            if row.action == "new":
                note = item_to_note(item, None)
                if web and item.version is not None:
                    note.extra["web_version"] = item.version
                _atomic_write(path, note.to_markdown(), exclusive=True)
            else:
                fsutil.ensure_utf8(path)
                old = ent.load_entity(path)
                raw = path.read_bytes().decode("utf-8")  # raw: CRLF in the author's text must survive
                if row.action == "missing":
                    extra = dict(old.extra)
                    extra["zotero_status"] = "missing"
                    new = replace(old, extra=extra)
                else:
                    new = item_to_note(item, old)
                    if web and item.version is not None:
                        new.extra["web_version"] = item.version
                _atomic_write(path, _splice(raw, new, old, frontmatter_only=row.action == "missing"))
        except (ValueError, OSError) as exc:   # NotUtf8Error and FileExistsError are among these
            skipped.append({"id": row.id, "reason": str(exc) or type(exc).__name__})
            continue
        changed.append(row.id)
    recorded = False
    done = set(changed)
    if (plan.state_key and plan.library_version is not None and not skipped
            and all(r.id in done for r in plan.actionable) and not skipped_blocking(plan)):
        record_version(project, plan.state_key, plan.library_version)
        recorded = True
    return {"changed": changed, "skipped": skipped, "recorded": recorded}


def skipped_blocking(plan: SyncPlan) -> bool:
    """True when the plan has a row that can never be applied (key-mismatch, damaged markers): the library
    version is then not recorded, so the next sync shows it again."""
    return any(r.blocked for r in plan.rows)
