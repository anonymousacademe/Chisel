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
        self._scenes: list[tuple[str, Path]] = []
        self._entities: list[tuple[str, Path]] = []
        self._scene_paths: list[Path] = []
        self._entity_paths: list[Path] = []

    def compose(self):
        yield Input(placeholder="filter…", id="filter")
        yield Label("Scenes", classes="sidebar-heading")
        yield ListView(id="scenes")
        yield Label("Entities", classes="sidebar-heading")
        yield ListView(id="entities")

    # -- data -----------------------------------------------------------------

    def set_scenes(self, scenes: list[tuple[str, Path]]) -> None:
        self._scenes = scenes
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

        scenes = [(t, p) for t, p in self._scenes if matches(t)]
        entities = [(t, p) for t, p in self._entities if matches(t)]

        self._scene_paths = [p for _, p in scenes]
        scene_lv = self.query_one("#scenes", ListView)
        scene_lv.clear()
        for title, _ in scenes:
            # Text(): titles may contain Rich markup chars like [
            scene_lv.append(ListItem(Label(Text(title))))
        if not scenes and not self._scenes:
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
                ListItem(Label(Text("type [[Name]], then ctrl+j")),
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
        if index is not None and 0 <= index < len(paths):
            self.post_message(OpenFile(paths[index]))
