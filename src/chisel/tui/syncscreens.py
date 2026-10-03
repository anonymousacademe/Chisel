"""Terminal prompt for a commit message (pre-filled, editable)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class MessagePrompt(ModalScreen["str | None"]):
    """One line of text, pre-filled. Enter dismisses with it (None if blank), esc with None."""

    def __init__(self, prompt: str, initial: str = "") -> None:
        super().__init__()
        self._prompt = prompt
        self._initial = initial

    def compose(self) -> ComposeResult:
        yield Label(Text(self._prompt))
        yield Input(value=self._initial, id="message-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def key_escape(self) -> None:
        self.dismiss(None)
