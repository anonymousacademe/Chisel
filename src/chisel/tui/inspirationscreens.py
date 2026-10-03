"""Inspiration images in the terminal: the prompt form and the picture list.

Terminals cannot show pictures well, so the images are saved under
``inspiration/`` and opened with the desktop's viewer only when chosen.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Label, ListItem, ListView, TextArea

from ..core.inspiration import Image


class InspirationPromptScreen(ModalScreen["tuple[str, str, bool] | None"]):
    """Describe a setting. ctrl+g generates (about $0.03), ctrl+d fills the box from
    the open scene (a cheap text call, then you edit it); esc cancels.
    Dismisses with ("describe" | "generate", text, pin) or None."""

    BINDINGS = [
        Binding("ctrl+g", "submit('generate')", "Generate", priority=True),
        Binding("ctrl+d", "submit('describe')", "Describe this scene", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    InspirationPromptScreen { align: center middle; }
    #insp-box { width: 84; height: auto; max-height: 90%; background: $surface; border: solid $primary; padding: 1 2; }
    #insp-title { text-style: bold; }
    #insp-input { height: 8; margin: 1 0; }
    #insp-pin { height: 1; border: none; padding: 0; }
    #insp-hint { color: $text-muted; padding-top: 1; }
    """

    def __init__(self, initial: str = "", scene_title: str = "") -> None:
        super().__init__()
        self._initial = initial
        self._scene_title = scene_title

    def compose(self) -> ComposeResult:
        with Vertical(id="insp-box"):
            yield Label("Inspiration image - describe the setting", id="insp-title")
            yield Label("Reference only: the picture is saved under inspiration/ and never goes into your prose.")
            yield TextArea(self._initial, id="insp-input", soft_wrap=True)
            pin = Checkbox(f"Pin to the open scene ({self._scene_title})" if self._scene_title
                           else "Pin to the open scene (no scene is open)", True, id="insp-pin",
                           disabled=not self._scene_title)
            yield pin
            hint = "ctrl+g generate (about $0.03)"
            if self._scene_title:
                hint += " · ctrl+d describe this scene"
            yield Label(hint + " · esc cancel", id="insp-hint")

    def on_mount(self) -> None:
        area = self.query_one("#insp-input", TextArea)
        area.focus()
        area.move_cursor(area.document.end)

    def action_submit(self, what: str) -> None:
        if what == "describe" and not self._scene_title:
            self.app.notify("Open a scene to describe it", severity="warning")
            return
        text = self.query_one("#insp-input", TextArea).text.strip()
        if what == "generate" and not text:
            self.app.notify("Describe the picture first (ctrl+d writes a description from the open scene)",
                            severity="warning")
            return
        self.dismiss((what, text, bool(self.query_one("#insp-pin", Checkbox).value)))

    def action_cancel(self) -> None:
        self.dismiss(None)


class InspirationListScreen(ModalScreen["tuple[str, str] | None"]):
    """The pictures of the open scene (a: all pictures). Dismisses with
    ("open" | "pin" | "trash", image id) or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("o", "act('open')", "Open"),
        Binding("p", "act('pin')", "Pin / unpin"),
        Binding("t", "act('trash')", "Move to Trash"),
        Binding("a", "toggle_all", "All / this scene"),
    ]

    DEFAULT_CSS = """
    InspirationListScreen { align: center middle; }
    #insp-list-box { width: 100; height: auto; max-height: 85%; background: $surface; border: solid $primary; padding: 1 2; }
    #insp-list-header { text-style: bold; padding-bottom: 1; }
    #insp-list { height: auto; max-height: 20; }
    #insp-list-hint { color: $text-muted; padding-top: 1; }
    """

    def __init__(self, scene_images: list[Image], all_images: list[Image], scene_title: str = "") -> None:
        super().__init__()
        self._scene_images = scene_images
        self._all_images = all_images
        self._scene_title = scene_title
        self._all = not scene_title
        self._shown: list[Image] = []

    @staticmethod
    def row(img: Image) -> Text:
        mark = "* " if img.pinned else "  "
        line = Text(mark + img.label)
        line.append(f"   {img.created[:16].replace('T', ' ')}", style="dim")
        if img.pinned:
            line.append("  pinned", style="bold")
        return line

    def compose(self) -> ComposeResult:
        with Vertical(id="insp-list-box"):
            yield Label("", id="insp-list-header")
            yield ListView(id="insp-list")
            yield Label("enter / o open · p pin or unpin · t move to Trash · a all or this scene · esc close",
                        id="insp-list-hint")

    def on_mount(self) -> None:
        self._fill()
        self.query_one("#insp-list", ListView).focus()

    def _fill(self) -> None:
        self._shown = list(self._all_images if self._all else self._scene_images)
        scope = "all pictures" if self._all else f"pictures for {self._scene_title}"
        self.query_one("#insp-list-header", Label).update(Text(f"Inspiration images - {scope} ({len(self._shown)})"))
        view = self.query_one("#insp-list", ListView)
        view.clear()
        if self._shown:
            view.extend([ListItem(Label(self.row(i))) for i in self._shown])
            view.index = 0
        else:
            view.extend([ListItem(Label("Nothing here yet. Action - Inspiration image makes one."))])

    def action_toggle_all(self) -> None:
        if self._scene_title:
            self._all = not self._all
            self._fill()

    def _current(self) -> Image | None:
        index = self.query_one("#insp-list", ListView).index
        return self._shown[index] if index is not None and 0 <= index < len(self._shown) else None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_act("open")      # enter

    def action_act(self, what: str) -> None:
        img = self._current()
        if img is not None:
            self.dismiss((what, img.id))

    def action_cancel(self) -> None:
        self.dismiss(None)
