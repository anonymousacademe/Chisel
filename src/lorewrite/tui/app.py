"""The lorewrite TUI application."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static
from textual import work

from .. import __version__
from ..ai.client import (
    DEFAULT_FAST_MODEL,
    DEFAULT_STRONG_MODEL,
    DEFAULT_WRITING_MODEL,
    set_api_key,
)
from ..ai.links import Suggestion, alias_form, suggest_links
from ..ai.style import learn_style
from ..ai.usage import LEDGER, format_cost
from ..ai.writing import build_context, generate
from ..core import drafts
from ..core import entities as ent
from ..core import settings as user_settings
from ..core.continuity import (
    apply_canon_update,
    filter_waived,
    get_canon,
    load_waivers,
    remove_waiver,
    save_waiver,
)
from ..core.index import Index
from ..core.links import link_at, rowcol_to_offset
from ..core.project import Project, retitle_text
from ..core.recents import add_recent
from ..core.style import (
    ensure_style_stub,
    load_style,
    sample_manuscript,
    save_style,
    style_path,
)
from .commands import ActionProvider, EntityProvider, InsertLinkProvider, SceneProvider
from .continuityscreen import ContinuityScreen, JumpToContradiction, WaiveToggled
from .editor import LinkedTextArea
from .launch import LaunchScreen
from .linkreview import AliasReviewScreen
from .panels import BacklinkSelected, EntityPanel
from .promptscreen import PromptScreen
from .settingscreen import KeyPrompt
from .sidebar import OpenFile, Sidebar
from .stylereview import StyleReviewScreen
from .theme import (
    distinct_color,
    draft_tint,
    link_color,
    load_omarchy_colors,
    omarchy_textual_theme,
)
from .tour import TourScreen

AUTOSAVE_DELAY = 0.6

HELP_TEXT = """\
# Keybindings

  ctrl+n          new scene
  alt+left/right  previous / next scene
  ctrl+p          command palette — everything else lives here
  ctrl+j          jump to the [[link]] under the cursor (creates the note if missing)
  ctrl+l          AI: find other ways this scene refers to your characters/places
                  ('the old smith' -> Borin) and add them as aliases
  ctrl+g          AI write: draft at the cursor (prompt window) - or, on a
                  {{expand: note}} marker, expand it - or, with text
                  selected, rewrite the selection in your style
  f7 / f8         accept / reject the AI draft under the cursor
                  (drafts are marked in color until you accept them)
  f5              select all (f7 is accept)
  ctrl+s          save now (autosave is always on)
  ctrl+b          hide/show the sidebar
  f11             writer mode — hide everything but the editor
  f9              rebuild the index from disk
  ?               this help
  ctrl+q          quit

# Also in the palette (ctrl+p)

  Settings — API key, models, editor preferences
  Return to main menu — save and switch projects

