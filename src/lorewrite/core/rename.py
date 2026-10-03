"""Rename an entity everywhere (deterministic, no AI; SPEC "Rename a character").

``plan_rename`` is read-only: it lists every occurrence of the entity's name
and renamed aliases (plain mentions with the ``find_mentions`` rules, explicit
``[[links]]`` and their display text, a scene's ``pov`` / ``place`` details,
optionally comments) as a preview. Nothing changes until ``apply_rename`` is
called with the ids the author left ticked.

Safety, in this order: files that changed since the preview are refused; every
scene about to change is snapshotted (``before-rename``); an undo journal is
written; only then are files rewritten atomically (a failure puts every written
file back). ``undo_rename`` restores the scene snapshots, the other files and
the entity note, and skips anything edited since.

Pending AI draft bodies (``<!--ai-->``) are shown but never ticked by default
(``Occurrence.in_draft``); the markers and the ``.drafts`` originals are never
touched. Scene frontmatter is not prose: only ``pov`` / ``place`` are rewritten.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

import yaml

from . import comments, drafts, fsutil, research, scenemeta, snapshots
from . import entities as ent
from .links import find_links, find_mentions

SCOPES = ("scenes", "entities", "research", "notebook", "comments")   # notebook = research (same notes)
DEFAULT_SCOPE = ("scenes", "entities")
JOURNAL_DIR = ".lorewrite/rename-undo"
_KEEP_JOURNALS = 10
_CONTEXT = 60  # characters of line shown each side of an occurrence


@dataclass(frozen=True)
class Occurrence:
    id: str
    file: str       # project-relative path (a comment: the scene it belongs to)
    kind: str       # mention | link | pov | place | comment
    start: int      # code points in the file text (a comment: in its body)
    end: int
    before: str     # the text replaced
    after: str      # what replaces it
    line: int       # 1-based
    pre: str        # the line before / after the match, for display
    post: str
    in_draft: bool = False   # inside a pending AI draft: unticked by default
    comment: str = ""        # comment id, for kind == "comment"

    @property
    def default_on(self) -> bool:
        return not self.in_draft


@dataclass
class RenamePlan:
    entity: str                 # current name
    entity_file: str            # project-relative path of the note
    new_name: str
    new_entity_file: str
    new_aliases: list[str]      # the note's aliases after the rename
    mapping: dict[str, str]     # old name/alias -> new
    scope: tuple[str, ...]
    occurrences: list[Occurrence] = field(default_factory=list)
    digests: dict[str, str] = field(default_factory=dict)  # file/sidecar -> sha256
    kinds: dict[str, str] = field(default_factory=dict)    # file -> scene|entity|research
    skipped: dict[str, str] = field(default_factory=dict)  # file -> why it is left out

    def default_ids(self) -> list[str]:
        return [o.id for o in self.occurrences if o.default_on]

    def files(self) -> list[str]:
        seen: dict[str, None] = {}
        for o in self.occurrences:
            seen.setdefault(o.file)
        return list(seen)


@dataclass
class RenameResult:
    undo_id: str
    replacements: int
    scenes: int                 # scenes rewritten
    changed: list[str]          # project-relative files changed (incl. the note)
    entity_file: str            # where the note is now
    remap: dict[str, str]       # {old note path: new} when the file name changed
    snapshots: dict[str, str]   # scene -> snapshot name


@dataclass
class UndoResult:
    restored: list[str]
    skipped: list[str]          # edited since the rename: left as they are
    entity_file: str


# -- helpers ---------------------------------------------------------------------


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(name: str) -> str:
    return " ".join(str(name).split())


def _rel(project, path: Path) -> str:
    return path.resolve().relative_to(project.root.resolve()).as_posix()


def _read(path: Path) -> str:
    return fsutil.read_text_lenient(path)  # callers that write back check ensure_utf8


def _write(path: Path, text: str) -> None:
    fsutil.ensure_utf8(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def _upper_first(s: str) -> str:
    return s[:1].upper() + s[1:]


def _adapt(found: str, old: str, new: str) -> str:
    """*new* spelled like the occurrence: the note's own spelling, or with a
    leading capital when the text had one the name does not (sentence start)."""
    if found == old:
        return new
    if found[:1].isupper() and not old[:1].isupper():
        return _upper_first(new)
    return new


def _yaml_scalar(value: str) -> str:
    s = yaml.safe_dump(value, allow_unicode=True, width=10 ** 6)
    if s.endswith("\n...\n"):
        s = s[:-5]
    return s.strip()


def _blank_entity_frontmatter(text: str) -> str:
    m = re.match(r"\A---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return text
    return re.sub(r"[^\n]", " ", text[:m.end()]) + text[m.end():]


def _only_pending(text: str) -> str:
    """Only the bodies of pending AI drafts survive (same-length whitespace
    elsewhere, newlines kept)."""
    out = ["\n" if ch == "\n" else " " for ch in text]
    for p in drafts.find_pending(text):
        out[p.body_start:p.body_end] = text[p.body_start:p.body_end]
    return "".join(out)


def _line_info(text: str, start: int, end: int) -> tuple[int, str, str]:
    line = text.count("\n", 0, start) + 1
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    le = len(text) if le == -1 else le
    pre = text[max(ls, start - _CONTEXT):start]
    post = text[end:min(le, end + _CONTEXT)].rstrip("\r")
    return line, pre, post


def _oid(file: str, kind: str, comment: str, start: int, end: int, before: str) -> str:
    raw = f"{file}|{kind}|{comment}|{start}|{end}|{before}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _find_old(mapping: dict[str, str], text: str, *, ci: bool) -> str | None:
    for old in mapping:
        if (text.casefold() == old.casefold()) if ci else (text in (old, _upper_first(old))):
            return old
    return None


def _scan(masked: str, mapping: dict[str, str], all_names: list[str]
          ) -> list[tuple[int, int, str, str, str]]:
    """(start, end, kind, before, after) in *masked*, a text with everything
    that must not be touched blanked out. Offsets index the real text too."""
    hits: list[tuple[int, int, str, str, str]] = []
    for link in find_links(masked):
        old_t = _find_old(mapping, link.target, ci=True)
        new_target = _adapt(link.target, old_t, mapping[old_t]) if old_t else link.target
        new_display = link.display
        if link.display:
            old_d = _find_old(mapping, link.display, ci=True)
            if old_d:
                new_display = _adapt(link.display, old_d, mapping[old_d])
        if new_target == link.target and new_display == link.display:
            continue
        after = f"[[{new_target}" + (f"|{new_display}" if new_display else "") + "]]"
        hits.append((link.start, link.end, "link", masked[link.start:link.end], after))
    for m in find_mentions(masked, all_names):
        old = _find_old(mapping, m.target, ci=False)
        if old:
            hits.append((m.start, m.end, "mention", m.target, _adapt(m.target, old, mapping[old])))
    hits.sort(key=lambda h: h[0])
    return hits


def _frontmatter_hits(text: str, mapping: dict[str, str]
                      ) -> list[tuple[int, int, str, str, str]]:
    block = scenemeta.find(text)
    if block is None:
        return []
    out = []
    for m in re.finditer(r"(?m)^[ \t]*(pov|place)[ \t]*:[ \t]*(.*?)[ \t]*$", text[:block.end],
                         re.IGNORECASE):
        raw = m.group(2)
        value = raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"" else raw
        old = _find_old(mapping, _clean(value), ci=True)
        if old:
            out.append((m.start(2), m.end(2), m.group(1).lower(), raw, _yaml_scalar(mapping[old])))
    return out


def _occurrence(file: str, text: str, hit: tuple, *, in_draft: bool = False,
                comment: str = "") -> Occurrence:
    start, end, kind, before, after = hit
    kind = "comment" if comment else kind
    line, pre, post = _line_info(text, start, end)
    return Occurrence(_oid(file, kind, comment, start, end, before), file, kind, start, end,
                      before, after, line, pre, post, in_draft, comment)


# -- plan ------------------------------------------------------------------------


def _new_aliases(entity: ent.Entity, new_name: str, renamed: dict[str, str],
                 keep_old_as_alias: bool) -> list[str]:
    out: list[str] = []

    def add(alias: str) -> None:
        if alias.casefold() != new_name.casefold() and all(
                alias.casefold() != a.casefold() for a in out):
            out.append(alias)

    for alias in entity.aliases:
        add(renamed.get(alias, alias))
    if keep_old_as_alias and entity.name != new_name:
        add(entity.name)
    return out


def plan_rename(project, entity: ent.Entity, new_name: str, *,
                keep_old_as_alias: bool = True,
                rename_aliases: dict[str, str] | None = None,
                scope: tuple[str, ...] | list[str] = DEFAULT_SCOPE) -> RenamePlan:
    """The preview of renaming *entity* (read-only; raises ValueError for a
    name that cannot be used)."""
    if entity.path is None:
        raise ValueError("this note has no file")
    new_name = _clean(new_name)
    renamed = {a: _clean(b) for a, b in (rename_aliases or {}).items()}
    unknown = [a for a in renamed if a not in entity.aliases]
    if unknown:
        raise ValueError(f"{unknown[0]!r} is not an alias of {entity.name}")
    scope = tuple(s for s in SCOPES if s in set(scope))
    for name in [new_name, *renamed.values()]:
        if not name:
            raise ValueError("a name can't be empty")
        if "/" in name or "\\" in name or "|" in name or "[" in name or "]" in name:
            raise ValueError(f"{name!r} can't be used as a name")
    mapping = {old: new for old, new in
               [(entity.name, new_name), *renamed.items()] if old != new}
    if not mapping:
        raise ValueError("nothing to rename: the new name is the same")
    others = [e for e in project.load_entities() if e.path != entity.path]
    taken = {n.casefold() for e in others for n in e.names}
    for new in mapping.values():
        if new.casefold() in taken:
            raise ValueError(f"{new!r} is already a name or alias of another note")
    new_path = project.entity_path(replace(entity, name=new_name))
    if new_path != entity.path and new_path.exists():
        raise ValueError(f"a note file {new_path.name!r} already exists")
    aliases = _new_aliases(entity, new_name, renamed, keep_old_as_alias)
    plan = RenamePlan(entity.name, _rel(project, entity.path), new_name,
                      _rel(project, new_path), aliases, mapping, scope)
    all_names = [n for e in [entity, *others] for n in e.names]

    def add(path: Path, kind: str, text: str, hits: list[tuple], draft_hits: list[tuple] = ()) -> None:
        rel = _rel(project, path)
        if not fsutil.is_valid_utf8(path):  # rewriting it would destroy its bytes
            plan.skipped[rel] = str(fsutil.NotUtf8Error(path))
            return
        plan.digests[rel] = _digest(text)
        plan.kinds[rel] = kind
        for h in hits:
            plan.occurrences.append(_occurrence(rel, text, h))
        for h in draft_hits:
            plan.occurrences.append(_occurrence(rel, text, h, in_draft=True))

    if "scenes" in scope:
        for scene in project.all_scene_files():
            text = _read(scene)
            base = scenemeta.blank(text)
            hits = _scan(drafts.blank_pending(base), mapping, all_names)
            hits += _frontmatter_hits(text, mapping)
            hits.sort(key=lambda h: h[0])
            draft_hits = _scan(_only_pending(base), mapping, all_names)
            add(scene, "scene", text, hits, draft_hits)
    if "entities" in scope:
        for path in project.list_entity_files():
            text = _read(path)
            add(path, "entity", text, _scan(_blank_entity_frontmatter(text), mapping, all_names))
    if "research" in scope or "notebook" in scope:
        for note in research.list_notes(project):
            text = _read(note.path)
            add(note.path, "research", text, _scan(text, mapping, all_names))
    if "comments" in scope:
        for scene in project.all_scene_files():
            rel = _rel(project, scene)
            for c in comments.load(project.root, scene):
                for h in _scan(c.body, mapping, all_names):
                    plan.occurrences.append(_occurrence(rel, c.body, h, comment=c.id))
            side = comments.sidecar_path(project.root, scene)
            if side.is_file() and any(o.comment and o.file == rel for o in plan.occurrences):
                plan.digests[f"comments:{rel}"] = _digest(_read(side))
    # the note itself is always part of the rename, even with nothing in it
    own = plan.entity_file
    fsutil.ensure_utf8(entity.path)
    if own not in plan.digests:
        plan.digests[own] = _digest(_read(entity.path))
        plan.kinds[own] = "entity"
    return plan


# -- apply -----------------------------------------------------------------------


def _edit(text: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, after in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + after + text[end:]
    return text


def _shift(pos: int, edits: list[tuple[int, int, str]], *, end: bool) -> int:
    """Where offset *pos* of the old text lands in the edited text."""
    delta = 0
    for s, e, after in sorted(edits):
        if e <= pos and not (end is False and s == e == pos):
            delta += len(after) - (e - s)
        elif s < pos < e:  # inside a replaced span: its start / end
            return s + delta + (len(after) if end else 0)
        elif s >= pos:
            break
    return pos + delta


def _journal_dir(project) -> Path:
    return project.root / JOURNAL_DIR


def apply_rename(project, plan: RenamePlan, accepted_ids, index=None) -> RenameResult:
    """Apply the ticked occurrences of *plan* and rename the note. Raises
    (ValueError) before writing anything if a file changed since the preview or
    an id is unknown; after a failure mid-way every written file is put back."""
    by_id = {o.id: o for o in plan.occurrences}
    ids = list(dict.fromkeys(accepted_ids))
    bad = [i for i in ids if i not in by_id]
    if bad:
        raise ValueError("the preview is out of date; preview again")
    picked = [by_id[i] for i in ids]
    root = project.root
    entity_path = root / plan.entity_file
    if not entity_path.is_file():
        raise FileNotFoundError("the note no longer exists")
    new_path = root / plan.new_entity_file
    if new_path != entity_path and new_path.exists():
        raise ValueError(f"a note file {new_path.name!r} already exists")

    text_edits: dict[str, list[tuple[int, int, str]]] = {}
    comment_edits: dict[str, dict[str, list[tuple[int, int, str]]]] = {}
    for o in picked:
        if o.kind == "comment":
            comment_edits.setdefault(o.file, {}).setdefault(o.comment, []).append((o.start, o.end, o.after))
        else:
            text_edits.setdefault(o.file, []).append((o.start, o.end, o.after))
    # the files to rewrite, each checked against the preview
    originals: dict[str, str] = {}
    for rel in {*text_edits, plan.entity_file}:
        fsutil.ensure_utf8(root / rel)
        text = _read(root / rel)
        if _digest(text) != plan.digests.get(rel):
            raise ValueError(f"{rel} changed since the preview; preview again")
        originals[rel] = text
    for o in picked:
        if o.kind != "comment" and originals[o.file][o.start:o.end] != o.before:
            raise ValueError(f"{o.file} changed since the preview; preview again")
    sidecars: dict[str, str | None] = {}
    for rel in comment_edits:
        side = comments.sidecar_path(root, root / rel)
        sidecars[rel] = _read(side) if side.is_file() else None
        if sidecars[rel] is None or _digest(sidecars[rel]) != plan.digests.get(f"comments:{rel}"):
            raise ValueError(f"the comments of {rel} changed since the preview; preview again")
    # comments are re-anchored whenever their scene's text changes
    for rel in text_edits:
        if plan.kinds.get(rel) == "scene" and rel not in sidecars:
            side = comments.sidecar_path(root, root / rel)
            if side.is_file():
                sidecars[rel] = _read(side)

    # 1. snapshot every scene that will change, before anything is written
    scene_rels = [r for r in text_edits if plan.kinds.get(r) == "scene"]
    snaps: dict[str, str] = {}
    for rel in scene_rels:
        snaps[rel] = snapshots.create(project, root / rel, "before-rename", originals[rel]).name

    # 2. the undo journal (originals of the non-scene files and sidecars)
    undo_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    journal = {
        "id": undo_id, "entity": plan.entity, "new_name": plan.new_name,
        "entity_file": plan.entity_file, "new_entity_file": plan.new_entity_file,
        "entity_original": originals[plan.entity_file],
        "files": {r: originals[r] for r in originals
                  if r != plan.entity_file and plan.kinds.get(r) != "scene"},
        "snapshots": snaps, "comments": sidecars, "after": {},
    }
    jpath = _journal_dir(project) / f"{undo_id}.json"
    _write(jpath, json.dumps(journal, ensure_ascii=False, indent=1))

    written: list[str] = []
    try:
        # 3. scenes and other notes (the note itself last)
        new_texts: dict[str, str] = {}
        for rel, edits in text_edits.items():
            if rel == plan.entity_file:
                continue
            new_texts[rel] = _edit(originals[rel], edits)
            _write(root / rel, new_texts[rel])
            written.append(rel)
        for rel in scene_rels:  # re-anchor, then the comment bodies
            if rel in sidecars and sidecars[rel] is not None and (
                    rel in comment_edits or text_edits.get(rel)):
                _rewrite_comments(project, root / rel, originals[rel], new_texts[rel],
                                  text_edits.get(rel, []), comment_edits.get(rel, {}))
                written.append(f"comments:{rel}")
        for rel in comment_edits:
            if rel not in scene_rels:
                scene = root / rel
                text = _read(scene)
                _rewrite_comments(project, scene, text, text, [], comment_edits[rel])
                written.append(f"comments:{rel}")
        # 4. the note: body edits, then name, aliases, file name
        own_text = _edit(originals[plan.entity_file], text_edits.get(plan.entity_file, []))
        entity = ent.Entity.from_markdown(own_text, path=entity_path)
        entity.name = plan.new_name
        entity.aliases = list(plan.new_aliases)
        ent.save_entity(entity, new_path)
        written.append(plan.entity_file)
        if new_path != entity_path:
            entity_path.unlink(missing_ok=True)
    except BaseException:
        _rollback(project, plan, originals, sidecars, written)
        jpath.unlink(missing_ok=True)
        raise

    journal["after"] = {r: _digest(_read(root / r)) for r in new_texts}
    journal["after"][plan.new_entity_file] = _digest(_read(new_path))
    for rel in sidecars:
        side = comments.sidecar_path(root, root / rel)
        journal["after"][f"comments:{rel}"] = _digest(_read(side)) if side.is_file() else ""
    _write(jpath, json.dumps(journal, ensure_ascii=False, indent=1))
    _prune_journals(project)
    if index is not None:
        index.rebuild(project)
    changed = list(dict.fromkeys([*new_texts, plan.new_entity_file]))
    remap = ({plan.entity_file: plan.new_entity_file}
             if plan.entity_file != plan.new_entity_file else {})
    return RenameResult(undo_id, len(picked), len(scene_rels), changed,
                        plan.new_entity_file, remap, snaps)


def _rewrite_comments(project, scene: Path, old_text: str, new_text: str,
                      edits: list[tuple[int, int, str]],
                      body_edits: dict[str, list[tuple[int, int, str]]]) -> None:
    """Keep the scene's comments pinned to the same passages after *edits*
    moved the text, and apply the ticked edits to their bodies."""
    out = []
    for c in comments.load(project.root, scene):
        found = comments.locate(old_text, c) if edits else None
        if found is not None:
            s, e = _shift(found[0], edits, end=False), _shift(found[1], edits, end=True)
            quote, prefix, suffix = comments.anchor(new_text, s, e)
            c = replace(c, quote=quote, prefix=prefix, suffix=suffix)
        if c.id in body_edits:
            c = replace(c, body=_edit(c.body, body_edits[c.id]))
        out.append(c)
    comments.save(project.root, scene, out)


def _rollback(project, plan: RenamePlan, originals: dict[str, str],
              sidecars: dict[str, str | None], written: list[str]) -> None:
    root = project.root
    for rel in written:
        try:
            if rel.startswith("comments:"):
                _restore_sidecar(project, rel[9:], sidecars.get(rel[9:]))
            elif rel in originals:
                _write(root / rel, originals[rel])
        except OSError:
            pass
    try:
        _write(root / plan.entity_file, originals[plan.entity_file])
        if plan.new_entity_file != plan.entity_file:
            (root / plan.new_entity_file).unlink(missing_ok=True)
    except OSError:
        pass


def _restore_sidecar(project, rel: str, text: str | None) -> None:
    side = comments.sidecar_path(project.root, project.root / rel)
    if text is None:
        side.unlink(missing_ok=True)
    else:
        _write(side, text)


def _prune_journals(project) -> None:
    files = sorted(_journal_dir(project).glob("*.json"))
    for old in files[:-_KEEP_JOURNALS]:
        old.unlink(missing_ok=True)


# -- undo ------------------------------------------------------------------------


def latest_undo(project) -> tuple[str, str, str] | None:
    """(undo id, old name, new name) of the most recent rename that can still
    be undone, or None. Survives restarts: the journal is a file."""
    for path in sorted(_journal_dir(project).glob("*.json"), reverse=True):
        try:
            j = json.loads(_read(path))
            return j["id"], j["entity"], j["new_name"]
        except (OSError, ValueError, KeyError):
            continue
    return None


def undo_rename(project, undo_id: str, index=None) -> UndoResult:
    """Put back what ``apply_rename`` changed. A file edited since the rename
    is left alone and reported in ``skipped``."""
    if not re.fullmatch(r"[0-9-]+", undo_id or ""):
        raise ValueError("invalid undo id")
    jpath = _journal_dir(project) / f"{undo_id}.json"
    if not jpath.is_file():
        raise FileNotFoundError("nothing to undo (the rename record is gone)")
    j = json.loads(_read(jpath))
    root = project.root
    after: dict[str, str] = j.get("after", {})
    restored: list[str] = []
    skipped: list[str] = []

    def current(rel: str) -> str | None:
        p = root / rel
        return _digest(_read(p)) if p.is_file() else None

    for rel, name in j["snapshots"].items():  # scenes
        if current(rel) == after.get(rel):
            snapshots.restore(project, root / rel, name)
            restored.append(rel)
        else:
            skipped.append(rel)
    for rel, text in j["files"].items():  # other notes
        if current(rel) == after.get(rel):
            _write(root / rel, text)
            restored.append(rel)
        else:
            skipped.append(rel)
    for rel, text in j["comments"].items():
        side = comments.sidecar_path(root, root / rel)
        now = _digest(_read(side)) if side.is_file() else ""
        if now == after.get(f"comments:{rel}", ""):
            _restore_sidecar(project, rel, text)
        else:
            skipped.append(f"comments of {rel}")
    old_rel, new_rel = j["entity_file"], j["new_entity_file"]
    if current(new_rel) == after.get(new_rel) and (old_rel == new_rel or not (root / old_rel).exists()):
        _write(root / old_rel, j["entity_original"])
        if old_rel != new_rel:
            (root / new_rel).unlink(missing_ok=True)
        restored.append(old_rel)
    elif old_rel != new_rel and not (root / new_rel).exists() and (root / old_rel).is_file() \
            and _read(root / old_rel) == j["entity_original"]:
        restored.append(old_rel)  # an earlier, partial undo already put it back
    else:
        skipped.append(new_rel)
    if restored and not skipped:
        jpath.unlink(missing_ok=True)  # otherwise keep it: a later undo can finish
    if index is not None:
        index.rebuild(project)
    return UndoResult(restored, skipped, old_rel if old_rel in restored else new_rel)
