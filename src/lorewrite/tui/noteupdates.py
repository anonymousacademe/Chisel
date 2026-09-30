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
    """Review proposed canon additions to entity notes, fact by fact.

    Each new fact is shown in full (wrapped) and individually toggleable;
    existing canon is shown dimmed above its entity's group. Dismisses with
    CanonUpdates holding only the accepted facts, or None.

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
        # one row per fact: (update index, fact index)
        self._rows = [(u, f) for u, up in enumerate(updates)
                      for f in range(len(up.new_facts))]
        self._accepted: set[tuple[int, int]] = set(self._rows)

    def compose(self) -> ComposeResult:
        yield Label(
            f"Add {len(self._rows)} new fact(s) to {len(self._updates)} entity"
            " note(s)? Existing canon is never changed; notes change only if"
            " you press enter.",
            id="noteupdate-header",
        )
        yield ListView(id="updates")
        yield Label(
            "space: toggle fact · a: all · enter: apply · esc: cancel",
            id="noteupdate-hint",
        )

    def on_mount(self) -> None:
        lv = self.query_one("#updates", ListView)
        for i in range(len(self._rows)):
            lv.append(ListItem(Label(self._row_text(i))))
        if self._rows:
            lv.index = 0
        lv.focus()

    def _row_text(self, i: int) -> Text:
        u, f = self._rows[i]
        update = self._updates[u]
        mark = "x" if self._rows[i] in self._accepted else " "
        text = Text()
        if f == 0:  # group header: entity, dimmed existing canon, evidence
            text.append(f"{update.entity}\n", style="bold")
            if update.existing_canon:
                text.append(update.existing_canon + "\n", style="dim")
            if update.evidence:
                text.append(f"why: {update.evidence}\n", style="dim italic")
        text.append(f"[{mark}] {update.new_facts[f]}")
        return text

    def _refresh_row(self, i: int) -> None:
        lv = self.query_one("#updates", ListView)
        if 0 <= i < len(lv.children):
            lv.children[i].children[0].update(self._row_text(i))

    def action_toggle(self) -> None:
        index = self.query_one("#updates", ListView).index
        if index is None or index >= len(self._rows):
            return
        row = self._rows[index]
        if row in self._accepted:
            self._accepted.discard(row)
        else:
            self._accepted.add(row)
        self._refresh_row(index)

    def action_accept_all(self) -> None:
        self._accepted = set(self._rows)
        for i in range(len(self._rows)):
            self._refresh_row(i)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "updates":
            self.action_apply()

    def action_apply(self) -> None:
        from dataclasses import replace

        result = []
        for u, update in enumerate(self._updates):
            facts = tuple(fact for f, fact in enumerate(update.new_facts)
                          if (u, f) in self._accepted)
            if facts:
                result.append(replace(update, new_facts=facts))
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)
