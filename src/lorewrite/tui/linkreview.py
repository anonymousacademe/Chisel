"""Review modal for AI link suggestions: accept/reject before anything changes."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from ..ai.links import Suggestion
from ..core.links import offset_to_rowcol


class LinkReviewScreen(ModalScreen[list[Suggestion] | None]):
    """Lists AI-proposed links. Nothing is applied until enter.

    space: toggle current · a: accept all · enter: apply accepted · esc: cancel
    """

    BINDINGS = [
        Binding("space", "toggle", "Toggle"),
        Binding("a", "accept_all", "All"),
        Binding("enter", "apply", "Apply"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, suggestions: list[Suggestion], scene_text: str) -> None:
        super().__init__()
        self._suggestions = suggestions
        self._scene_text = scene_text
        self._accepted: set[int] = set(range(len(suggestions)))  # default: all on

    def compose(self) -> ComposeResult:
        yield Label(
            f"Link {len(self._suggestions)} mention(s)? Nothing changes"
            " until you press enter.",
            id="review-header",
        )
        yield ListView(id="suggestions")
        yield Label(
            "space: toggle · a: all · enter: apply · esc: cancel",
            id="review-hint",
        )

    def on_mount(self) -> None:
        lv = self.query_one("#suggestions", ListView)
        lv.clear()
        for i, s in enumerate(self._suggestions):
            lv.append(ListItem(Label(self._row_text(i))))
        if self._suggestions:
            lv.index = 0
        lv.focus()

    def _row_text(self, i: int) -> Text:
        s = self._suggestions[i]
        row, _ = offset_to_rowcol(self._scene_text, s.start)
        mark = "x" if i in self._accepted else " "
        return Text(f"[{mark}] {s.surface} → {s.entity}   (line {row + 1})")

    def _refresh_row(self, i: int) -> None:
        lv = self.query_one("#suggestions", ListView)
        if 0 <= i < len(lv.children):
            lv.children[i].children[0].update(self._row_text(i))

    def action_toggle(self) -> None:
        index = self.query_one("#suggestions", ListView).index
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
        if event.list_view.id == "suggestions":
            self.action_apply()

    def action_apply(self) -> None:
        accepted = [s for i, s in enumerate(self._suggestions)
                    if i in self._accepted]
        self.dismiss(accepted)

    def action_cancel(self) -> None:
        self.dismiss(None)
