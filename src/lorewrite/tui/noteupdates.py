"""Story-bible update review: accept/reject AI-proposed canon updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:  # avoid a hard import while ai/continuity.py is in flight
    from ..ai.continuity import CanonUpdate


class NoteUpdateScreen(ModalScreen[list | None]):
    """Review proposed canon updates to entity notes.

    space: toggle · a: all · enter: apply accepted · esc: cancel
    """

    BINDINGS = [
        Binding("space", "toggle", "Toggle"),
        Binding("a", "accept_all", "All"),
        Binding("enter", "apply", "Apply"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, updates: list[CanonUpdate]) -> None:
        super().__init__()
        self._updates = updates
        self._accepted: set[int] = set(range(len(updates)))

    def compose(self) -> ComposeResult:
        yield Label(
            f"Update {len(self._updates)} entity note(s) with new canon?"
            " Notes change only if you press enter.",
            id="noteupdate-header",
        )
        yield ListView(id="updates")
        yield Label(
            "space: toggle · a: all · enter: apply · esc: cancel",
            id="noteupdate-hint",
        )

    def on_mount(self) -> None:
        lv = self.query_one("#updates", ListView)
        for i, _ in enumerate(self._updates):
            lv.append(ListItem(Label(self._row_text(i))))
        if self._updates:
            lv.index = 0
        lv.focus()

    def _row_text(self, i: int) -> Text:
        u = self._updates[i]
        mark = "x" if i in self._accepted else " "
        canon = " ".join(u.new_canon.split())
        if len(canon) > 80:
            canon = canon[:77] + "..."
        return Text(
            f"[{mark}] {u.entity}\n"
            f"    {canon}\n"
            f"    why: {u.justification}"
        )

    def _refresh_row(self, i: int) -> None:
        lv = self.query_one("#updates", ListView)
        if 0 <= i < len(lv.children):
            lv.children[i].children[0].update(self._row_text(i))

    def action_toggle(self) -> None:
        index = self.query_one("#updates", ListView).index
        if index is None:
            return
        if index in self._accepted:
            self._accepted.discard(index)
        else:
            self._accepted.add(index)
        self._refresh_row(index)

    def action_accept_all(self) -> None:
        self._accepted = set(range(len(self._updates)))
        for i in range(len(self._updates)):
            self._refresh_row(i)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "updates":
            self.action_apply()

    def action_apply(self) -> None:
        self.dismiss([u for i, u in enumerate(self._updates)
                      if i in self._accepted])

    def action_cancel(self) -> None:
        self.dismiss(None)
