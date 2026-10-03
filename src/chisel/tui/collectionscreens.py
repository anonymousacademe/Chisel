"""Terminal screen for collections: tick the open scene's collections, and
add, rename, recolour or delete them (SPEC: Notes around the manuscript)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from ..core.collections import Collection

RICH_COLOR = {"violet": "medium_purple", "amber": "yellow", "green": "green",
              "red": "red", "gray": "grey50"}


def row_text(c: Collection, member: bool | None, unit: str = "scene") -> Text:
    """``[x] * Name  (3 scenes)`` - the tick only when a scene is open."""
    n = len(c.scenes)
    text = Text()
    if member is not None:
        text.append("[x] " if member else "[ ] ")
    text.append("● ", style=RICH_COLOR.get(c.color, "grey50"))
    text.append(c.name, style="bold" if member else "")
    text.append(f"  {n} {unit}{'' if n == 1 else 's'}", style="dim")
    if not c.declared:
        text.append("  (not defined: recolour to keep)", style="dim italic")
    return text


class CollectionsScreen(ModalScreen["tuple[str, str] | None"]):
    """Dismisses with (action, collection name), ("new", "") or None. The app
    does the work and reopens this screen at the same row."""

    DEFAULT_CSS = """
    CollectionsScreen { align: center middle; }
    #coll-box { width: 76; height: auto; max-height: 80%;
        background: $surface; border: solid $primary; padding: 1 2; }
    #coll-header { text-style: bold; padding-bottom: 1; }
    #coll-list { height: auto; max-height: 16; }
    #coll-hint { color: $text-muted; padding-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("space", "act('toggle')", "Toggle"),
        Binding("n", "new", "New"),
        Binding("r", "act('rename')", "Rename"),
        Binding("c", "act('recolor')", "Recolour"),
        Binding("d", "act('delete')", "Delete"),
    ]

    def __init__(self, collections: list[Collection], members: set[str] | None,
                 scene_title: str | None, index: int = 0, unit: str = "scene") -> None:
        super().__init__()
        self._collections = collections
        self._members = members
        self._title = scene_title
        self._index = index
        self._unit = unit

    def compose(self) -> ComposeResult:
        with Vertical(id="coll-box"):
            yield Label(Text("Collections" + (f" - {self._title}" if self._title else "")),
                        id="coll-header")
            if self._collections:
                yield ListView(*[
                    ListItem(Label(row_text(
                        c, None if self._members is None else c.name in self._members,
                        self._unit)))
                    for c in self._collections], id="coll-list")
            else:
                yield Label("No collections yet. Press n to add one.", id="coll-empty")
            yield Label("space/enter tick · n new · r rename · c colour · d delete · esc close",
                        id="coll-hint")

    def on_mount(self) -> None:
        if self._collections:
            lv = self.query_one("#coll-list", ListView)
            lv.index = min(self._index, len(self._collections) - 1)
            lv.focus()

    def _current(self) -> int | None:
        if not self._collections:
            return None
        index = self.query_one("#coll-list", ListView).index
        return index if index is not None and 0 <= index < len(self._collections) else None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_act("toggle")  # enter

    def action_act(self, what: str) -> None:
        i = self._current()
        if i is None:
            return
        if what == "toggle" and self._members is None:
            self.notify("Open a scene to tick its collections", severity="warning")
            return
        self.dismiss((what, self._collections[i].name))

    def action_new(self) -> None:
        self.dismiss(("new", ""))

    def action_cancel(self) -> None:
        self.dismiss(None)

    @property
    def index(self) -> int:
        return self._current() or 0
