"""Brainstorm (Wave 4.3): the "unstuck" ideas in a list, each with Draft from this
and Save to notes."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView


class BrainstormScreen(ModalScreen["tuple[str, str] | None"]):
    """Dismisses with ("draft" | "save", idea) or None. The app does the work and,
    for *save*, reopens the list so several ideas can be kept."""

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("d", "act('draft')", "Draft from this"),
        Binding("s", "act('save')", "Save to notes"),
    ]

    def __init__(self, ideas: list[str]) -> None:
        super().__init__()
        self._ideas = ideas

    def compose(self) -> ComposeResult:
        with Vertical(id="idea-box"):
            yield Label("Brainstorm - ideas to get unstuck", id="idea-header")
            yield ListView(*[ListItem(Label(Text(f"{i}. {idea}"))) for i, idea in enumerate(self._ideas, 1)],
                           id="idea-list")
            yield Label("enter / d draft from this · s save to notes · esc close", id="idea-hint")

    def on_mount(self) -> None:
        self.query_one("#idea-list", ListView).focus()

    def _current(self) -> str | None:
        index = self.query_one("#idea-list", ListView).index
        return self._ideas[index] if index is not None and 0 <= index < len(self._ideas) else None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_act("draft")      # enter

    def action_act(self, what: str) -> None:
        idea = self._current()
        if idea is not None:
            self.dismiss((what, idea))

    def action_cancel(self) -> None:
        self.dismiss(None)
