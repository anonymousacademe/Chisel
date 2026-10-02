"""The assistant in the terminal: a small chat window over ``ai.writing.ask``
(about the open scene or the project) and, in research mode, over
``ai.writing.research_answer`` (answers from your research notes and the canon,
citing the notes used). Suggest-only: nothing here edits the manuscript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..core.chats import ChatInfo

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

MODES = ("chat", "research")


@dataclass
class ChatMsg:
    role: str                       # "user" | "assistant"
    text: str
    error: bool = False
    #: research notes an answer was given: (project-relative id, title), in citation order
    sources: list[tuple[str, str]] = field(default_factory=list)


def render(msg: ChatMsg) -> Text:
    text = Text()
    if msg.role == "user":
        text.append("you  ", style="bold cyan")
        text.append(msg.text)
        return text
    text.append("ai   ", style="bold red" if msg.error else "bold green")
    text.append(msg.text, style="red" if msg.error else "")
    if msg.sources:
        text.append("\n     notes: ", style="dim")
        text.append("  ".join(f"[{i}] {title}" for i, (_, title) in enumerate(msg.sources, 1)),
                    style="dim underline")
    return text


@dataclass
class AssistantOps:
    """What the window asks of the app (kept out of the widget so it is testable)."""
    submit: Callable[["AssistantScreen", str, str], None]
    open_source: Callable[[str], None]
    save_reply: Callable[[str, str], None]


class AssistantScreen(ModalScreen["str | None"]):
    """Dismisses with "history" (open the saved conversations), "new" (start a
    fresh chat) or None."""

    DEFAULT_CSS = """
    AssistantScreen { align: center middle; }
    #as-box { width: 100; height: 85%; background: $surface; border: solid $primary; padding: 1 2; }
    #as-header { text-style: bold; padding-bottom: 1; }
    #as-log { height: 1fr; border: round $primary-darken-2; padding: 0 1; }
    #as-log Static { margin-bottom: 1; }
    #as-input { margin-top: 1; border: solid $primary; }
    #as-hint { color: $text-muted; padding-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close (or stop a running answer)"),
        Binding("ctrl+x", "stop", "Stop the answer", priority=True, show=False),
        Binding("ctrl+r", "toggle_mode", "Research mode"),
        Binding("ctrl+o", "open_source", "Open a note the answer cites"),
        Binding("ctrl+s", "save_reply", "Save the last answer to your notes"),
        Binding("ctrl+t", "history", "Saved conversations"),
        Binding("ctrl+n", "new_chat", "New chat"),
    ]

    def __init__(self, messages: list[ChatMsg], mode: str, ops: AssistantOps) -> None:
        super().__init__()
        self.messages = messages
        self.mode = mode if mode in MODES else "chat"
        self._ops = ops
        self.busy = False
        self._live: Static | None = None     # the answer as it streams in (not yet a message)

    def check_action(self, action: str, parameters) -> bool | None:
        if action == "stop":
            return self.busy             # otherwise ctrl+x is the input's cut
        return super().check_action(action, parameters)

    # -- layout ----------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="as-box"):
            yield Label("", id="as-header")
            yield VerticalScroll(id="as-log")
            yield Input(id="as-input")
            yield Label("enter send · ctrl+x stop · ctrl+r research · ctrl+o open cited note · ctrl+s save answer "
                        "to notes · ctrl+t history · ctrl+n new chat · esc close", id="as-hint")

    def on_mount(self) -> None:
        log = self.query_one("#as-log", VerticalScroll)
        for msg in self.messages:
            log.mount(Static(render(msg)))
        log.scroll_end(animate=False)
        self._refresh_header()
        self.query_one("#as-input", Input).focus()

    def _refresh_header(self) -> None:
        mode = ("Research - answers from your notes/ research folder and the canon, citing them"
                if self.mode == "research" else "Assistant - about the open scene, or the project")
        self.query_one("#as-header", Label).update(Text(mode + ("   (working...)" if self.busy else "")))
        self.query_one("#as-input", Input).placeholder = (
            "Ask a question your research notes can answer..." if self.mode == "research"
            else "Ask about this scene or your project...")

    # -- messages ----------------------------------------------------------------------

    def add_message(self, msg: ChatMsg) -> None:
        self.messages.append(msg)
        log = self.query_one("#as-log", VerticalScroll)
        log.mount(Static(render(msg)))
        log.scroll_end(animate=False)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self._refresh_header()

    def show_stream(self, text: str) -> None:
        """The answer so far, typed in live under the conversation (not a message yet)."""
        log = self.query_one("#as-log", VerticalScroll)
        shown = Text()
        shown.append("ai   ", style="bold green")
        shown.append(text or "...", style="" if text else "dim")
        if self._live is None or not self._live.is_attached:
            self._live = Static(shown, classes="as-live")
            log.mount(self._live)
        else:
            self._live.update(shown)
        log.scroll_end(animate=False)

    def end_stream(self) -> None:
        if self._live is not None:
            self._live.remove()
            self._live = None

    def show_note(self, text: str) -> None:
        """A line in the log that is not part of the conversation (nothing is saved)."""
        log = self.query_one("#as-log", VerticalScroll)
        log.mount(Static(Text(text, style="dim italic")))
        log.scroll_end(animate=False)

    # -- input ---------------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        if self.busy:
            self.notify("Wait for the current answer", severity="warning")
            return
        event.input.value = ""
        self.add_message(ChatMsg("user", prompt))
        self._ops.submit(self, prompt, self.mode)

    def action_toggle_mode(self) -> None:
        self.mode = "chat" if self.mode == "research" else "research"
        self._refresh_header()

    def action_open_source(self) -> None:
        last = next((m for m in reversed(self.messages) if m.sources), None)
        if last is None:
            self.notify("No answer here cites a research note", severity="warning")
            return
        from .structurescreens import ChoiceScreen

        self.app.push_screen(
            ChoiceScreen("Open which note?", [(f"[{i}] {t}", sid)
                                              for i, (sid, t) in enumerate(last.sources, 1)]),
            lambda sid: sid and self._ops.open_source(sid))

    def action_save_reply(self) -> None:
        """Append the last answer (with the date and its prompt) to research/assistant-notes.md."""
        for i in range(len(self.messages) - 1, -1, -1):
            m = self.messages[i]
            if m.role == "assistant" and not m.error:
                prompt = next((x.text for x in reversed(self.messages[:i]) if x.role == "user"), "")
                self._ops.save_reply(prompt, m.text)
                return
        self.notify("There is no answer to save yet", severity="warning")

    def action_history(self) -> None:
        self.dismiss("history")

    def action_new_chat(self) -> None:
        self.dismiss("new")

    def action_stop(self) -> None:
        self.app.action_stop_ai()

    def action_close(self) -> None:
        if self.busy:                    # escape stops a running answer first; close when idle
            self.action_stop()
            return
        self.dismiss(None)


