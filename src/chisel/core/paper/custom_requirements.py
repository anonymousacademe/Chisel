"""The author's own requirements of a research project: ``requirements.toml`` at the project root.

Rows have the schema of the journal profiles (``core/paper/journals/*.toml``): ``id, group, title, kind``
("check" | "advice"), ``check``, ``section`` (title patterns), ``min``, ``max``, ``item_chars_max``,
``object``, ``severity`` ("warn" | "info"), plus an optional ``source`` (a guideline file name) and ``quote``
(the guideline sentence the rule came from). ``requirements.evaluate`` runs them after the profile's rows.

Everything here is plain and bounded: ``validate_row`` refuses with a message that names the row, the file is
written by a small hand writer (strings through ``json.dumps``, valid TOML basic strings) and replaced
atomically, and a file that cannot be read gives no rows plus a plain warning (never an exception).
"""

from __future__ import annotations

import json
import re
import tomllib

from . import journals

FILE_NAME = "requirements.toml"
DEFAULT_GROUP = "Your requirements"
MAX_ROWS = 100
MAX_INT = 100_000
ITEM_CHARS_MAX = 10_000
MAX_PATTERNS = 6
PATTERN_MAX = 60
LINE_MAX = 160
SOURCE_MAX = 200
QUOTE_MAX = 240
OBJECTS = ("fig", "tbl", "eq")
# the check kinds a custom row may use: everything requirements.py implements except "ai-declaration"
ALLOWED_CHECKS = tuple(k for k in journals.CHECK_KINDS if k != "ai-declaration")
NEEDS_SECTION = ("section-present", "section-words-max", "section-no-citations", "list-count", "last-section")
KEYS = ("id", "group", "title", "kind", "check", "section", "min", "max", "item_chars_max", "object",
        "severity", "source", "quote")

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _line(value, limit: int = 1_000_000) -> str:
    return " ".join(_CONTROL.sub(" ", str(value if value is not None else "")).split())[:limit].strip()


def _label(row) -> str:
    if isinstance(row, dict):
        return _line(row.get("title") or row.get("id"), 60) or "(untitled)"
    return "(not a row)"


def _int(value, name: str, lo: int, hi: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f'The requirement "{label}" needs a whole number for {name}.')
    value = int(value)
    if not lo <= value <= hi:
        raise ValueError(f'The requirement "{label}": {name} must be between {lo} and {hi}.')
    return value


def validate_row(raw) -> dict:
    """The clean row for *raw*, or ``ValueError`` (plain words, naming the row)."""
    if not isinstance(raw, dict):
        raise ValueError("A requirement is not a row.")
    label = _label(raw)
    rid = str(raw.get("id") if raw.get("id") is not None else "").strip()
    if not journals.is_plain_id(rid):
        raise ValueError(f'The requirement "{label}" needs an id of lowercase letters, digits, - or _ '
                         "(up to 64 characters).")
    title = _line(raw.get("title"))
    if not title:
        raise ValueError(f'The requirement "{label}" needs a title.')
    if len(title) > LINE_MAX:
        raise ValueError(f'The requirement "{label}": the title is longer than {LINE_MAX} characters.')
    group = _line(raw.get("group")) or DEFAULT_GROUP
    if len(group) > LINE_MAX:
        raise ValueError(f'The requirement "{label}": the group is longer than {LINE_MAX} characters.')
    kind = str(raw.get("kind") or "").strip()
    if kind not in ("check", "advice"):
        raise ValueError(f'The requirement "{label}" must be a check or advice.')
    severity = str(raw.get("severity") or "warn").strip()
    if severity not in ("warn", "info"):
        raise ValueError(f'The requirement "{label}": severity must be warn or info.')
    out: dict = {"id": rid, "group": group, "title": title, "kind": kind, "severity": severity}
    if kind == "check":
        check = str(raw.get("check") or "").strip()
        if check == "ai-declaration":
            raise ValueError(f'The requirement "{label}": the AI-use check is only for journal profiles.')
        if check not in ALLOWED_CHECKS:
            raise ValueError(f'The requirement "{label}" uses an unknown check ({check or "none"}).')
        out["check"] = check
        section = raw.get("section")
        if section in (None, ""):
            section = []
        if isinstance(section, str):
            section = [section]
        if not isinstance(section, (list, tuple)):
            raise ValueError(f'The requirement "{label}": section must be a list of title words.')
        pats = [p for p in (_line(p) for p in section) if p]
        if len(pats) > MAX_PATTERNS:
            raise ValueError(f'The requirement "{label}" has more than {MAX_PATTERNS} section patterns.')
        if any(len(p) > PATTERN_MAX for p in pats):
            raise ValueError(f'The requirement "{label}": a section pattern is longer than '
                             f"{PATTERN_MAX} characters.")
        if check in NEEDS_SECTION:
            if not pats:
                raise ValueError(f'The requirement "{label}" needs at least one section pattern.')
            out["section"] = pats
        for key in ("min", "max"):
            if raw.get(key) not in (None, ""):
                out[key] = _int(raw[key], key, 0, MAX_INT, label)
        if raw.get("item_chars_max") not in (None, ""):
            out["item_chars_max"] = _int(raw["item_chars_max"], "item_chars_max", 1, ITEM_CHARS_MAX, label)
        if check == "section-words-max":
            if "max" not in out:
                raise ValueError(f'The requirement "{label}" needs a maximum number of words.')
            out.pop("min", None)
            out.pop("item_chars_max", None)
        elif check == "list-count":
            if "min" not in out and "max" not in out:
                raise ValueError(f'The requirement "{label}" needs a minimum or a maximum number of items.')
            if "min" in out and "max" in out and out["min"] > out["max"]:
                raise ValueError(f'The requirement "{label}": the minimum is above the maximum.')
        else:
            for key in ("min", "max", "item_chars_max"):
                out.pop(key, None)
        if check in ("objects-captioned", "objects-referenced"):
            obj = str(raw.get("object") or "fig").strip()
            if obj not in OBJECTS:
                raise ValueError(f'The requirement "{label}": object must be fig, tbl or eq.')
            out["object"] = obj
    source = _line(raw.get("source"))
    if len(source) > SOURCE_MAX:
        raise ValueError(f'The requirement "{label}": the source name is too long.')
    if source:
        out["source"] = source
    quote = _line(raw.get("quote"))
    if quote:
        out["quote"] = quote[:QUOTE_MAX].strip()
    for value in out.values():              # a lone surrogate cannot be written as UTF-8
        for s in (value if isinstance(value, list) else [value]):
            if isinstance(s, str):
                try:
                    s.encode("utf-8")
                except UnicodeEncodeError:
                    raise ValueError(f'The requirement "{label}" has a character that cannot be saved.') from None
    return out


