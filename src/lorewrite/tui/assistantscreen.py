"""The assistant in the terminal: a small chat window over ``ai.writing.ask``
(about the open scene or the project) and, in research mode, over
``ai.writing.research_answer`` (answers from your research notes and the canon,
citing the notes used). Suggest-only: nothing here edits the manuscript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

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


class AssistantScreen(ModalScreen[None]):
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
        Binding("escape", "close", "Close"),
        Binding("ctrl+r", "toggle_mode", "Research mode"),
        Binding("ctrl+o", "open_source", "Open a note the answer cites"),
    ]

    def __init__(self, messages: list[ChatMsg], mode: str,
                 on_submit: Callable[["AssistantScreen", str, str], None],
                 on_open_source: Callable[[str], None]) -> None:
        super().__init__()
        self.messages = messages
        self.mode = mode if mode in MODES else "chat"
        self._on_submit = on_submit
        self._on_open_source = on_open_source
        self.busy = False

    # -- layout ----------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="as-box"):
            yield Label("", id="as-header")
            yield VerticalScroll(id="as-log")
            yield Input(id="as-input")
            yield Label("enter send · ctrl+r research mode · ctrl+o open a cited note · esc close",
                        id="as-hint")

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
        self._on_submit(self, prompt, self.mode)

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
            lambda sid: sid and self._on_open_source(sid))

    def action_close(self) -> None:
        self.dismiss(None)
