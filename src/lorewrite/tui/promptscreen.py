"""Prompt window for AI drafting: a small multi-line instruction box."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea


class PromptScreen(ModalScreen[str | None]):
    """Multi-line instruction prompt. ctrl+g submits (the key that opened it —
    enter inserts a newline, ctrl+enter never reaches terminals); esc cancels.
    Dismisses with the trimmed instruction, or None.
    """

    BINDINGS = [
        Binding("ctrl+g", "submit", "Generate", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, initial: str = "") -> None:
        super().__init__()
        self._title = title
        self._initial = initial

    def compose(self) -> ComposeResult:
        yield Label(Text(self._title), id="prompt-title")
        yield TextArea(self._initial, id="prompt-input", soft_wrap=True)
        yield Label("ctrl+g: generate · esc: cancel", id="prompt-hint")

    def on_mount(self) -> None:
        area = self.query_one("#prompt-input", TextArea)
        area.focus()
        area.move_cursor(area.document.end)

    def action_submit(self) -> None:
        value = self.query_one("#prompt-input", TextArea).text.strip()
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
