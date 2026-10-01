"""Writing stats modal (Wave 4.1)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class StatsScreen(ModalScreen[None]):
    """Read-only summary: today, this session, streak, 30-day sparkline."""

    BINDINGS = [Binding("escape", "close", "Close"), Binding("enter", "close", "Close", show=False)]

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="stats-box"):
            yield Label("Session stats", id="stats-header")
            with VerticalScroll(id="stats-scroll"):
                yield Static(Text(self._text), id="stats-body")
            yield Label("esc close", id="stats-hint")

    def action_close(self) -> None:
        self.dismiss(None)
