"""Saved assistant conversations: ``<project>/.assistant/chats/<id>.json``.

    {"id": "c3f9a1b2c4", "title": "How would Mara react...", "created": "2026-10-01T10:15:00",
     "updated": "2026-10-01T10:20:41", "scope": "scene",
     "attachments": [{"kind": "scene", "id": "manuscript/01-rain.md"}],
     "messages": [{"id": "...", "role": "user" | "assistant", "text": "...",
                   "error": false, "sources": [{"id": "research/tides.md", "title": "Tides"}]}]}

Plain JSON, author data (committed with the project, never under ``.lorewrite/``).
The title is the first prompt. Chat ids arrive over the GUI bridge, so every
lookup goes through ``_path`` (it refuses anything that is not a plain id).
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CHATS_DIR = ".assistant/chats"
TITLE_MAX = 60
MAX_MESSAGES = 400
MAX_TEXT = 20000
SCOPES = ("scene", "project")
_ID_RE = re.compile(r"^c[0-9a-f]{10}$")


@dataclass
class Chat:
    id: str
    title: str = ""
    created: str = ""
    updated: str = ""
    scope: str = "scene"
    attachments: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "created": self.created, "updated": self.updated,
                "scope": self.scope, "attachments": self.attachments, "messages": self.messages}


@dataclass(frozen=True)
class ChatInfo:
    id: str
    title: str
    created: str
    updated: str
    count: int


def chats_dir(project) -> Path:
    return project.root / CHATS_DIR


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _path(project, chat_id: str) -> Path:
    if not _ID_RE.fullmatch(chat_id or ""):
        raise ValueError("invalid chat id")
    return chats_dir(project) / f"{chat_id}.json"


def title_from(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1].rstrip() + "…"


def _clean_message(m: object) -> dict | None:
    if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
        return None
    text = m.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    out = {"id": str(m.get("id") or secrets.token_hex(6))[:64], "role": m["role"],
           "text": text[:MAX_TEXT]}
    if m.get("error"):
        out["error"] = True
    sources = [{"id": str(s["id"]), "title": str(s.get("title", ""))}
               for s in m.get("sources") or [] if isinstance(s, dict) and s.get("id")]
    if sources:
        out["sources"] = sources
    return out


def _clean_attachment(a: object) -> dict | None:
    if not isinstance(a, dict) or a.get("kind") not in ("scene", "note", "research", "comments"):
        return None
    ident = a.get("id")
    return {"kind": a["kind"], "id": ident} if isinstance(ident, str) and ident else None


def new_id(project) -> str:
    taken = {p.stem for p in chats_dir(project).glob("*.json")} if chats_dir(project).is_dir() else set()
    return next(i for i in (f"c{secrets.token_hex(5)}" for _ in range(1000)) if i not in taken)


def load(project, chat_id: str) -> Chat:
    path = _path(project, chat_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise FileNotFoundError("no such chat") from None
    except ValueError:
        raise ValueError("that chat file is damaged") from None
    if not isinstance(data, dict):
        raise ValueError("that chat file is damaged")
    return Chat(
        id=chat_id, title=str(data.get("title") or ""), created=str(data.get("created") or ""),
        updated=str(data.get("updated") or ""),
        scope=data.get("scope") if data.get("scope") in SCOPES else "scene",
        attachments=[a for a in map(_clean_attachment, data.get("attachments") or []) if a],
        messages=[m for m in map(_clean_message, data.get("messages") or []) if m])


def _write(project, chat: Chat) -> None:
    path = _path(project, chat.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(chat.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def save(project, chat_id: str | None, messages: list, scope: str = "scene",
         attachments: list | None = None) -> Chat:
    """Store a conversation (the client's whole state: it is the truth, so a
    regenerated answer simply replaces the old one). A new chat gets an id and a
    title from its first prompt; an existing chat keeps its title (and creation
    time) unless it is still untitled. Failed answers (``error``) are not kept."""
    clean = [m for m in map(_clean_message, messages or []) if m and not m.get("error")]
    clean = clean[-MAX_MESSAGES:]
    if not clean:
        raise ValueError("nothing to save yet")
    if chat_id:
        try:
            chat = load(project, chat_id)
        except FileNotFoundError:
            chat = Chat(id=chat_id, created=_now())      # deleted elsewhere: save it anew
    else:
        chat = Chat(id=new_id(project), created=_now())
    chat.messages = clean
    chat.scope = scope if scope in SCOPES else "scene"
    chat.attachments = [a for a in map(_clean_attachment, attachments or []) if a]
    chat.updated = _now()
    if not chat.title:
        first = next((m["text"] for m in clean if m["role"] == "user"), "")
        chat.title = title_from(first) or "Conversation"
    _write(project, chat)
    return chat


def list_chats(project) -> list[ChatInfo]:
    """Saved chats, most recently active first."""
    base = chats_dir(project)
    if not base.is_dir():
        return []
    out = []
    for p in base.glob("*.json"):
        if not _ID_RE.fullmatch(p.stem):
            continue
        try:
            c = load(project, p.stem)
        except (OSError, ValueError):
            continue
        out.append((p.stat().st_mtime_ns, ChatInfo(c.id, c.title or "Conversation", c.created,
                                                   c.updated or c.created, len(c.messages))))
    # the file's own clock breaks ties within the same second
    return [i for _, i in sorted(out, key=lambda t: (t[1].updated, t[0], t[1].id), reverse=True)]


def rename(project, chat_id: str, title: str) -> Chat:
    title = title_from(title)
    if not title:
        raise ValueError("a chat needs a title")
    chat = load(project, chat_id)
    chat.title = title
    _write(project, chat)
    return chat


def delete(project, chat_id: str) -> None:
    path = _path(project, chat_id)
    if not path.is_file():
        raise FileNotFoundError("no such chat")
    path.unlink()
