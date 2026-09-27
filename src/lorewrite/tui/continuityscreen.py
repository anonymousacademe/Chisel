"""Continuity review modal: list contradictions, waive, jump to evidence."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from ..core.continuity import Contradiction

SEVERITY_MARKS = {"error": "!", "warning": "?", "note": "-"}


class WaiveToggled(Message):
    """A contradiction was (un)waived. The app persists immediately."""

    def __init__(self, waiver_key: str, waived: bool) -> None:
        super().__init__()
        self.waiver_key = waiver_key
        self.waived = waived


class JumpToContradiction(Message):
    """Enter on a row: open the scene at the evidence line."""

    def __init__(self, contradiction: Contradiction) -> None:
        super().__init__()
        self.contradiction = contradiction


class ContinuityScreen(ModalScreen[None]):
    """Review continuity flags. space: waive · enter: jump to line · esc: done"""

    BINDINGS = [
        Binding("space", "toggle_waive", "Waive"),
        Binding("enter", "jump", "Jump to line"),
        Binding("escape", "done", "Done"),
    ]

    def __init__(self, contradictions: list[Contradiction]) -> None:
        super().__init__()
        self._contradictions = contradictions
        self._waived: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Label(
            f"{len(self._contradictions)} continuity issue(s) — your call"
            " on every one.",
            id="continuity-header",
        )
        yield ListView(id="contradictions")
        yield Label(
            "space: waive (won't be reported again) · enter: jump to line"
            " · esc: done",
            id="continuity-hint",
        )

    def on_mount(self) -> None:
        lv = self.query_one("#contradictions", ListView)
        for i, _ in enumerate(self._contradictions):
            lv.append(ListItem(Label(self._row_text(i))))
        if self._contradictions:
            lv.index = 0
        lv.focus()

    def _row_text(self, i: int) -> Text:
        c = self._contradictions[i]
        mark = SEVERITY_MARKS.get(c.severity, "-")
        waived = " (waived)" if c.waiver_key() in self._waived else ""
        where = f" line {c.row + 1}" if c.row is not None else ""
        evidence = " ".join(c.evidence.split())
        if len(evidence) > 70:
            evidence = evidence[:67] + "..."
        return Text(
            f"[{mark}] {c.type} — {c.entity}{where}{waived}\n"
            f"    {evidence}\n"
            f"    fix: {c.suggested_fix}"
        )

    def _refresh_row(self, i: int) -> None:
        lv = self.query_one("#contradictions", ListView)
        if 0 <= i < len(lv.children):
            lv.children[i].children[0].update(self._row_text(i))

    def action_toggle_waive(self) -> None:
        index = self.query_one("#contradictions", ListView).index
        if index is None:
            return
        key = self._contradictions[index].waiver_key()
        if key in self._waived:
            self._waived.discard(key)
            self.post_message(WaiveToggled(key, False))
        else:
            self._waived.add(key)
            self.post_message(WaiveToggled(key, True))
        self._refresh_row(index)

    def action_jump(self) -> None:
        index = self.query_one("#contradictions", ListView).index
        if index is not None:
            self.post_message(
                JumpToContradiction(self._contradictions[index])
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "contradictions":
            self.action_jump()

    def action_done(self) -> None:
        self.dismiss(None)
