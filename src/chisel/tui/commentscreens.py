"""Terminal screen for the open scene's comments: list, jump, resolve, edit, delete."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from ..core.comments import Placed


def _short(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def row_text(p: Placed, line: int | None) -> Text:
    """``o line 12  "quoted text"  - the comment`` (detached ones say so)."""
    c = p.comment
    text = Text()
    text.append("done " if c.resolved else "open ", style="dim" if c.resolved else "bold")
    text.append("detached " if p.detached else f"line {line + 1} ", style="yellow" if p.detached else "dim")
    text.append(f"“{_short(c.quote, 32)}”", style="underline")
    text.append(f"  {_short(c.body, 48)}", style="dim" if c.resolved else "")
    return text


class CommentsScreen(ModalScreen["tuple[str, str] | None"]):
    """Dismisses with (action, comment id) or None; the app does the work and
    reopens this screen. Actions: jump, resolve, edit, delete."""

    DEFAULT_CSS = """
    CommentsScreen { align: center middle; }
    #cm-box { width: 100; height: auto; max-height: 80%;
        background: $surface; border: solid $primary; padding: 1 2; }
    #cm-header { text-style: bold; padding-bottom: 1; }
    #cm-list { height: auto; max-height: 16; }
    #cm-detail { padding-top: 1; height: auto; max-height: 8; }
    #cm-hint { color: $text-muted; padding-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("r", "act('resolve')", "Resolve"),
        Binding("e", "act('edit')", "Edit"),
        Binding("d", "act('delete')", "Delete"),
    ]

    def __init__(self, placed: list[Placed], lines: dict[str, int | None],
                 title: str, index: int = 0) -> None:
        super().__init__()
        self._placed = placed
        self._lines = lines
        self._title = title
        self._index = index

    def compose(self) -> ComposeResult:
        with Vertical(id="cm-box"):
            yield Label(Text(f"Comments - {self._title}"), id="cm-header")
            if self._placed:
                yield ListView(*[ListItem(Label(row_text(p, self._lines.get(p.comment.id))))
                                 for p in self._placed], id="cm-list")
                yield Label("", id="cm-detail")
            else:
                yield Label("No comments on this scene. Select text and use "
                            "'Add comment on selection'.", id="cm-empty")
            yield Label("enter jump to it · r resolve / reopen · e edit · d delete · esc close",
                        id="cm-hint")

    def on_mount(self) -> None:
        if self._placed:
            lv = self.query_one("#cm-list", ListView)
            lv.index = min(self._index, len(self._placed) - 1)
            lv.focus()
            self._show_detail()

    def _current(self) -> Placed | None:
        if not self._placed:
            return None
        i = self.query_one("#cm-list", ListView).index
        return self._placed[i] if i is not None and 0 <= i < len(self._placed) else None

    def _show_detail(self) -> None:
        p = self._current()
        if p is not None:
            self.query_one("#cm-detail", Label).update(Text(p.comment.body))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if self._placed:
            self._show_detail()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_act("jump")

    def action_act(self, what: str) -> None:
        p = self._current()
        if p is None:
            return
        if what == "jump" and p.detached:
            self.notify("This comment is detached: its passage is no longer in the text",
                        severity="warning")
            return
        self.dismiss((what, p.comment.id))

    def action_cancel(self) -> None:
        self.dismiss(None)
