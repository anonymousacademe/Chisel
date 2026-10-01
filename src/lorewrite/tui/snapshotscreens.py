"""Terminal screens for snapshots: the list, the compare view and a label prompt."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from ..core.snapshots import Segment, Snapshot, ago, diff_stats

LABEL_NAMES = {
    "auto": "automatic (first edit of the day)",
    "before-restore": "before a restore",
    "before-accept-all": "before accepting all AI drafts",
    "before-reject-all": "before rejecting all AI drafts",
}


def label_text(label: str) -> str:
    if not label:
        return "snapshot"
    if label in LABEL_NAMES:
        return LABEL_NAMES[label]
    if label.startswith("end-of-draft-"):
        return f"end of draft {label.removeprefix('end-of-draft-')}"
    return label


def delta_text(n: int) -> str:
    return f"+{n}" if n > 0 else f"-{-n}" if n < 0 else "+-0"


def unified(segments: list[Segment]) -> Text:
    """One stream: removed words struck through in red, added words underlined
    in green (style, not brackets, so the prose stays readable)."""
    out = Text()
    for s in segments:
        if s.op == "equal":
            out.append(s.new)
            continue
        if s.old:
            out.append(s.old, style="red strike")
        if s.new:
            out.append(s.new, style="green underline")
    return out


class LabelPrompt(ModalScreen["str | None"]):
    """Optional label. Enter dismisses with the text (possibly empty); esc with None."""

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        yield Label(Text(self._prompt))
        yield Input(id="label-input", placeholder="label (optional) - enter to snapshot")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def key_escape(self) -> None:
        self.dismiss(None)


class SnapshotsScreen(ModalScreen["tuple[str, str] | None"]):
    """Snapshots of the open scene. Dismisses with ("compare" | "restore" |
    "delete", name), ("new", ""), ("all", "") or None; the app does the work
    (confirming the destructive ones) and reopens this screen."""

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("c", "act('compare')", "Compare"),
        Binding("r", "act('restore')", "Restore"),
        Binding("d", "act('delete')", "Delete"),
        Binding("n", "plain('new')", "New"),
        Binding("a", "plain('all')", "All scenes"),
    ]

    def __init__(self, title: str, items: list[Snapshot], words_now: int) -> None:
        super().__init__()
        self._title = title
        self._items = items
        self._now = words_now

    def compose(self) -> ComposeResult:
        with Vertical(id="snap-box"):
            yield Label(Text(f"Snapshots: {self._title}"), id="snap-header")
            if self._items:
                yield ListView(*[ListItem(Label(Text(self._row(s)))) for s in self._items],
                               id="snap-list")
            else:
                yield Label("No snapshots of this scene yet.", id="snap-empty")
            yield Label("enter/c compare · r restore · d delete · n new snapshot · "
                        "a snapshot all scenes · esc close", id="snap-hint")

    def _row(self, s: Snapshot) -> str:
        when = s.when.strftime("%Y-%m-%d %H:%M")
        return (f"{label_text(s.label)}  -  {when} ({ago(s.when)})  -  "
                f"{s.words} words ({delta_text(self._now - s.words)} now)")

    def on_mount(self) -> None:
        if self._items:
            self.query_one("#snap-list", ListView).focus()

    def _current(self) -> Snapshot | None:
        if not self._items:
            return None
        i = self.query_one("#snap-list", ListView).index
        return self._items[i] if i is not None and 0 <= i < len(self._items) else None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_act("compare")  # enter

    def action_act(self, what: str) -> None:
        s = self._current()
        if s is not None:
            self.dismiss((what, s.name))

    def action_plain(self, what: str) -> None:
        self.dismiss((what, ""))

    def action_cancel(self) -> None:
        self.dismiss(None)


class CompareScreen(ModalScreen["str | None"]):
    """Unified word-level diff, snapshot -> now. Dismisses "restore" or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
        Binding("r", "restore", "Restore"),
    ]

    def __init__(self, title: str, segments: list[Segment]) -> None:
        super().__init__()
        self._title = title
        self._segments = segments

    def compose(self) -> ComposeResult:
        added, removed = diff_stats(self._segments)
        same = all(s.op == "equal" for s in self._segments)
        summary = ("The text is the same as this snapshot." if same
                   else f"{added} words added (green, underlined), "
                        f"{removed} removed (red, struck through) since the snapshot.")
        with Vertical(id="compare-box"):
            yield Label(Text(f"Compare: {self._title}"), id="compare-header")
            yield Label(Text(summary), id="compare-summary")
            with VerticalScroll(id="compare-scroll"):
                yield Static(unified(self._segments), id="compare-text")
            yield Label("r restore this snapshot · esc back", id="compare-hint")

    def action_restore(self) -> None:
        self.dismiss("restore")

    def action_cancel(self) -> None:
        self.dismiss(None)
