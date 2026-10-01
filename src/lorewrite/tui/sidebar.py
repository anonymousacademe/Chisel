"""Sidebar: filter box, scene list, and entity list."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, Label, ListItem, ListView


class OpenFile(Message):
    """Request to open a file in the editor."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path


class Sidebar(Vertical):
    def __init__(self) -> None:
        super().__init__(id="sidebar")
        #: rows: (kind, title, path) with kind "scene", "part" or "header"
        self._scenes: list[tuple[str, str, Path | None]] = []
        self._entities: list[tuple[str, Path]] = []
        self._scene_paths: list[Path | None] = []  # None for header rows
        self._unit = "scene"
        self._entity_paths: list[Path] = []

    def compose(self):
        yield Input(placeholder="filter…", id="filter")
        yield Label("Scenes", classes="sidebar-heading", id="scenes-heading")
        yield ListView(id="scenes")
        yield Label("Entities", classes="sidebar-heading")
        yield ListView(id="entities")

    # -- data -----------------------------------------------------------------

    def set_scenes(self, rows: list[tuple[str, str, Path | None]],
                   unit: str = "scene") -> None:
        """*rows*: ("scene", title, path), ("part", title, folder) and
        ("header", title, None). Parts and headers are not openable."""
        self._scenes = rows
        if unit != self._unit:
            self._unit = unit
            try:
                self.query_one("#scenes-heading", Label).update(f"{unit.capitalize()}s")
            except Exception:
                pass
        self._render_lists()

    def set_entities(self, entities: list[tuple[str, Path]]) -> None:
        self._entities = entities
        self._render_lists()

    def _render_lists(self) -> None:
        try:
            query = self.query_one("#filter", Input).value.strip().casefold()
        except Exception:
            query = ""

        def matches(title: str) -> bool:
            return not query or query in title.casefold()

        entities = [(t, p) for t, p in self._entities if matches(t)]

        # with a filter, only matching scenes (and the part headers above them)
        rows: list[tuple[str, str, Path | None]] = []
        pending: tuple[str, str, Path | None] | None = None
        for kind, title, path in self._scenes:
            if kind == "scene":
                if matches(title):
                    if pending is not None:
                        rows.append(pending)
                        pending = None
                    rows.append((kind, title, path))
            elif not query:
                rows.append((kind, title, path))
            else:
                pending = (kind, title, path)

        self._scene_paths = [p if k == "scene" else None for k, _, p in rows]
        scene_lv = self.query_one("#scenes", ListView)
        scene_lv.clear()
        for kind, title, _ in rows:
            # Text(): titles may contain Rich markup chars like [
            if kind == "scene":
                scene_lv.append(ListItem(Label(Text(title))))
            else:
                scene_lv.append(ListItem(Label(Text(title.upper(), style="bold dim")),
                                         classes="part-header"))
        if not rows and not self._scenes:
            scene_lv.append(
                ListItem(Label(Text("ctrl+n — your first scene")),
                         classes="empty-hint")
            )

        self._entity_paths = [p for _, p in entities]
        entity_lv = self.query_one("#entities", ListView)
        entity_lv.clear()
        for name, _ in entities:
            entity_lv.append(ListItem(Label(Text(name))))
        if not entities and not self._entities:
            entity_lv.append(
                ListItem(Label(Text("select a name, then ctrl+j")),
                         classes="empty-hint")
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            self._render_lists()

    # -- selection --------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "scenes":
            paths = self._scene_paths
        elif event.list_view.id == "entities":
            paths = self._entity_paths
        else:
            return
        index = event.list_view.index
        if index is not None and 0 <= index < len(paths) and paths[index] is not None:
            self.post_message(OpenFile(paths[index]))
