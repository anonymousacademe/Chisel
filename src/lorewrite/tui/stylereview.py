"""Review modal for a proposed style guide: enter saves, esc discards."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Markdown


class StyleReviewScreen(ModalScreen[bool]):
    """Read-only scrollable preview of the proposed style.md.

    Dismisses True only on enter; nothing is written before that.
    """

    BINDINGS = [
        Binding("enter", "save", "Save"),
        Binding("escape", "discard", "Discard"),
    ]

    def __init__(self, markdown: str, replacing: bool) -> None:
        super().__init__()
        self._markdown = markdown
        self._replacing = replacing

    def compose(self) -> ComposeResult:
        header = "Proposed style guide (style.md)."
        if self._replacing:
            header += " Your current style.md will be replaced (kept as style.md.bak)."
        yield Label(header, id="style-header")
        with VerticalScroll(id="style-scroll"):
            yield Markdown(self._markdown, id="style-preview")
        yield Label("↑/↓ scroll · enter: save style.md · esc: discard",
                    id="style-hint")

    def on_mount(self) -> None:
        self.query_one("#style-scroll", VerticalScroll).focus()

    def action_save(self) -> None:
        self.dismiss(True)

    def action_discard(self) -> None:
        self.dismiss(False)
