"""Launch screen: resume a recent project, open a folder, or start a new one."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from .. import __version__
from ..core import entities as ent
from ..core.project import Project
from ..core.recents import Recent, load_recents, remove_recent


class PathPrompt(ModalScreen[Path | None]):
    """Prompt for a project folder path."""

    def __init__(self, prompt: str, initial: str = "") -> None:
        super().__init__()
        self._prompt = prompt
        self._initial = initial

    def compose(self) -> ComposeResult:
        yield Label(self._prompt)
        yield Input(value=self._initial, id="path-input")

    def on_mount(self) -> None:
        inp = self.query_one(Input)
        inp.focus()
        inp.cursor_position = len(inp.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(Path(value).expanduser() if value else None)

    def key_escape(self) -> None:
        self.dismiss(None)


class NewProjectPrompt(ModalScreen[tuple[str, Path] | None]):
    """Prompt for a new project's title and location."""

    def __init__(self, default_parent: Path) -> None:
        super().__init__()
        self._default_parent = default_parent

    def compose(self) -> ComposeResult:
        yield Label("New project")
        yield Input(placeholder="Title, e.g. The Salt Road", id="title-input")
        yield Input(placeholder="Folder", id="path-input")

    def on_mount(self) -> None:
        self.query_one("#title-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "title-input":
            path_input = self.query_one("#path-input", Input)
            slug = ent.slugify(event.value) if event.value.strip() else ""
            path_input.value = str(self._default_parent / slug) if slug else ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "title-input":
            self.query_one("#path-input", Input).focus()
            return
        self._submit()

    def key_enter(self) -> None:
        self._submit()

    def _submit(self) -> None:
        title = self.query_one("#title-input", Input).value.strip()
        raw = self.query_one("#path-input", Input).value.strip()
        if not title or not raw:
            self.app.notify("Title and folder are both required", severity="error")
            return
        self.dismiss((title, Path(raw).expanduser()))

    def key_escape(self) -> None:
        self.dismiss(None)


class LaunchScreen(ModalScreen[Project | None]):
    """Start here: pick a recent project, open a folder, or create new."""

    BINDINGS = [
        Binding("o", "open_folder", "Open…"),
        Binding("n", "new_project", "New…"),
        Binding("s", "settings", "Settings"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._recents: list[Recent] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="launch"):
            yield Static(f"lorewrite v{__version__}", id="launch-title")
            yield Label("Recent projects", classes="launch-heading")
            yield ListView(id="recents")
            yield Label(
                "enter: resume   o: open folder…   n: new project…"
                "   s: settings   q: quit",
                id="launch-hint",
            )

    def on_mount(self) -> None:
        self._recents = [r for r in load_recents() if Project.is_project(r.path)]
        lv = self.query_one("#recents", ListView)
        lv.clear()
        for recent in self._recents:
            lv.append(ListItem(Label(Text(f"{recent.title}  —  {recent.path}"))))
        if self._recents:
            lv.index = 0  # first recent highlighted: enter resumes instantly
            lv.focus()
        else:
            lv.append(ListItem(Label(Text("(none yet — press n to start a novel)"))))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or not (0 <= index < len(self._recents)):
            return
        recent = self._recents[index]
        if not Project.is_project(recent.path):
            remove_recent(recent.path)
            self.app.notify(f"{recent.path} is no longer a project",
                            severity="error")
            self.on_mount()
            return
        self.dismiss(Project.open(recent.path))

    def action_open_folder(self) -> None:
        def _open(path: Path | None) -> None:
            if path is None:
                return
            if Project.is_project(path):
                self.dismiss(Project.open(path))
            else:
                self.app.notify(f"No lorewrite project in {path}",
                                severity="error")

        self.app.push_screen(PathPrompt("Project folder:"), _open)

    def action_new_project(self) -> None:
        default_parent = Path.home() / "novels"

        def _create(result: tuple[str, Path] | None) -> None:
            if result is None:
                return
            title, path = result
            if Project.is_project(path):
                self.dismiss(Project.open(path))
                return
            try:
                self.dismiss(Project.create(path, title=title))
            except OSError as exc:
                self.app.notify(f"Could not create project: {exc}",
                                severity="error")

        self.app.push_screen(NewProjectPrompt(default_parent), _create)

    def action_quit_app(self) -> None:
        self.dismiss(None)

    def action_settings(self) -> None:
        from .settingscreen import SettingsScreen

        self.app.push_screen(SettingsScreen(None))
