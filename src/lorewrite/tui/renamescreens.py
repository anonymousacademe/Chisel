"""Terminal screens for "Rename everywhere": the form (new name, aliases, where
to look) and the preview, a list with a tick per occurrence (SPEC "Rename a
character"). Nothing is written by either; the app applies the ticked ids."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label, ListItem, ListView

from ..core.rename import Occurrence, RenamePlan


@dataclass
class RenameForm:
    new_name: str
    keep_old: bool
    aliases: dict[str, str]   # alias -> new spelling (unchanged ones included)
    scope: tuple[str, ...]


class RenameFormScreen(ModalScreen["RenameForm | None"]):
    """New name, "keep the old name as an alias", a new spelling per alias and
    which kinds of file to look in. enter in the name box continues."""

    DEFAULT_CSS = """
    RenameFormScreen { align: center middle; }
    #rename-box { width: 70; height: auto; max-height: 85%;
        background: $surface; border: solid $primary; padding: 1 2; }
    #rename-box Input { margin-bottom: 1; }
    #rename-box Checkbox { height: 1; border: none; padding: 0; }
    #rename-hint { color: $text-muted; padding-top: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, name: str, aliases: list[str]) -> None:
        super().__init__()
        self._name = name
        self._aliases = aliases

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="rename-box"):
            yield Label(f"Rename '{self._name}' everywhere", id="rename-title")
            yield Label("New name:")
            yield Input(self._name, id="rename-name")
            yield Checkbox(f"Keep '{self._name}' as an alias", True, id="rename-keep")
            if self._aliases:
                yield Label("\nAliases (change a spelling to rename it too):")
                for i, alias in enumerate(self._aliases):
                    yield Input(alias, id=f"rename-alias-{i}")
            yield Label("\nLook in (scenes and this note are always included):")
            yield Checkbox("Other notes", True, id="rename-entities")
            yield Checkbox("Notebook notes", False, id="rename-research")
            yield Checkbox("Comments", False, id="rename-comments")
            yield Label("enter (in the name box): preview changes · esc: cancel", id="rename-hint")

    def on_mount(self) -> None:
        self.query_one("#rename-name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        name = " ".join(self.query_one("#rename-name", Input).value.split())
        if not name:
            return
        aliases = {a: " ".join(self.query_one(f"#rename-alias-{i}", Input).value.split())
                   for i, a in enumerate(self._aliases)}
        scope = ["scenes"]
        for key, box in (("entities", "#rename-entities"), ("research", "#rename-research"),
                         ("comments", "#rename-comments")):
            if self.query_one(box, Checkbox).value:
                scope.append(key)
        self.dismiss(RenameForm(name, self.query_one("#rename-keep", Checkbox).value,
                                aliases, tuple(scope)))

    def action_cancel(self) -> None:
        self.dismiss(None)


class RenamePreviewScreen(ModalScreen["list[str] | None"]):
    """One row per occurrence. space toggles, a ticks all, n unticks all,
    enter applies the ticked ones, esc cancels (nothing has changed)."""

    DEFAULT_CSS = """
    RenamePreviewScreen { align: center middle; }
    #rp-header { width: 96; padding: 1 2; background: $surface; border: solid $primary; }
    #rp-list { width: 96; height: auto; max-height: 60%;
        background: $surface; border: solid $primary; padding: 0 1; }
    #rp-hint { width: 96; padding: 0 2; color: $text-muted; }
    """
    BINDINGS = [
        Binding("space", "toggle", "Toggle"),
        Binding("a", "all", "All"),
        Binding("n", "none", "None"),
        Binding("enter", "apply", "Apply"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, plan: RenamePlan, titles: dict[str, str]) -> None:
        super().__init__()
        self._plan = plan
        self._titles = titles
        self._occ: list[Occurrence] = list(plan.occurrences)
        self._ticked: set[str] = set(plan.default_ids())

    def compose(self) -> ComposeResult:
        n = len(self._occ)
        if n:
            yield Label(
                f"Rename '{self._plan.entity}' to '{self._plan.new_name}': {n} place"
                f"{'' if n == 1 else 's'} in {len(self._plan.files())} file(s)."
                " Untick what should stay; text inside an unaccepted AI draft starts"
                " unticked. Nothing changes until enter.", id="rp-header")
        else:
            yield Label(
                f"Nothing in the text uses '{self._plan.entity}'. Enter renames only"
                " the note itself.", id="rp-header")
        yield ListView(id="rp-list")
        yield Label("space: toggle · a: all · n: none · enter: apply · esc: cancel", id="rp-hint")

    def on_mount(self) -> None:
        lv = self.query_one("#rp-list", ListView)
        for i in range(len(self._occ)):
            lv.append(ListItem(Label(self._row(i))))
        if self._occ:
            lv.index = 0
        lv.focus()

    def _row(self, i: int) -> Text:
        o = self._occ[i]
        text = Text("[x] " if o.id in self._ticked else "[ ] ")
        text.append(f"{self._titles.get(o.file, o.file)}:{o.line}  ", style="dim")
        text.append(o.pre.lstrip())
        text.append(o.before, style="strike red")
        text.append(" → ")
        text.append(o.after, style="bold green")
        text.append(o.post.rstrip())
        if o.in_draft:
            text.append("  (in an AI draft)", style="dim italic")
        return text

    def _refresh(self, i: int) -> None:
        lv = self.query_one("#rp-list", ListView)
        if 0 <= i < len(lv.children):
            lv.children[i].children[0].update(self._row(i))

    def action_toggle(self) -> None:
        i = self.query_one("#rp-list", ListView).index
        if i is None:
            return
        self._ticked ^= {self._occ[i].id}
        self._refresh(i)

    def action_all(self) -> None:
        self._ticked = {o.id for o in self._occ}
        for i in range(len(self._occ)):
            self._refresh(i)

    def action_none(self) -> None:
        self._ticked = set()
        for i in range(len(self._occ)):
            self._refresh(i)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_apply()  # ListView swallows enter

    def action_apply(self) -> None:
        self.dismiss([o.id for o in self._occ if o.id in self._ticked])

    def action_cancel(self) -> None:
        self.dismiss(None)
