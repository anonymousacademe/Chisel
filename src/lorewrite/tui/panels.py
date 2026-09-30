"""Right-hand panel: entity preview and backlinks."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Markdown

from ..core.index import Backlink


class BacklinkSelected(Message):
    """User picked a backlink: open source file at row."""

    def __init__(self, source: str, row: int) -> None:
        super().__init__()
        self.source = source
        self.row = row


class EntityPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="panel")
        self._backlinks: list[Backlink] = []

    def compose(self):
        yield Label("Entity", classes="panel-heading", id="entity-title")
        yield Markdown(
            "*Put the cursor on a character or place name to inspect it."
            " Its note and every scene mentioning it shows up here.*",
            id="entity-body",
        )
        yield Label("Backlinks", classes="panel-heading")
        yield ListView(id="backlinks")

    def show_entity(self, title: str, body_markdown: str) -> None:
        self.query_one("#entity-title", Label).update(title)
        self.query_one("#entity-body", Markdown).update(
            body_markdown or "*(empty note — ctrl+j to open and write it)*"
        )

    def set_backlinks(self, backlinks: list[Backlink]) -> None:
        self._backlinks = backlinks
        lv = self.query_one("#backlinks", ListView)
        lv.clear()
        for bl in backlinks:
            context = bl.line.strip()
            if len(context) > 60:
                context = context[:57] + "..."
            # Text(): backlink lines contain [[...]] which Rich reads as markup
            lv.append(ListItem(Label(Text(f"{bl.source}:{bl.row + 1}  {context}"))))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "backlinks":
            return
        index = event.list_view.index
        if index is not None and 0 <= index < len(self._backlinks):
            bl = self._backlinks[index]
            self.post_message(BacklinkSelected(bl.source, bl.row))