# Links

  No brackets needed: once a character or place has a note, every
  mention of its name or aliases is recognized (colored) automatically.

  select a name, ctrl+j   make a note for it (once — then it's recognized)
  ctrl+j on a name        open its note
  [[Name]] still works; its brackets are faded. orange = no note yet

Everything is saved as plain Markdown in your project folder.
Press escape or ? to close this help.
"""


def _word_count(text: str, originals: dict[str, str] | None = None) -> int:
    """Words in *text*, not counting pending AI drafts (unaccepted AI text)."""
    return len(drafts.strip_pending(text, originals).split())


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close"), Binding("question_mark", "close")]

    def compose(self) -> ComposeResult:
        from textual.widgets import Markdown

        yield Markdown(HELP_TEXT, id="help")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_click(self) -> None:
        self.dismiss(None)


class NamePrompt(ModalScreen[str | None]):
    """Single-line input modal. Dismisses with the entered text or None."""

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        yield Label(self._prompt)
        yield Input(id="name-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)

    def key_escape(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Yes/no confirmation. Dismisses True only on explicit confirm."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, message: str, confirm_label: str = "Delete") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        yield Label(self._message)
        yield Button(self._confirm_label, id="ok", variant="error")
        yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "ok")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class EntityTypePrompt(ModalScreen[str | None]):
    """Pick a type for a new entity note."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name

    def compose(self) -> ComposeResult:
        yield Label(Text(f'Create a note for "{self._name}" as:'))
        yield Button("Character", id="character", variant="primary")
        yield Button("Place", id="place")
        yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        self.dismiss(None if bid == "cancel" else bid)

    def action_cancel(self) -> None:
        self.dismiss(None)


class LorewriteApp(App):
    TITLE = "lorewrite"

    COMMANDS = App.COMMANDS | {SceneProvider, EntityProvider, InsertLinkProvider,
                               ActionProvider}

    BINDINGS = [
        Binding("ctrl+j", "jump", "Jump to link"),
        Binding("ctrl+n", "new_scene", "New scene"),
        Binding("ctrl+l", "find_aliases", "Find aliases"),
        Binding("ctrl+g", "generate", "AI write"),
        Binding("f7", "accept_draft", "Accept AI draft", show=False),
        Binding("f8", "reject_draft", "Reject AI draft", show=False),
        Binding("alt+left", "previous_scene", "Prev scene"),
        Binding("alt+right", "next_scene", "Next scene"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar"),
        Binding("f11", "writer_mode", "Writer mode"),
        Binding("f9", "rebuild_index", "Reindex"),
        Binding("question_mark", "help", "Help"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    CSS = """
    /* only the main layout row: a bare `Horizontal` rule also hit the
       Markdown widget's list items and blew up bullet lists */
    Screen > Horizontal { height: 1fr; }
    #sidebar { width: 28; border-right: solid $primary; }
    #panel { width: 38; border-left: solid $primary; }
    .sidebar-heading, .panel-heading {
        text-style: bold; padding: 0 1; background: $boost;
    }
    LinkedTextArea { width: 1fr; }
    #entity-body { height: 1fr; padding: 0 1; }
    #backlinks { height: 40%; }
    #status {
        height: 1; padding: 0 1;
        background: $boost; color: $text;
    }
    /* Writer mode: everything but the editor and status bar disappears */
    Screen.writer-mode #sidebar, Screen.writer-mode #panel,
    Screen.writer-mode Header, Screen.writer-mode Footer {
        display: none;
    }
    #filter { height: 1; border: none; padding: 0 1; }
    TourScreen { align: center middle; }
    #tour-page {
        width: 76; height: auto; max-height: 90%;
        padding: 1 2; background: $surface; border: solid $primary;
    }
    #tour-hint { width: 76; padding: 0 2; color: $text-muted; }
    HelpScreen { align: center middle; }
    HelpScreen #help {
        width: 72; height: auto; max-height: 90%;
        padding: 1 2; background: $surface; border: solid $primary;
    }
    NamePrompt, EntityTypePrompt { align: center middle; }
    NamePrompt > *, EntityTypePrompt > * { width: 60; }
    EntityTypePrompt Button { width: 100%; margin-top: 1; }
    NamePrompt Label, EntityTypePrompt Label {
        padding: 1; background: $surface; border: solid $primary; width: 62;
    }
    NamePrompt Input { border: solid $primary; }
    EntityTypePrompt Button { border: solid $primary; }
    ConfirmScreen { align: center middle; }
    ConfirmScreen > * { width: 60; }
    ConfirmScreen Label {
        padding: 1; background: $surface; border: solid $primary; width: 62;
    }
    ConfirmScreen Button { width: 100%; margin-top: 1; border: solid $primary; }
    LaunchScreen { align: center middle; }
    #launch {
        width: 76; height: auto; max-height: 90%;
        background: $surface; border: solid $primary; padding: 1 2;
    }
    #launch-title { text-style: bold; text-align: center; padding: 1 0; }
    .launch-heading { text-style: bold; padding: 1 0 0 0; }
    #recents { height: auto; max-height: 12; }
    #launch-hint { padding: 1 0 0 0; color: $text-muted; }
    PathPrompt, NewProjectPrompt { align: center middle; }
    PathPrompt > *, NewProjectPrompt > * { width: 64; }
    PathPrompt Label, NewProjectPrompt Label {
        padding: 1; background: $surface; border: solid $primary;
    }
    PathPrompt Input, NewProjectPrompt Input {
        border: solid $primary; margin-top: 1;
    }
    AliasReviewScreen { align: center middle; }
    #review-header {
        width: 76; padding: 1 2; background: $surface; border: solid $primary;
    }
    #suggestions {
        width: 76; height: auto; max-height: 60%;
        background: $surface; border: solid $primary; padding: 0 1;
    }
    #review-hint { width: 76; padding: 0 2; color: $text-muted; }
    ContinuityScreen, NoteUpdateScreen { align: center middle; }
    #continuity-header, #noteupdate-header {
        width: 76; padding: 1 2; background: $surface; border: solid $primary;
    }
    #contradictions, #updates {
        width: 76; height: auto; max-height: 60%;
        background: $surface; border: solid $primary; padding: 0 1;
    }
    #continuity-hint, #noteupdate-hint {
        width: 76; padding: 0 2; color: $text-muted;
    }
    PromptScreen { align: center middle; }
    #prompt-title {
        width: 76; padding: 1 2; background: $surface; border: solid $primary;
    }
    #prompt-input {
        width: 76; height: 8; border: solid $primary; background: $surface;
    }
    #prompt-hint { width: 76; padding: 0 2; color: $text-muted; }
    StyleReviewScreen { align: center middle; }
    #style-header {
        width: 84; padding: 1 2; background: $surface; border: solid $primary;
    }
    #style-scroll {
        width: 84; height: auto; max-height: 70%;
        background: $surface; border: solid $primary; padding: 0 1;
    }
    #style-hint { width: 84; padding: 0 2; color: $text-muted; }
    SettingsScreen { align: center middle; }
    #settings {
        width: 64; height: auto; max-height: 90%;
        background: $surface; border: solid $primary; padding: 1 2;
    }
    #settings-title { text-style: bold; text-align: center; }
    .settings-heading { text-style: bold; padding: 1 0 0 0; }
    /* compact fields: the screen must fit ~40 rows with three model rows */
    #settings Input { height: 1; border: none; padding: 0 1; background: $boost; }
    #settings Checkbox { height: 1; border: none; padding: 0; }
    #settings Button { width: 100%; height: 1; border: none; margin-top: 1; }
    #settings .model-row { height: auto; }
    #settings .model-row Input { width: 1fr; }
    #settings .model-row Button { width: 12; margin-top: 0; }
    #settings-hint { padding: 1 0 0 0; color: $text-muted; }
    """

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.project = project
        self.index: Index | None = None
        self.entities: list[ent.Entity] = []
        self.current_path: Path | None = None
        self._dirty = False
        self._save_timer = None
        self._save_token = 0
        self._status_text = ""
        self._writer_mode = False
        self._last_save: float | None = None
        self._project_words = 0
        self._editor_padding = 0
        # direct widget refs, set in compose(); safe to use during teardown
        self._editor: LinkedTextArea | None = None
        self._sidebar: Sidebar | None = None
        self._panel: EntityPanel | None = None
        self._status: Static | None = None
        self._style_tip_shown = False

    # -- layout ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        self._sidebar = Sidebar()
        self._editor = LinkedTextArea(id="editor")
        self._panel = EntityPanel()
        with Horizontal():
            yield self._sidebar
            yield self._editor
            yield self._panel
        self._status = Static("", id="status")
        yield self._status
        yield Footer()

    @property
    def editor(self) -> LinkedTextArea:
        assert self._editor is not None
        return self._editor

    @property
    def sidebar(self) -> Sidebar:
        assert self._sidebar is not None
        return self._sidebar

    @property
    def panel(self) -> EntityPanel:
        assert self._panel is not None
        return self._panel

    @property
    def idx(self) -> Index:
        """The index; only valid after a project is loaded."""
        assert self.index is not None, "no project loaded"
        return self.index

    # -- startup / shutdown -----------------------------------------------------

    def on_mount(self) -> None:
        omarchy_theme = omarchy_textual_theme()
        if omarchy_theme is not None:
            self.register_theme(omarchy_theme)
            self.theme = omarchy_theme.name
            colors = load_omarchy_colors() or {}
            from rich.style import Style

            resolved = link_color(colors)
            if resolved:
                self.editor.resolved_style = Style(
                    color=resolved, bold=True, underline=True
                )
                self.editor.mention_style = Style(color=resolved)
            hue = distinct_color(colors, [colors.get("foreground"), resolved,
                                          colors.get("orange")])
            self.editor.ai_style = Style(color=hue, italic=True,
                                         bgcolor=draft_tint(colors))
            if colors.get("dark_foreground"):
                self.editor.bracket_style = Style(color=colors["dark_foreground"])
            if colors.get("orange"):
                self.editor.unresolved_style = Style(
                    color=colors["orange"], bold=True, underline=True
                )
        if self.project is not None:
            self.initialize_project(self.project)
        else:
            self.push_screen(LaunchScreen(), self._launch_result)
        self.update_status()

    def _launch_result(self, project: Project | None) -> None:
        if project is None:
            self.exit()
            return
        self.initialize_project(project)

    def initialize_project(self, project: Project) -> None:
        """Load a project into the UI: index, entities, sidebar, first scene."""
        self.project = project
        self.index = Index(project.index_path)
        self.title = f"lorewrite v{__version__}"
        self.sub_title = project.title
        add_recent(project.root, project.title)
        self.idx.rebuild(project)
        self.reload_entities()
        self.refresh_sidebar()
        self.editor.link_resolver = self.is_resolved
        editor_prefs = project.editor_settings()
        self.editor.show_line_numbers = editor_prefs["line_numbers"]
        self._editor_padding = editor_prefs["padding"]
        self._apply_editor_padding()
        self._recount_project_words()
        scenes = project.list_scenes()
        if scenes:
            self.open_file(scenes[0])
        self.editor.focus()
        self.update_status()
        if not user_settings.get("tour_seen", False):
            user_settings.set("tour_seen", True)
            self.push_screen(TourScreen())

    def _apply_editor_padding(self) -> None:
        if not self._writer_mode:
            self.editor.styles.padding = (0, getattr(self, "_editor_padding", 0))

    def _recount_project_words(self) -> None:
        if self.project is None:
            self._project_words = 0
            return
        total = 0
        for path in self.project.list_scenes():
            try:
                text = path.read_text(encoding="utf-8")
                total += _word_count(text, self._originals(text, path))
            except OSError:
                continue
        self._project_words = total

    def on_unmount(self) -> None:
        if self._save_timer is not None:
            self._save_timer.stop()
        try:
            self._write_to_disk()  # final flush; UI updates skipped on teardown
        except Exception:
            pass
        if self.index is not None:
            self.index.close()

    # -- files --------------------------------------------------------------------

    def reload_entities(self) -> None:
        self.entities = self.project.load_entities()
        self._sync_mention_names()

    def _all_names(self) -> list[str]:
        return [n for e in self.entities for n in e.names]

    def _is_scene(self, path: Path | None) -> bool:
        return (path is not None and self.project is not None
                and path.parent == self.project.manuscript_dir)

    def _sync_mention_names(self) -> None:
        """Plain-name recognition applies to scenes, not entity notes."""
        if self._editor is not None:
            self._editor.mention_names = (
                self._all_names() if self._is_scene(self.current_path) else [])

    def _entities_changed(self) -> None:
        """Names/aliases changed: earlier scenes may now mention them."""
        self.idx.rebuild(self.project)
        self.reload_entities()
        self.refresh_sidebar()
        self.editor.refresh_links()

    def refresh_sidebar(self) -> None:
        self.sidebar.set_scenes(
            [(self.project.scene_title(p), p) for p in self.project.list_scenes()]
        )
        self.sidebar.set_entities(
            [(f"{e.name} [{e.type}]", e.path) for e in self.entities if e.path]
        )

    def open_file(self, path: Path) -> None:
        self.save_current()
        self.current_path = path
        self._dirty = False
        self._sync_mention_names()
        self.editor.load_text(path.read_text(encoding="utf-8"))
        self.editor.refresh_links()
        self.editor.focus()
        self.update_status()

    def _write_to_disk(self) -> None:
        if self.current_path is None or self._editor is None:
            return
        text = self._editor.text
        tmp = self.current_path.with_suffix(self.current_path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.current_path)
        if self.current_path == style_path(self.project):
            return  # the style guide isn't part of the link index
        rel = str(self.current_path.relative_to(self.project.root))
        names = self._all_names() if self._is_scene(self.current_path) else None
        self.idx.update_file(rel, text, names)

    def save_current(self, explicit: bool = False) -> None:
        """Write the current buffer to disk and refresh derived state."""
        if self.current_path is None or self._editor is None:
            return
        self._write_to_disk()
        names_before = self._all_names()
        self.reload_entities()
        if self._all_names() != names_before:  # aliases edited in a note
            self._entities_changed()
        self._dirty = False
        self._last_save = time.time()
        self._recount_project_words()
        self.update_panel_for_cursor()
        self.update_status()
        if explicit:
            self.notify("Saved", timeout=1)

    def on_text_area_changed(self) -> None:
        self._dirty = True
        self.editor.refresh_links()
        self.update_status()
        self._save_token += 1
        token = self._save_token
        if self._save_timer is not None:
            self._save_timer.stop()
        self._save_timer = self.set_timer(
            AUTOSAVE_DELAY, lambda: self._autosave(token)
        )

    def _autosave(self, token: int) -> None:
        if token == self._save_token and self._editor is not None:
            self.save_current()

    def on_open_file(self, message: OpenFile) -> None:
        self.open_file(message.path)

    # -- status bar ------------------------------------------------------------------

    def update_status(self) -> None:
        if self._status is None:
            return
        if self.current_path is None:
            self._status_text = "no file open — ctrl+p to open a scene"
            self._status.update(self._status_text)
            return
        rel = self.current_path.relative_to(self.project.root)
        if self._dirty:
            state = "● modified"
        elif self._last_save:
            state = f"saved {time.strftime('%H:%M', time.localtime(self._last_save))}"
        else:
            state = "saved"
        words = (_word_count(self._editor.text, self._originals(self._editor.text))
                 if self._editor else 0)
        if self._editor is not None:
            row, col = self._editor.cursor_location
            hint = self._link_hint()
            cursor = f"Ln {row + 1}, Col {col + 1}"
        else:
            hint, cursor = "", ""
        parts = [
            str(rel), state,
            f"{words} words ({self._project_words} project)",
            cursor,
        ]
        if hint:
            parts.append(hint)
        if LEDGER.session_total() > 0:
            parts.append(format_cost(LEDGER.session_total()))
        self._status_text = "  |  ".join(parts)
        self._status.update(self._status_text)

    def _link_hint(self) -> str:
        text = self._editor.text
        offset = rowcol_to_offset(text, *self._editor.cursor_location)
        hint = ""
        if drafts.pending_at(text, offset) is not None:
            hint = "AI draft — f7 accept · f8 reject"
        link = link_at(text, offset, self.editor.mention_names)
        if link is None:
            return hint
        if self.is_resolved(link.target):
            link_hint = f"{link.target} — ctrl+j to open"
        else:
            link_hint = f"{link.target} — no note, ctrl+j to create"
        return f"{hint}  |  {link_hint}" if hint else link_hint

    def _cost_note(self, calls_before: int) -> str:
        """' (AI $0.0031)' for the AI call made since *calls_before*, if the
        provider reported a cost. Also refreshes the status-bar total."""
        self.update_status()
        if LEDGER.count() <= calls_before:
            return ""
        last = LEDGER.last()
        if last is None or last.cost is None:
            return ""
        return f" ({format_cost(last.cost)})"

    # -- entity panel / backlinks --------------------------------------------------

    def is_resolved(self, target: str) -> bool:
        return ent.resolve(target, self.entities) is not None

    def on_text_area_selection_changed(self) -> None:
        self.update_panel_for_cursor()
        self.update_status()

    def update_panel_for_cursor(self) -> None:
        text = self.editor.text
        offset = rowcol_to_offset(text, *self.editor.cursor_location)
        link = link_at(text, offset, self.editor.mention_names)
        if link is None:
            return
        entity = ent.resolve(link.target, self.entities)
        if entity is None:
            self.panel.show_entity(f"{link.target} — no note yet", "")
            self.panel.set_backlinks([])
        else:
            self.panel.show_entity(f"{entity.name} [{entity.type}]", entity.body)
            self.panel.set_backlinks(self.idx.backlinks(entity))

    def on_backlink_selected(self, message: BacklinkSelected) -> None:
        path = self.project.root / message.source
        if path.is_file():
            self.open_file(path)
            self.editor.move_cursor((message.row, 0))

    # -- actions ---------------------------------------------------------------------

    def action_save(self) -> None:
        self.save_current(explicit=True)

    def action_toggle_sidebar(self) -> None:
        self.sidebar.display = not self.sidebar.display

    def writer_mode(self) -> None:
        """Toggle writer mode: hide chrome, pad the editor, keep status."""
        self._writer_mode = not self._writer_mode
        if self._writer_mode:
            self.screen.add_class("writer-mode")
            self.editor.styles.padding = (0, max(4, self._editor_padding))
        else:
            self.screen.remove_class("writer-mode")
            self._apply_editor_padding()
        self.editor.focus()

    action_writer_mode = writer_mode

    def _scene_neighbor(self, delta: int) -> None:
        if self.project is None:
            return
        scenes = self.project.list_scenes()
        if not scenes:
            self.notify("No scenes yet — ctrl+n to create one", severity="warning")
            return
        path = self._current_scene_path()
        if path is None:
            self.open_file(scenes[0])  # on an entity note: jump to the text
            return
        try:
            i = scenes.index(path)
        except ValueError:
            i = 0
        j = i + delta
        if not (0 <= j < len(scenes)):
            self.notify("No more scenes this way", severity="warning")
            return
        self.open_file(scenes[j])
        self.notify(self.project.scene_title(scenes[j]), timeout=1)

    def action_previous_scene(self) -> None:
        self._scene_neighbor(-1)

    def action_next_scene(self) -> None:
        self._scene_neighbor(1)

    previous_scene = action_previous_scene
    next_scene = action_next_scene

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # -- main menu & settings ---------------------------------------------------

    def action_main_menu(self) -> None:
        """Save, then return to the launch screen (switch projects)."""
        if self.project is None:
            return
        self.save_current()
        self.push_screen(LaunchScreen(), self._main_menu_result)

    main_menu = action_main_menu

    def _main_menu_result(self, project: Project | None) -> None:
        if project is None:
            return  # cancelled — stay in the current project
        if self.index is not None:
            self.index.close()
            self.index = None
        self.current_path = None
        self._dirty = False
        if self._writer_mode:
            self.writer_mode()  # toggle chrome back on for the switch
        self.editor.load_text("")
        self.initialize_project(project)

    def action_settings(self) -> None:
        from .settingscreen import SettingsScreen

        self.push_screen(SettingsScreen(self.project), self._settings_closed)

    open_settings = action_settings

    def _settings_closed(self, _) -> None:
        """Re-apply anything the settings screen may have changed."""
        if self.project is not None:
            prefs = self.project.editor_settings()
            self.editor.show_line_numbers = prefs["line_numbers"]
            self._editor_padding = prefs["padding"]
            self._apply_editor_padding()

    # -- AI: alias finder ----------------------------------------------------

    _MODEL_DEFAULTS = {
        "fast": DEFAULT_FAST_MODEL,
        "strong": DEFAULT_STRONG_MODEL,
        "writing": DEFAULT_WRITING_MODEL,
    }

    def _ai_model(self, kind: str) -> str:
        """kind: fast | strong | writing.

        Precedence: project.toml [ai] <kind>_model > global settings
        <kind>_model > built-in default.
        """
        key = f"{kind}_model"
        if self.project is not None:
            raw = (self.project.meta.get("ai") or {}).get(key)
            if raw:
                return str(raw)
        return user_settings.get(key) or self._MODEL_DEFAULTS[kind]

    def _ai_fast_model(self) -> str:
        return self._ai_model("fast")

    def action_find_aliases(self) -> None:
        """AI: find descriptive references to known entities; offer as aliases."""
        if self.project is None or self.current_path is None:
            self.notify("Open a scene first", severity="warning")
            return
        if not self.entities:
            self.notify("No entities yet — create some notes first",
                        severity="warning")
            return
        self.notify("Looking for aliases…", timeout=2)
        self._fetch_suggestions()

    find_aliases = action_find_aliases
    action_link_mentions = action_find_aliases  # pre-M4 name
    link_mentions = action_find_aliases

    @work(exclusive=True)
    async def _fetch_suggestions(self) -> None:
        # AI text isn't canon; blanking (not stripping) keeps line numbers
        scene_text = drafts.blank_pending(self.editor.text)
        entities = list(self.entities)
        calls = LEDGER.count()
        try:
            suggestions = await asyncio.to_thread(
                suggest_links, scene_text, entities, self._ai_fast_model()
            )
        except Exception as exc:
            self.notify(f"Alias search failed: {exc}", severity="error",
                        timeout=6)
            return
        cost = self._cost_note(calls)
        if not suggestions:
            self.notify("No new aliases found" + cost, timeout=2)
            return
        if cost:
            self.notify(f"Found {len(suggestions)} possible alias(es){cost}",
                        timeout=3)
        self.push_screen(
            AliasReviewScreen(suggestions, scene_text),
            self._apply_alias_suggestions,
        )

    def _apply_alias_suggestions(self, accepted: list[Suggestion] | None) -> None:
        """Accepted suggestions become aliases; scene text is never modified."""
        if not accepted:
            return
        added = 0
        for s in accepted:
            entity = ent.resolve(s.entity, self.entities)
            if entity is None:
                continue
            alias = alias_form(s.surface)
            if all(alias.casefold() != n.casefold() for n in entity.names):
                ent.add_alias(entity, alias)
                added += 1
        self._entities_changed()
        self.notify(f"Added {added} alias(es) to entity notes", timeout=2)

    # -- AI drafts: accept / reject (M4) ------------------------------------------

    def _cursor_offset(self) -> int:
        return rowcol_to_offset(self.editor.text, *self.editor.cursor_location)

    def _originals(self, text: str, path: Path | None = None) -> dict[str, str]:
        """The draft sidecar of *path* (default: the open scene); read only
        when the text actually contains an id-carrying draft."""
        path = path or self.current_path
        if self.project is None or path is None or '<!--ai id="' not in text:
            return {}
        return drafts.load_originals(self.project.root, path)

    def action_accept_draft(self) -> None:
        """Accept the pending AI draft under the cursor (becomes normal text)."""
        pending = drafts.pending_at(self.editor.text, self._cursor_offset())
        if pending is None:
            self.notify("No AI draft under the cursor", severity="warning",
                        timeout=2)
            return
        body = self.editor.text[pending.body_start:pending.body_end]
        self.editor.replace_offsets(pending.start, pending.end, body)
        self._forget_originals([pending])
        self.notify("AI draft accepted", timeout=1)

    def _forget_originals(self, resolved: list) -> None:
        """Drop sidecar entries of accepted/rejected drafts."""
        if self.project is None or self.current_path is None:
            return
        for p in resolved:
            if p.id is not None:
                drafts.drop_original(self.project.root, self.current_path, p.id)

    def _reject_pending(self, pending) -> bool:
        """Restore what a draft replaced. Refuses (returns False) when the
        original is missing: prose is never deleted on a failed lookup."""
        originals = self._originals(self.editor.text)
        if pending.id is not None and pending.id not in originals:
            return False
        original = originals[pending.id] if pending.id is not None else ""
        self.editor.replace_offsets(pending.start, pending.end, original)
        self._forget_originals([pending])
        return True

    def action_reject_draft(self) -> None:
        """Reject the pending AI draft under the cursor: restore what was there."""
        pending = drafts.pending_at(self.editor.text, self._cursor_offset())
        if pending is None:
            self.notify("No AI draft under the cursor", severity="warning",
                        timeout=2)
            return
        if not self._reject_pending(pending):
            self.notify("Original text for this draft is missing — accept it "
                        "or edit by hand", severity="error", timeout=6)
            return
        self.notify("AI draft rejected", timeout=1)

    def _resolve_all_drafts(self, accept: bool) -> None:
        found = drafts.find_pending(self.editor.text)
        if not found:
            self.notify("No AI drafts in this scene", timeout=2)
            return
        skipped = 0
        for p in reversed(found):  # back to front so offsets hold
            if accept:
                text = self.editor.text
                self.editor.replace_offsets(
                    p.start, p.end, text[p.body_start:p.body_end])
                self._forget_originals([p])
            elif not self._reject_pending(p):
                skipped += 1
        verb = "accepted" if accept else "rejected"
        msg = f"{len(found) - skipped} AI draft(s) {verb}"
        if skipped:
            msg += (f"; {skipped} left because the original text is missing"
                    " — accept them or edit by hand")
        self.notify(msg, severity="warning" if skipped else "information",
                    timeout=6 if skipped else 2)

    def accept_all_drafts(self) -> None:
        self._resolve_all_drafts(True)

    def reject_all_drafts(self) -> None:
        self._resolve_all_drafts(False)

    # -- AI: generate — draft, expand, rewrite (M4) ---------------------------------

    def action_generate(self) -> None:
        """ctrl+g: rewrite the selection, expand the {{expand:}} marker under
        the cursor, or draft new prose at the cursor (prompt window)."""
        if self.project is None or not self._is_scene(self.current_path):
            self.notify("Open a scene first", severity="warning")
            return
        text = self.editor.text
        selected = self.editor.selected_text
        if selected.strip():
            start, end = self.editor.selection
            lo = min(rowcol_to_offset(text, *start), rowcol_to_offset(text, *end))
            hi = max(rowcol_to_offset(text, *start), rowcol_to_offset(text, *end))
            self.push_screen(
                PromptScreen("Rewrite the selection — edit the instruction:",
                             "Rewrite this in my style."),
                lambda instruction: self._start_generate(
                    "rewrite", instruction, lo, hi),
            )
            return
        offset = self._cursor_offset()
        marker = drafts.expand_marker_at(text, offset)
        if marker is not None:
            if not marker.instruction.strip():
                self.notify("Empty {{expand: }} marker — say what to write",
                            severity="warning")
                return
            self._start_generate("expand", marker.instruction, marker.start,
                                 marker.end)
            return
        self.push_screen(
            PromptScreen("What should the AI write here? (e.g. \"one paragraph"
                         " describing the busy street, stressed mood\")"),
            lambda instruction: self._start_generate(
                "draft", instruction, offset, offset),
        )

    generate_text = action_generate

    def _start_generate(self, mode: str, instruction: str | None,
                        start: int, end: int) -> None:
        if not instruction:
            return
        text = self.editor.text
        selection = text[start:end] if end > start else None
        span = (start, end) if end > start else None
        context = build_context(text, start, self.entities, self._canon_map(),
                                load_style(self.project), span=span,
                                originals=self._originals(text))
        if load_style(self.project) is None and not self._style_tip_shown:
            self._style_tip_shown = True
            self.notify("Tip: learn a style guide first (ctrl+p → learn style)",
                        timeout=5)
        model = self._ai_model("writing")
        self.notify(f"Drafting… ({model})", timeout=3)
        self._generate_worker(mode, instruction, context, model, selection,
                              start, end, self.current_path, text)

    @work(exclusive=True, group="generate")
    async def _generate_worker(self, mode, instruction, context, model,
                               selection, start, end, path, snapshot) -> None:
        calls = LEDGER.count()
        try:
            body = await asyncio.to_thread(
                generate, mode, instruction, context, model,
                selection=selection)
        except Exception as exc:
            self.notify(f"AI writing failed: {exc}", severity="error",
                        timeout=6)
            return
        cost = self._cost_note(calls)
        if self.current_path != path:
            self.notify("Scene changed while drafting — draft discarded" + cost,
                        severity="warning", timeout=5)
            return
        self._insert_draft(mode, body, start, end, selection, snapshot)
        self.notify(f"AI draft ready — f7 accept · f8 reject{cost}", timeout=5)

    def _insert_draft(self, mode: str, body: str, start: int, end: int,
                      original: str | None, snapshot: str) -> None:
        """Put *body* into the scene as a pending draft. The buffer may have
        changed while the model worked: re-find what is being replaced, else
        fall back to the current cursor (insertions) or give up (rewrites)."""
        text = self.editor.text
        if mode == "draft":
            pos = start if text == snapshot else self._cursor_offset()
            if pos > 0 and not text[pos - 1].isspace() and not body[0].isspace():
                body = " " + body  # inside the draft: accept keeps the spacing
            self.editor.replace_offsets(pos, pos, drafts.wrap(body))
            return
        if text[start:end] != original:
            first = text.find(original)
            if first == -1 or text.find(original, first + 1) != -1:
                self.notify("The text changed while drafting — draft discarded",
                            severity="warning", timeout=5)
                return
            start, end = first, first + len(original)
        # sidecar first: a marker must never exist without its original
        draft_id = drafts.new_id(
            drafts.all_ids(self.project.root)
            | {p.id for p in drafts.find_pending(text) if p.id})
        drafts.add_original(self.project.root, self.current_path, draft_id,
                            original)
        self.editor.replace_offsets(start, end, drafts.wrap(body, draft_id))

    # -- AI: style guide (M4) ---------------------------------------------------

    def action_open_style_guide(self) -> None:
        """Open style.md in the editor, creating it from a stub if missing."""
        if self.project is None:
            return
        self.save_current()
        self.open_file(ensure_style_stub(self.project))

    open_style_guide = action_open_style_guide

    def action_learn_style(self) -> None:
        """AI: learn a style guide from the manuscript; review before saving."""
        if self.project is None:
            self.notify("Open a project first", severity="warning")
            return
        self.save_current()
        samples = sample_manuscript(self.project)
        if not samples:
            self.notify("Nothing to learn from yet — write some scenes first",
                        severity="warning")
            return
        self.notify(f"Learning your style from {len(samples)} paragraphs…",
                    timeout=3)
        self._learn_style_worker(samples)

    learn_style_guide = action_learn_style

    @work(exclusive=True, group="style")
    async def _learn_style_worker(self, samples) -> None:
        calls = LEDGER.count()
        try:
            proposal = await asyncio.to_thread(
                learn_style, samples, self._ai_model("writing"))
        except Exception as exc:
            self.notify(f"Style guide failed: {exc}", severity="error",
                        timeout=6)
            return
        cost = self._cost_note(calls)
        if cost:
            self.notify(f"Style guide ready{cost}", timeout=3)
        replacing = style_path(self.project).is_file()
        self.push_screen(
            StyleReviewScreen(proposal.markdown, replacing),
            lambda ok: self._save_style_guide(proposal.markdown, ok),
        )

    def _save_style_guide(self, markdown: str, ok: bool | None) -> None:
        if not ok or self.project is None:
            return
        path = save_style(self.project, markdown)
        if self.current_path == path:  # open in the editor: show the new text
            self.editor.load_text(markdown)
            self._dirty = False
            self.update_status()
        self.notify("Saved style.md", timeout=2)

    def set_api_key(self) -> None:
        def _store(key: str | None) -> None:
            if not key:
                return
            try:
                set_api_key(key)
                self.notify("API key stored in the system keyring", timeout=3)
            except Exception as exc:
                self.notify(
                    f"Keyring unavailable ({exc}). Set the OPENROUTER_API_KEY"
                    " environment variable instead.",
                    severity="error", timeout=8,
                )

        self.push_screen(KeyPrompt(), _store)

    # -- AI: continuity checking (M3) -----------------------------------------

    def _ai_strong_model(self) -> str:
        return self._ai_model("strong")

    def _canon_map(self) -> dict[str, str]:
        """Established canon per entity: the managed section, else the body."""
        canon = {}
        for e in self.entities:
            managed = get_canon(e.body)
            canon[e.name] = managed if managed else e.body[:1500]
        return canon

    def action_check_continuity(self) -> None:
        """AI: check the current scene against the story bible."""
        if self.project is None or self.current_path is None:
            self.notify("Open a scene first", severity="warning")
            return
        if not self.entities:
            self.notify("No entities yet — nothing to check against",
                        severity="warning")
            return
        self.notify("Checking continuity…", timeout=2)
        self._check_continuity_worker()

    check_continuity = action_check_continuity

    @work(exclusive=True)
    async def _check_continuity_worker(self) -> None:
        from dataclasses import replace

        from ..ai.continuity import check_scene

        scene_text = drafts.strip_pending(  # AI text isn't canon
            self.editor.text, self._originals(self.editor.text))
        entities = list(self.entities)
        canon = self._canon_map()
        scene_rel = str(self.current_path.relative_to(self.project.root))
        calls = LEDGER.count()
        try:
            results = await asyncio.to_thread(
                check_scene, scene_text, entities, canon,
                self._ai_strong_model(),
            )
        except Exception as exc:
            self.notify(f"Continuity check failed: {exc}", severity="error",
                        timeout=6)
            return
        # check_scene leaves scene blank; the jump action needs it
        cost = self._cost_note(calls)
        results = [replace(c, scene=scene_rel) for c in results]
        results = filter_waived(results, load_waivers(self.project.root))
        if not results:
            self.notify("No continuity issues found" + cost, timeout=3)
            return
        if cost:
            self.notify(f"Continuity check done{cost}", timeout=3)
        self.push_screen(ContinuityScreen(results))

    def on_waive_toggled(self, message: WaiveToggled) -> None:
        if self.project is None:
            return
        if message.waived:
            save_waiver(self.project.root, message.waiver_key)
        else:
            remove_waiver(self.project.root, message.waiver_key)

    def on_jump_to_contradiction(self, message: JumpToContradiction) -> None:
        c = message.contradiction
        if self.project is None or not c.scene:
            return
        path = self.project.root / c.scene
        if not path.is_file():
            return
        self.open_file(path)
        if c.row is not None:
            self.editor.move_cursor((c.row, 0))

    def action_update_bible(self) -> None:
        """AI: propose canon updates to entity notes from this scene."""
        if self.project is None or self.current_path is None:
            self.notify("Open a scene first", severity="warning")
            return
        if not self.entities:
            self.notify("No entities yet — create some notes first",
                        severity="warning")
            return
        self.notify("Reading the scene for new canon…", timeout=2)
        self._update_bible_worker()

    update_bible = action_update_bible

    @work(exclusive=True)
    async def _update_bible_worker(self) -> None:
        from ..ai.continuity import propose_canon_updates
        from .noteupdates import NoteUpdateScreen

        scene_text = drafts.strip_pending(  # AI text isn't canon
            self.editor.text, self._originals(self.editor.text))
        entities = list(self.entities)
        calls = LEDGER.count()
        try:
            updates = await asyncio.to_thread(
                propose_canon_updates, scene_text, entities,
                self._ai_strong_model(),
            )
        except Exception as exc:
            self.notify(f"Story-bible update failed: {exc}", severity="error",
                        timeout=6)
            return
        cost = self._cost_note(calls)
        if not updates:
            self.notify("No new canon found in this scene" + cost, timeout=2)
            return
        if cost:
            self.notify(f"Canon proposals ready{cost}", timeout=3)
        self.push_screen(NoteUpdateScreen(updates), self._apply_canon_updates)

    def _apply_canon_updates(self, accepted) -> None:
        if not accepted:
            return
        applied = 0
        for update in accepted:
            entity = ent.resolve(update.entity, self.entities)
            if entity is not None:
                apply_canon_update(entity, list(update.new_facts))
                applied += 1
        self.reload_entities()
        self.refresh_sidebar()
        self.editor.refresh_links()
        self.notify(f"Added canon to {applied} entity note(s)", timeout=2)

    def action_jump(self) -> None:
        """Open the note for the name under the cursor.

        With a selection (or on an unresolved [[link]]), create a note for it
        first; from then on plain mentions of the name are recognized.
        """
        selected = self.editor.selected_text.strip()
        if selected and "\n" not in selected:
            target = selected
        else:
            text = self.editor.text
            offset = rowcol_to_offset(text, *self.editor.cursor_location)
            link = link_at(text, offset, self.editor.mention_names)
            if link is None:
                self.notify("Select a name and press ctrl+j to make a note for it",
                            severity="warning")
                return
            target = link.target
        entity = ent.resolve(target, self.entities)
        if entity is not None and entity.path is not None:
            self.open_file(entity.path)
            return
        self.save_current()

        def _created(etype: str | None) -> None:
            if etype is None:
                return
            _, path = self.project.create_entity(target, etype)
            self._entities_changed()
            self.open_file(path)

        self.push_screen(EntityTypePrompt(target), _created)

    def insert_link(self, name: str) -> None:
        self.editor.insert(name)
        self.editor.refresh_links()
        self.editor.focus()
        self.save_current()

    def action_new_scene(self) -> None:
        self.create_scene_prompt()

    def create_scene_prompt(self) -> None:
        def _create(title: str | None) -> None:
            if not title:
                return
            path = self.project.next_scene_path(title)
            path.write_text(f"# {title}\n\n", encoding="utf-8")
            self.refresh_sidebar()
            self.open_file(path)

        self.push_screen(NamePrompt("New scene title:"), _create)

    # -- scene organization -----------------------------------------------------

    def _current_scene_path(self) -> Path | None:
        """The open file, if it's a manuscript scene (not an entity note)."""
        if self.project is None or self.current_path is None:
            return None
        if self.current_path.parent == self.project.manuscript_dir:
            return self.current_path
        return None

    def rename_scene_prompt(self) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        current = self.project.scene_title(path)

        def _rename(title: str | None) -> None:
            if not title or title == current:
                return
            # retitle the editor buffer, then save — a disk-side rename would
            # be clobbered by the next autosave of the stale buffer
            self.editor.load_text(retitle_text(self.editor.text, title))
            self.save_current()
            self.refresh_sidebar()
            self.notify(f"Renamed to '{title}'", timeout=1)

        self.push_screen(NamePrompt(f"Rename '{current}' to:"), _rename)

    def delete_scene_confirm(self) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        title = self.project.scene_title(path)

        def _delete(ok: bool) -> None:
            if not ok:
                return
            rel = str(path.relative_to(self.project.root))
            self.project.delete_scene(path)
            self.idx.remove_file(rel)
            # detach BEFORE open_file, whose save step would otherwise
            # resurrect the deleted file from the editor buffer
            self.current_path = None
            self.editor.load_text("")
            self.refresh_sidebar()
            scenes = self.project.list_scenes()
            if scenes:
                self.open_file(scenes[0])
            else:
                self.update_status()
            self.notify(f"Deleted '{title}'", timeout=2)

        self.push_screen(
            ConfirmScreen(
                f"Delete scene '{title}'?\nThis deletes {path.name} from disk."
            ),
            _delete,
        )

    def _move_scene(self, delta: int) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        new_path = self.project.move_scene(path, delta)
        if new_path is None:
            self.notify("Scene is already at the edge", severity="warning")
            return
        self.current_path = new_path  # content unchanged; only the name moved
        self.refresh_sidebar()
        self.update_status()
        self.notify(f"Moved to {new_path.name}", timeout=1)

    def move_scene_up(self) -> None:
        self._move_scene(-1)

    def move_scene_down(self) -> None:
        self._move_scene(1)

    def _make_entity_prompt(self, etype: str) -> None:
        def _create(name: str | None) -> None:
            if not name:
                return
            _, path = self.project.create_entity(name, etype)
            self._entities_changed()
            self.open_file(path)

        self.push_screen(NamePrompt(f"New {etype} name:"), _create)

    def create_entity_prompt_character(self) -> None:
        self._make_entity_prompt("character")

    def create_entity_prompt_place(self) -> None:
        self._make_entity_prompt("place")

    def rebuild_index(self) -> None:
        self.save_current()
        self.idx.rebuild(self.project)
        self.reload_entities()
        self.refresh_sidebar()
        self.editor.refresh_links()
        self.notify("Index rebuilt")

    action_rebuild_index = rebuild_index


def main() -> None:
    parser = argparse.ArgumentParser(prog="lorewrite")
    parser.add_argument("--project", type=Path, default=None,
                        help="Open this project directly (default: launch screen)")
    parser.add_argument("--new", metavar="TITLE",
                        help="Create a new project with this title"
                             " (at --project, or cwd)")
    args = parser.parse_args()

    project: Project | None = None
    if args.new:
        project = Project.create(args.project or Path.cwd(), title=args.new)
    elif args.project is not None and Project.is_project(args.project):
        project = Project.open(args.project)
    app = LorewriteApp(project)
    app.run()


if __name__ == "__main__":
    main()
