"""Small modals for manuscript structure: pick from a list, the Trash, and
the scene details form (POV / place / purpose / status / target)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import Input, Label, ListItem, ListView

from ..core import scenemeta
from ..core.structure import TrashItem


class ChoiceScreen(ModalScreen["object | None"]):
    """Pick one of *options* [(label, value)]; dismisses with the value or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, options: list[tuple[str, object]],
                 initial: object | None = None) -> None:
        super().__init__()
        self._prompt = prompt
        self._options = options
        self._initial = next((i for i, (_, v) in enumerate(options)
                              if initial is not None and v == initial), 0)

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-box"):
            yield Label(Text(self._prompt), id="choice-header")
            yield ListView(*[ListItem(Label(Text(label))) for label, _ in self._options],
                           id="choice-list")
            yield Label("enter choose · esc cancel", id="choice-hint")

    def on_mount(self) -> None:
        lv = self.query_one("#choice-list", ListView)
        lv.index = self._initial
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is not None and 0 <= index < len(self._options):
            self.dismiss(self._options[index][1])

    def action_cancel(self) -> None:
        self.dismiss(None)


class TrashScreen(ModalScreen["tuple[str, str] | None"]):
    """The Trash. Dismisses with ("restore" | "delete", name), ("empty", "")
    or None; the app confirms destructive choices and reopens the screen."""

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("r", "act('restore')", "Restore"),
        Binding("d", "act('delete')", "Delete forever"),
        Binding("e", "empty", "Empty trash"),
    ]

    def __init__(self, items: list[TrashItem]) -> None:
        super().__init__()
        self._items = items

    def compose(self) -> ComposeResult:
        with Vertical(id="trash-box"):
            yield Label("Trash", id="trash-header")
            if self._items:
                yield ListView(*[ListItem(Label(Text(self._row(i)))) for i in self._items],
                               id="trash-list")
            else:
                yield Label("The trash is empty.", id="trash-empty")
            yield Label("enter / r restore · d delete forever · e empty trash · esc close",
                        id="trash-hint")

    @staticmethod
    def _row(item: TrashItem) -> str:
        when = item.deleted.strftime("%Y-%m-%d %H:%M")
        if item.kind == "research":
            return f"{item.title}  -  {when}  (research note, from {item.original})"
        return f"{item.title}  -  {when}  (from {item.original.removeprefix('manuscript/')})"

    def on_mount(self) -> None:
        if self._items:
            self.query_one("#trash-list", ListView).focus()

    def _current(self) -> TrashItem | None:
        if not self._items:
            return None
        index = self.query_one("#trash-list", ListView).index
        return self._items[index] if index is not None and 0 <= index < len(self._items) else None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_act("restore")  # enter

    def action_act(self, what: str) -> None:
        item = self._current()
        if item is not None:
            self.dismiss((what, item.name))

    def action_empty(self) -> None:
        if self._items:
            self.dismiss(("empty", ""))

    def action_cancel(self) -> None:
        self.dismiss(None)


class DetailsScreen(ModalScreen["dict | None"]):
    """Edit a scene's details. Dismisses with the new field values
    ({"pov", "place", "purpose", "status", "target"}) or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel"),
                Binding("ctrl+s", "save", "Save")]

    FIELDS = (
        ("pov", "POV character"),
        ("place", "Place"),
        ("purpose", "Scene purpose"),
        ("status", "Status (idea / draft / revising / done, or your own)"),
        ("target", "Target words (a number, blank for none)"),
    )

    def __init__(self, text: str, characters: list[str], places: list[str]) -> None:
        super().__init__()
        self._current = scenemeta.details(text)
        self._suggest = {"pov": characters, "place": places,
                         "status": list(scenemeta.SUGGESTED_STATUS)}

    def compose(self) -> ComposeResult:
        with Vertical(id="details-box"):
            yield Label("Scene details", id="details-header")
            for key, label in self.FIELDS:
                yield Label(label, classes="details-label")
                value = self._current[key]
                suggester = (SuggestFromList(self._suggest[key], case_sensitive=False)
                             if key in self._suggest else None)
                yield Input("" if value is None else str(value), id=f"detail-{key}",
                            suggester=suggester)
            yield Label("tab next · right arrow accepts a suggestion · "
                        "enter/ctrl+s save · esc cancel", id="details-hint")

    def on_mount(self) -> None:
        self.query_one("#detail-pov", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_save()

    def action_save(self) -> None:
        values = {key: self.query_one(f"#detail-{key}", Input).value.strip()
                  for key, _ in self.FIELDS}
        target = values["target"].replace(",", "")
        if target and not target.isdigit():
            self.notify("Target must be a number of words", severity="warning")
            return
        self.dismiss(values)

    def action_cancel(self) -> None:
        self.dismiss(None)
