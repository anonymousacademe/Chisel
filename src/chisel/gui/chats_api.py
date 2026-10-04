"""Attachments (core/attach.py) and saved conversations (.assistant/chats/)."""

from __future__ import annotations

from . import workspace as ws
from ..core import attach, chats, research as research_notes
from ._bridge import bridge


class ChatsMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @bridge
    def list_attachable(self) -> dict:
        """Everything the paperclip can attach, with approximate sizes in words."""
        with self._lock:
            project = self._require()
            return {"items": attach.attachable(project, self.entities),
                    "maxWords": attach.TOTAL_CHARS // 6, "maxItems": attach.MAX_ITEMS}

    @staticmethod
    def _chat_row(info: chats.ChatInfo) -> dict:
        return {"id": info.id, "title": info.title, "created": info.created,
                "updated": info.updated, "count": info.count}

    @bridge
    def list_chats(self) -> dict:
        with self._lock:
            return {"chats": [self._chat_row(i) for i in chats.list_chats(self._require())]}

    @bridge
    def open_chat(self, chat_id: str) -> dict:
        with self._lock:
            return {"chat": chats.load(self._require(), chat_id).as_dict()}

    @bridge
    def save_chat(self, chat_id: str | None, messages: list, scope: str = "scene",
                  attachments: list | None = None) -> dict:
        """Store the conversation as the client has it (see core.chats.save)."""
        with self._lock:
            chat = chats.save(self._require(), chat_id, messages, scope, attachments)
            return {"id": chat.id, "title": chat.title}

    @bridge
    def rename_chat(self, chat_id: str, title: str) -> dict:
        with self._lock:
            chats.rename(self._require(), chat_id, title)
            return {"chats": [self._chat_row(i) for i in chats.list_chats(self._require())]}

    @bridge
    def delete_chat(self, chat_id: str) -> dict:
        with self._lock:
            chats.delete(self._require(), chat_id)
            return {"chats": [self._chat_row(i) for i in chats.list_chats(self._require())]}

    @bridge
    def save_reply_to_notes(self, prompt: str, reply: str) -> dict:
        """Append an assistant reply, with the date and the prompt, to
        notebook/assistant-notes.md (Save to notes)."""
        with self._lock:
            project = self._require()
            path = research_notes.append_assistant_note(project, prompt, reply)
            return {"id": ws.rel_id(project, path)}
