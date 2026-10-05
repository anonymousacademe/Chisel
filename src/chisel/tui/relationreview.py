"""Review modal for AI relationship suggestions: accept/reject before anything changes."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from ..ai.relationships import Suggestion


class RelationshipReviewScreen(ModalScreen[list[Suggestion] | None]):
    """Lists AI-proposed relationships for the open note. Nothing is applied
    until enter.

    space: toggle current · a: accept all · enter: apply accepted · esc: cancel
    """

    BINDINGS = [
        Binding("space", "toggle", "Toggle"),
        Binding("a", "accept_all", "All"),
        Binding("enter", "apply", "Apply"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, suggestions: list[Suggestion]) -> None:
        super().__init__()
        self._suggestions = suggestions
        self._accepted: set[int] = set(range(len(suggestions)))  # default: all on

    def compose(self) -> ComposeResult:
        yield Label(
            f"Add {len(self._suggestions)} relationship(s) to this note? Your"
            " other notes are never changed; nothing happens until you press enter.",
            id="rel-review-header",
        )
        yield ListView(id="rel-suggestions")
        yield Label(
            "space: toggle · a: all · enter: apply · esc: cancel",
            id="rel-review-hint",
        )

    def on_mount(self) -> None:
        lv = self.query_one("#rel-suggestions", ListView)
        lv.clear()
        for i, s in enumerate(self._suggestions):
            lv.append(ListItem(Label(self._row_text(i))))
        if self._suggestions:
            lv.index = 0
        lv.focus()

    def _row_text(self, i: int) -> Text:
        s = self._suggestions[i]
        mark = "x" if i in self._accepted else " "
        row = f"{s.label} — [[{s.target}]]" if s.label else f"[[{s.target}]]"
        return Text(f"[{mark}] {row}")

    def _refresh_row(self, i: int) -> None:
        lv = self.query_one("#rel-suggestions", ListView)
        if 0 <= i < len(lv.children):
            lv.children[i].children[0].update(self._row_text(i))

    def action_toggle(self) -> None:
        index = self.query_one("#rel-suggestions", ListView).index
        if index is None:
            return
        if index in self._accepted:
            self._accepted.discard(index)
        else:
            self._accepted.add(index)
        self._refresh_row(index)

    def action_accept_all(self) -> None:
        self._accepted = set(range(len(self._suggestions)))
        for i in range(len(self._suggestions)):
            self._refresh_row(i)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # ListView consumes enter itself; treat selection as apply
        if event.list_view.id == "rel-suggestions":
            self.action_apply()

    def action_apply(self) -> None:
        accepted = [s for i, s in enumerate(self._suggestions)
                    if i in self._accepted]
        self.dismiss(accepted)

    def action_cancel(self) -> None:
        self.dismiss(None)