def validate_rows(rows) -> list[dict]:
    """Every row clean and the ids unique, or ``ValueError`` naming the first bad row."""
    if not isinstance(rows, (list, tuple)):
        raise ValueError("The requirements are not a list.")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"At most {MAX_ROWS} requirements can be saved.")
    out, seen = [], set()
    for raw in rows:
        row = validate_row(raw)
        if row["id"] in seen:
            raise ValueError(f'Two requirements share the id "{row["id"]}" ("{row["title"]}").')
        seen.add(row["id"])
        out.append(row)
    return out


# -- the file --------------------------------------------------------------------------------------------

def path_of(project):
    return project.root / FILE_NAME


def load_report(project) -> tuple[list[dict], str]:
    """(rows, warning): the clean rows of requirements.toml and a plain sentence when the file (or a row of
    it) could not be used, "" otherwise. Never raises."""
    path = path_of(project)
    try:
        if not path.is_file():
            return [], ""
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError, RecursionError):
        return [], f"{FILE_NAME} could not be read, so your own requirements are not checked. Fix or delete the file."
    raw_rows = data.get("requirement") if isinstance(data, dict) else None
    if not isinstance(raw_rows, list):
        return [], ""
    rows, seen, skipped = [], set(), 0
    for raw in raw_rows:
        try:
            row = validate_row(raw)
        except ValueError:
            skipped += 1
            continue
        if row["id"] in seen or len(rows) >= MAX_ROWS:
            skipped += 1
            continue
        seen.add(row["id"])
        rows.append(row)
    warning = ""
    if skipped:
        warning = (f"{skipped} of the requirements in {FILE_NAME} could not be used and "
                   f"{'was' if skipped == 1 else 'were'} skipped.")
    return rows, warning


def load_custom(project) -> list[dict]:
    return load_report(project)[0]


def _toml_value(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in value) + "]"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def to_toml(rows: list[dict]) -> str:
    parts = ["# Your own requirements for this project (edited in Chisel's Requirements dialog).\n"]
    for row in rows:
        lines = ["[[requirement]]"]
        for key in KEYS:
            if key in row:
                lines.append(f"{key} = {_toml_value(row[key])}")
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts)


def save_custom(project, rows) -> list[dict]:
    """Validate every row and replace requirements.toml atomically; nothing is written when any row is
    invalid (``ValueError`` naming it). An empty list removes the file."""
    from ..project import write_atomic
    clean = validate_rows(rows)
    path = path_of(project)
    if not clean:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise ValueError("requirements.toml could not be removed.") from exc
        return []
    try:
        write_atomic(path, to_toml(clean))
    except OSError as exc:
        raise ValueError("requirements.toml could not be saved.") from exc
    return clean


def remove(project, row_id: str) -> list[dict]:
    rows = load_custom(project)
    kept = [r for r in rows if r["id"] != str(row_id)]
    if len(kept) == len(rows):
        raise ValueError("There is no such requirement.")
    return save_custom(project, kept)


def as_requirement(row: dict) -> journals.Requirement:
    """The journals.Requirement of a clean row (patterns folded as a profile load does)."""
    known = {"id", "group", "title", "kind", "check", "section", "severity", "source", "quote"}
    return journals.Requirement(
        row["id"], row.get("group") or DEFAULT_GROUP, row["title"], row["kind"], row.get("check", ""),
        tuple(p.strip().casefold() for p in row.get("section", []) if p.strip()),
        row.get("severity", "warn"), {k: v for k, v in row.items() if k not in known})