class ChatsScreen(ModalScreen["tuple[str, str] | None"]):
    """Saved conversations. Dismisses with (open | rename | delete, id), ("new", "") or None."""

    DEFAULT_CSS = """
    ChatsScreen { align: center middle; }
    #chats-box { width: 90; height: auto; max-height: 80%;
        background: $surface; border: solid $primary; padding: 1 2; }
    #chats-header { text-style: bold; padding-bottom: 1; }
    #chats-list { height: auto; max-height: 16; }
    #chats-hint { color: $text-muted; padding-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("r", "act('rename')", "Rename"),
        Binding("d", "act('delete')", "Delete"),
        Binding("n", "new", "New chat"),
    ]

    def __init__(self, chats: list[ChatInfo], current: str | None = None) -> None:
        super().__init__()
        self._chats = chats
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="chats-box"):
            yield Label("Saved conversations", id="chats-header")
            if self._chats:
                yield ListView(*[ListItem(Label(Text(self._row(c)))) for c in self._chats],
                               id="chats-list")
            else:
                yield Label("No saved conversations yet. A chat is saved after the assistant answers.",
                            id="chats-empty")
            yield Label("enter open · r rename · d delete · n new chat · esc close", id="chats-hint")

    def _row(self, c: ChatInfo) -> str:
        when = c.updated.replace("T", " ")[:16]
        return f"{c.title}  -  {when}  ({c.count} messages){'  - open now' if c.id == self._current else ''}"

    def on_mount(self) -> None:
        if self._chats:
            self.query_one("#chats-list", ListView).focus()

    def _selected(self) -> ChatInfo | None:
        if not self._chats:
            return None
        i = self.query_one("#chats-list", ListView).index
        return self._chats[i] if i is not None and 0 <= i < len(self._chats) else None

    def on_list_view_selected(self, event) -> None:
        self.action_act("open")

    def action_act(self, what: str) -> None:
        c = self._selected()
        if c is not None:
            self.dismiss((what, c.id))

    def action_new(self) -> None:
        self.dismiss(("new", ""))

    def action_cancel(self) -> None:
        self.dismiss(None)
