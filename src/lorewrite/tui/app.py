"""The lorewrite TUI application."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static
from textual.widgets.text_area import Selection
from textual import work

from .. import __version__
from ..ai.client import MODEL_DEFAULTS, resolve_model, set_api_key
from ..ai.links import Suggestion, alias_form, suggest_links
from ..ai.style import learn_style
from ..ai.usage import LEDGER, format_cost
from ..ai.writing import (
    ask as ask_writer,
    brainstorm as brainstorm_ideas,
    build_context,
    build_project_context,
    generate,
    research_answer,
    research_context,
)
from ..core import chats, inspiration
from ..core import collections as coll
from ..core import research as research_notes
from ..core import comments
from ..core import drafts, scenemeta, snapshots, sync
from ..core import entities as ent
from ..core import settings as user_settings
from ..core import spelling
from ..core import stats as writing_stats
from ..core.continuity import (
    apply_canon_update,
    canon_map,
    clear_scene_waivers,
    filter_waived,
    load_waivers,
    remove_waiver,
    save_waiver,
)
from ..core.index import Index
from ..core.links import link_at, offset_to_rowcol, rowcol_to_offset
from ..core.project import Project, retitle_text, write_atomic
from ..core.recents import add_recent
from ..core.style import (
    ensure_style_stub,
    load_style,
    manuscript_stats,
    select_voice_samples,
    sample_manuscript,
    save_style,
    style_path,
)
from .assistantscreen import AssistantOps, AssistantScreen, ChatMsg, ChatsScreen
from .collectionscreens import CollectionsScreen
from .commentscreens import CommentsScreen
from .commands import (
    ActionProvider,
    EntityProvider,
    InsertLinkProvider,
    ResearchProvider,
    SceneProvider,
)
from .continuityscreen import ContinuityScreen, JumpToContradiction, WaiveToggled
from .editor import LinkedTextArea
from .launch import LaunchScreen
from .linkreview import AliasReviewScreen
from .panels import BacklinkSelected, EntityPanel
from .brainstormscreen import BrainstormScreen
from .promptscreen import PromptScreen
from .settingscreen import KeyPrompt
from .sidebar import OpenFile, Sidebar
from .spellscreen import SpellScreen
from .snapshotscreens import CompareScreen, LabelPrompt, SnapshotsScreen, label_text
from .syncscreens import MessagePrompt
from .statsscreens import StatsScreen
from .structurescreens import ChoiceScreen, DetailsScreen, TrashScreen
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
  f6              spell check: fix the next misspelled word (suggestions,
                  add to the project / your dictionary, ignore)
  ctrl+s          save now (autosave is always on)
  ctrl+b          hide/show the sidebar
  f11             writer mode — hide everything but the editor
  f9              rebuild the index from disk
  f1              this help (also ? when not typing in the editor)
  ctrl+q          quit

# Also in the palette (ctrl+p)

  New part / Rename part / Move part up, down / Delete empty part
  Move scene to part / Move scene to Unplaced / Place scene in the book
  Scene · Edit details — POV, place, purpose, status, word target
  Open Trash — restore deleted scenes and research notes, delete forever, empty the Trash
  Scene · Snapshots / Snapshot scene / Snapshot all scenes — compare and restore
  Brainstorm — AI "unstuck" ideas for the open scene; draft from one or save it to notes
  Focus sprint — 15 / 25 / 45 / custom minutes, countdown in the status bar, optional writer mode
  Session stats — today, this session, 30-day sparkline, streak, daily target (Settings)
  Start new draft — snapshot the whole book as "end of draft N", then count up
  Commit changes / Push / Initialize git — only when you pick them; the status
  bar shows Synced, N changes or Ahead N for a project under git
  Scene · Collections — tick the scene's collections (sidebar filter: #name)
  Scene · Add comment on selection / Scene · Comments — notes kept beside the
  scene, never in the text; commented text is underlined faintly
  Research · <note> / New research note / ... from a link — research/ notes
  Ask the assistant (ctrl+r research mode: answers from your notes, citing them;
  ctrl+t saved conversations, ctrl+n new chat, ctrl+s save an answer to notes)
  Call them chapters / Call them scenes (wording only)
  Settings — API key, models, editor preferences, spell check
  Toggle spell check / Add selection to dictionary / Open project dictionary
  Return to main menu — save and switch projects

# Links

  No brackets needed: once a character or place has a note, every
  mention of its name or aliases is recognized (colored) automatically.

  select a name, ctrl+j   make a note for it (once — then it's recognized)
  ctrl+j on a name        open its note
  [[Name]] still works; its brackets are faded. orange = no note yet

Everything is saved as plain Markdown in your project folder.
Press escape, f1 or ? to close this help.
"""


def _word_count(text: str, originals: dict[str, str] | None = None) -> int:
    """Words in *text*, not counting pending AI drafts (unaccepted AI text)."""
    return drafts.count_words(text, originals)


def help_renderable() -> Text:
    """HELP_TEXT with every line on its own row. (Markdown collapses single
    line breaks, which ran the keybinding lists together.) Lines starting
    with '# ' are section headings, shown bold and colored."""
    out = Text()
    for i, line in enumerate(HELP_TEXT.rstrip("\n").split("\n")):
        if i:
            out.append("\n")
        if line.startswith("# "):
            out.append(line[2:], style="bold underline")
        else:
            out.append(line)
    return out


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close"), Binding("question_mark", "close"),
                Binding("f1", "close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-scroll"):
            yield Static(help_renderable(), id="help")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_click(self) -> None:
        self.dismiss(None)


class NamePrompt(ModalScreen[str | None]):
    """Single-line input modal. Dismisses with the entered text or None."""

    def __init__(self, prompt: str, initial: str = "") -> None:
        super().__init__()
        self._prompt = prompt
        self._initial = initial

    def compose(self) -> ComposeResult:
        yield Label(self._prompt)
        yield Input(self._initial, id="name-input")

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

    COMMANDS = App.COMMANDS | {SceneProvider, EntityProvider, ResearchProvider,
                               InsertLinkProvider, ActionProvider}

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
        Binding("f1", "help", "Help"),
        Binding("question_mark", "help", "Help", show=False),
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
    HelpScreen #help-scroll {
        width: 100; max-width: 100%; height: auto; max-height: 90%;
        padding: 1 2; background: $surface; border: solid $primary;
    }
    HelpScreen #help { width: 100%; height: auto; }
    NamePrompt, EntityTypePrompt { align: center middle; }
    NamePrompt > *, EntityTypePrompt > * { width: 60; }
    EntityTypePrompt Button { width: 100%; margin-top: 1; }
    NamePrompt Label, EntityTypePrompt Label {
        padding: 1; background: $surface; border: solid $primary; width: 62;
    }
    NamePrompt Input { border: solid $primary; }
    EntityTypePrompt Button { border: solid $primary; }
    ChoiceScreen, TrashScreen, DetailsScreen, StatsScreen, BrainstormScreen { align: center middle; }
    #idea-box { width: 90; height: auto; max-height: 85%; background: $surface; border: solid $primary; padding: 1 2; }
    #idea-header { text-style: bold; padding-bottom: 1; }
    #idea-list { height: auto; max-height: 22; }
    #idea-list ListItem Label { width: 100%; padding-bottom: 1; }
    #idea-hint { color: $text-muted; padding-top: 1; }
    #choice-box, #trash-box, #details-box, #snap-box, #compare-box, #stats-box {
        width: 76; height: auto; max-height: 80%;
        background: $surface; border: solid $primary; padding: 1 2;
    }
    #choice-header, #trash-header, #details-header, #snap-header, #compare-header, #stats-header { text-style: bold; padding-bottom: 1; }
    #choice-list, #trash-list, #snap-list { height: auto; max-height: 16; }
    #choice-hint, #trash-hint, #details-hint, #snap-hint, #compare-hint, #stats-hint { color: $text-muted; padding-top: 1; }
    #stats-box { width: 100; }
    #stats-scroll { height: auto; max-height: 20; }
    #compare-box { width: 110; height: 80%; }
    #compare-scroll { height: 1fr; border: round $primary-darken-2; padding: 0 1; }
    .details-label { color: $text-muted; padding-top: 1; }
    #sidebar .part-header { background: $boost; }
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
    #launch-hint { width: 100%; height: auto; padding: 1 0 0 0; color: $text-muted; }
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
    /* long canon facts wrap instead of running off the modal */
    #updates ListItem Label { width: 100%; height: auto; }
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
    SpellScreen { align: center middle; }
    #spell-header {
        width: 60; padding: 1 2; background: $surface; border: solid $primary;
    }
    #spell-suggestions {
        width: 60; height: auto; padding: 0 2; background: $surface;
        border: solid $primary;
    }
    #spell-hint { width: 60; padding: 0 2; color: $text-muted; }
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
        self._snapshot_at = None  # datetime of the open scene's latest snapshot
        self._sync = None         # core.sync.SyncStatus of the project folder (None: no git / no repo)
        self._sync_timer = None
        self._project_words = 0
        self._editor_padding = 0
        # direct widget refs, set in compose(); safe to use during teardown
        self._editor: LinkedTextArea | None = None
        self._sidebar: Sidebar | None = None
        self._panel: EntityPanel | None = None
        self._status: Static | None = None
        self._style_tip_shown = False
        self._spell_timer = None
        self._spell_lines = 0
        self._chat_messages: list[ChatMsg] = []
        self._chat_id: str | None = None      # the saved conversation behind it
        self._assistant_screen: AssistantScreen | None = None
        self._comment_list: list[comments.Comment] = []   # the open scene's comments
        self._comment_scene: Path | None = None
        self._spell_ignores = spelling.SessionIgnores()
        self.stats: writing_stats.Tracker | None = None   # personal writing stats (state dir)
        self._stats_brief: dict | None = None
        self._sprint_timer = None
        self._sprint_writer = False   # the sprint switched writer mode on, so it switches it off
        self._skip_touch = False   # the Changed event of a programmatic load is not typing

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
        if self.stats is not None:
            self.stats.close()
        self.stats = writing_stats.Tracker(project.root)
        if self._sprint_timer is None:
            self._sprint_timer = self.set_interval(1.0, self._sprint_tick)
        self._recount_project_words()
        self._refresh_stats()
        scenes = project.list_scenes()
        if scenes:
            self.open_file(scenes[0])
        self.editor.focus()
        self.update_status()
        self.refresh_sync()
        if not user_settings.get("tour_seen", False):
            user_settings.set("tour_seen", True)
            self.push_screen(TourScreen())

    def _apply_editor_padding(self) -> None:
        if not self._writer_mode:
            self.editor.styles.padding = (0, getattr(self, "_editor_padding", 0))

    # -- writing stats (core.stats): counted on save, kept in the state dir ------------

    def _stats_key(self, path: Path) -> str:
        return path.relative_to(self.project.root).as_posix()

    def _stats_seen(self, text: str, path: Path | None = None) -> None:
        """A scene was opened or replaced wholesale: its baseline, nothing counted."""
        path = path or self.current_path
        if self.stats is None or not self._is_scene(path):
            return
        self.stats.seen(self._stats_key(path), _word_count(text, self._originals(text, path)))

    def _stats_record(self, text: str) -> None:
        if self.stats is None or not self._is_scene(self.current_path):
            return
        try:
            self.stats.record(self._stats_key(self.current_path),
                              _word_count(text, self._originals(text)))
            self._refresh_stats()
        except OSError:
            pass  # stats are a convenience; never block a save

    def _stats_accepted(self, pending, body: str) -> None:
        """An AI draft is about to become prose: AI words, not the author's."""
        if self.stats is None or not self._is_scene(self.current_path):
            return
        original = self._originals(self.editor.text).get(pending.id, "") if pending.id else ""
        self.stats.accepted(self._stats_key(self.current_path), len(body.split()),
                            len(original.split()))

    def _refresh_stats(self) -> None:
        if self.stats is None:
            self._stats_brief = None
            return
        s = self.stats.summary()
        self._stats_brief = {"target": s["target"], "streak": s["streak"],
                             "todayWords": s["today"]["words"], "sprint": s["sprint"]}

    # -- focus sprint (Wave 4.2): a countdown in the status bar, optionally in writer mode ---

    SPRINT_CHOICES = [("15 minutes", 15), ("25 minutes", 25), ("45 minutes", 45), ("Custom length…", 0)]

    def focus_sprint(self) -> None:
        """Action · Focus sprint: start a timed writing sprint, or stop the running one."""
        if self.stats is None:
            return
        if self.stats.sprint is not None:
            def _stop(choice) -> None:
                if choice == "stop":
                    self._end_sprint(cancelled=True)

            self.push_screen(ChoiceScreen(
                f"Sprint running: {writing_stats.clock(self.stats.sprint_state()['remaining'])} left",
                [("Stop the sprint (keeps what you wrote)", "stop"), ("Keep going", "keep")]), _stop)
            return

        def _length(minutes) -> None:
            if minutes is None:
                return
            if minutes == 0:
                def _custom(raw) -> None:
                    try:
                        self._ask_sprint_mode(int(raw or 0))
                    except ValueError:
                        self.notify("A sprint length is a whole number of minutes", severity="warning")

                self.push_screen(NamePrompt("Sprint length in minutes (1-240):", "30"), _custom)
            else:
                self._ask_sprint_mode(minutes)

        self.push_screen(ChoiceScreen("Focus sprint - how long?", self.SPRINT_CHOICES), _length)

    def _ask_sprint_mode(self, minutes: int) -> None:
        def _go(writer) -> None:
            if writer is not None:
                self._start_sprint(minutes, bool(writer))

        self.push_screen(ChoiceScreen(
            f"{minutes}-minute sprint", [("Start, keep the screen as it is", False),
                                         ("Start in writer mode (hides everything but the editor)", True)]), _go)

    def _start_sprint(self, minutes: int, writer: bool) -> None:
        try:
            self.stats.start_sprint(minutes)
        except ValueError as exc:
            self.notify(str(exc), severity="warning")
            return
        self._sprint_writer = writer and not self._writer_mode
        if self._sprint_writer:
            self.writer_mode()
        self._refresh_stats()
        self.update_status()
        self.notify(f"Sprint started: {minutes} minutes", timeout=2)

    def _sprint_tick(self) -> None:
        if self.stats is None or self.stats.sprint is None:
            return
        state = self.stats.sprint_state()
        if state["done"]:
            self._end_sprint(cancelled=False)
        else:
            self._refresh_stats()
            self.update_status()

    def _end_sprint(self, cancelled: bool) -> None:
        if self.stats is None or self.stats.sprint is None:
            return
        self.save_current()   # the last words count
        rec = self.stats.finish_sprint(cancelled=cancelled)
        if getattr(self, "_sprint_writer", False):
            self._sprint_writer = False
            if self._writer_mode:
                self.writer_mode()
        self._refresh_stats()
        self.update_status()
        if rec is not None:
            verb = "stopped" if cancelled else "done"
            self.notify(f"Sprint {verb}: {rec['minutes']} minutes, {writing_stats.signed(rec['words'])} words "
                        f"(today {writing_stats.signed(self._stats_brief['todayWords'])})", timeout=12)

    def open_stats(self) -> None:
        """Action · Session stats: today, this session, the last 30 days, streak."""
        if self.stats is None:
            return
        self.save_current()
        summary = self.stats.summary(project_words=self._project_words)
        self.push_screen(StatsScreen(writing_stats.format_summary(summary)))

    def _recount_project_words(self) -> None:
        if self.project is None:
            self._project_words = 0
            return
        total = 0
        for path in self.project.counted_scenes():  # front matter isn't the book
            try:
                text = path.read_text(encoding="utf-8")
                total += _word_count(text, self._originals(text, path))
            except OSError:
                continue
        self._project_words = total

    def on_unmount(self) -> None:
        if self._save_timer is not None:
            self._save_timer.stop()
        if self._spell_timer is not None:
            self._spell_timer.stop()
        if self._sync_timer is not None:
            self._sync_timer.stop()
        if self._sprint_timer is not None:
            self._sprint_timer.stop()
        try:
            self._write_to_disk()  # final flush; UI updates skipped on teardown
        except Exception:
            pass
        if self.stats is not None:
            try:
                self.stats.close()
            except OSError:
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
        """A manuscript scene (in a part, unparted or unplaced), not a note."""
        return self.project is not None and self.project.is_scene_path(path)

    def _sync_mention_names(self) -> None:
        """Plain-name recognition applies to scenes, not entity notes."""
        if self._editor is not None:
            is_scene = self._is_scene(self.current_path)
            self._editor.mention_names = self._all_names() if is_scene else []
            self._editor.scene_mode = is_scene

    def _entities_changed(self) -> None:
        """Names/aliases changed: earlier scenes may now mention them."""
        self.idx.rebuild(self.project)
        self.reload_entities()
        self.refresh_sidebar()
        self.editor.refresh_links()

    def sidebar_rows(self) -> list[tuple[str, str, Path | None]]:
        """Scenes for the sidebar: unparted first, then each part under its
        header, then Unplaced. A project without parts is just the scenes."""
        project = self.project
        rows: list[tuple[str, str, Path | None]] = [
            ("scene", project.scene_title(p), p) for p in project.part_scenes(None)]
        for part in project.list_parts():
            rows.append(("part", project.part_title(part), part))
            rows += [("scene", project.scene_title(p), p)
                     for p in project.part_scenes(part)]
        unplaced = project.list_unplaced()
        if unplaced:
            rows.append(("header", "Unplaced scenes", None))
            rows += [("scene", project.scene_title(p), p) for p in unplaced]
        return rows

    def refresh_sidebar(self) -> None:
        self.sidebar.collection_source = self._scene_collection_names
        self.sidebar.set_scenes(self.sidebar_rows(), self.project.unit)
        self.sidebar.set_entities(
            [(f"{e.name} [{e.type}]", e.path) for e in self.entities if e.path]
        )

    def open_file(self, path: Path) -> None:
        self.save_current()
        self.current_path = path
        self._dirty = False
        self._sync_mention_names()
        self._refresh_snapshot_time()
        text = path.read_text(encoding="utf-8")
        self._stats_seen(text)
        self._skip_touch = True
        self.editor.load_text(text)
        self.editor.refresh_links()
        self.refresh_comments(reload=True)
        self.editor.set_misspellings(None)
        self.schedule_spelling(0.05)
        self.editor.focus()
        self.update_status()

    def _write_to_disk(self) -> None:
        if self.current_path is None or self._editor is None:
            return
        text = self._editor.text
        if self._is_scene(self.current_path) and snapshots.auto_enabled():
            try:  # the daily safety net must never block a save
                snapshots.ensure_daily(self.project, self.current_path, text)
            except Exception:
                pass
        write_atomic(self.current_path, text)
        self._stats_record(text)
        if self._is_scene(self.current_path) and \
                comments.sidecar_path(self.project.root, self.current_path).is_file():
            try:  # comments follow edited passages: refresh what they quote
                comments.reanchor(self.project.root, self.current_path, text)
            except Exception:
                pass
        if self.current_path in (style_path(self.project),
                                 spelling.project_dictionary_path(self.project)) \
                or research_notes.is_research_path(self.project, self.current_path):
            return  # the style guide, dictionary and research notes aren't in the link index
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
        self._refresh_snapshot_time()
        self._schedule_sync()
        self._recount_project_words()
        self.update_panel_for_cursor()
        self.update_status()
        if explicit:
            self.notify("Saved", timeout=1)

    def on_text_area_changed(self) -> None:
        self._dirty = True
        if self._skip_touch:
            self._skip_touch = False
        elif self.stats is not None:
            self.stats.touch()
        self.editor.refresh_links()
        self.refresh_comments()
        self._spelling_edited()
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
        if self._stats_brief:
            b = self._stats_brief
            goal = f"{writing_stats.signed(b['todayWords'])} / {b['target']:,} today" if b["target"] else f"{writing_stats.signed(b['todayWords'])} today"
            parts.insert(3, goal)
            if b["streak"]:
                parts.insert(4, f"streak {b['streak']}")
            if b["sprint"]:
                sp = b["sprint"]
                parts.insert(1, f"SPRINT {writing_stats.clock(sp['remaining'])} ({writing_stats.signed(sp['words'])})")
        parts.insert(1, f"Draft {self.project.draft}")
        if self._sync is not None:
            parts.insert(2, self._sync.label)
        if self._snapshot_at is not None and self._is_scene(self.current_path):
            parts.append(f"Snapshot {snapshots.ago(self._snapshot_at)}")
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

    # -- spell check ---------------------------------------------------------------------

    def _spell_active(self) -> bool:
        """Spelling applies to scenes only (not notes, style.md, dictionary)."""
        return (self.project is not None and self._editor is not None
                and self._is_scene(self.current_path))

    def _spell_on(self) -> bool:
        return bool(user_settings.get("spellcheck", True)) and self._spell_active()

    def _accepted(self) -> spelling.AcceptedTerms:
        return spelling.accepted_terms(
            self.project, entities=self.entities,
            ignored=self._spell_ignores.for_project(self.project.root))

    def _spelling_edited(self) -> None:
        """Keep underlines honest between checks: a line-count change shifts
        every later row, so clear; otherwise the edited row is dropped."""
        if not self._spell_on():
            return
        lines = self.editor.document.line_count
        if lines != self._spell_lines:
            self.editor.set_misspellings(None)
        else:
            row = self.editor.cursor_location[0]
            self.editor._spelling.pop(row, None)
        self.schedule_spelling()

    def schedule_spelling(self, delay: float = 0.6) -> None:
        if self._spell_timer is not None:
            self._spell_timer.stop()
        self._spell_timer = self.set_timer(delay, self._spell_start)

    def _spell_start(self) -> None:
        if self._editor is None:
            return
        if not self._spell_on():
            self.editor.set_misspellings(None)
            return
        text = self.editor.text
        accepted = self._accepted()
        self._spell_lines = self.editor.document.line_count

        def work() -> None:
            found = spelling.check(text, accepted)
            try:
                self.call_from_thread(self._spell_apply, text, found)
            except Exception:  # app shutting down
                pass

        self.run_worker(work, thread=True, exclusive=True, group="spell")

    def _spell_apply(self, text: str, found) -> None:
        if self._editor is not None and self._editor.text == text \
                and self._spell_on():
            self.editor.set_misspellings(found)

    def refresh_spelling(self) -> None:
        """Re-check right now (after a dictionary change)."""
        if self._editor is None:
            return
        if not self._spell_on():
            self.editor.set_misspellings(None)
            return
        self._spell_lines = self.editor.document.line_count
        self.editor.set_misspellings(
            spelling.check(self.editor.text, self._accepted()))

    def toggle_spellcheck(self) -> None:
        on = not user_settings.get("spellcheck", True)
        user_settings.set("spellcheck", on)
        self.refresh_spelling()
        self.notify(f"Spell check {'on' if on else 'off'}", timeout=2)

    def action_spell_next(self) -> None:
        """f6: jump to the next misspelling after the cursor and fix it."""
        if not self._spell_active():
            self.notify("Spell check applies to scenes", timeout=2)
            return
        text = self.editor.text
        found = spelling.check(text, self._accepted())
        if not found:
            self.notify("No misspellings", timeout=2)
            return
        offset = rowcol_to_offset(text, *self.editor.cursor_location)
        m = next((m for m in found if m.start >= offset), found[0])
        self.editor.move_cursor(offset_to_rowcol(text, m.end))
        word = text[m.start:m.end]

        def _done(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            kind, value = result
            self._spell_resolve(m, word, kind, value)

        self.push_screen(SpellScreen(word, spelling.suggestions(word)), _done)

    def _spell_resolve(self, m, word: str, kind: str, value: str) -> None:
        if kind == "replace":
            if self.editor.text[m.start:m.end] == word:
                self.editor.replace_offsets(m.start, m.end, value)
            return
        if kind == "project":
            spelling.add_to_dictionary(
                spelling.project_dictionary_path(self.project), word)
            self.notify(f'Added "{word}" to the project dictionary', timeout=2)
        elif kind == "personal":
            spelling.add_to_dictionary(spelling.personal_dictionary_path(), word)
            self.notify(f'Added "{word}" to your dictionary', timeout=2)
        elif kind == "ignore":
            self._spell_ignores.add(self.project.root, word)
        self.refresh_spelling()

    def add_selection_to_dictionary(self) -> None:
        """Palette: selected word or phrase -> project dictionary."""
        if self.project is None or self._editor is None:
            return
        term = " ".join(self.editor.selected_text.split())
        if not term:
            self.notify("Select a word or phrase first", timeout=2)
            return
        added = spelling.add_to_dictionary(
            spelling.project_dictionary_path(self.project), term)
        self.notify(f'Added "{term}" to the project dictionary' if added
                    else f'"{term}" is already in the dictionary', timeout=2)
        self.refresh_spelling()

    def open_project_dictionary(self) -> None:
        if self.project is None:
            return
        self.save_current()
        self.open_file(spelling.ensure_dictionary(
            spelling.project_dictionary_path(self.project)))

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
        if self.project.is_unplaced(path):  # unplaced scenes read as their own run
            scenes = self.project.list_unplaced()
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
        self.refresh_spelling()

    # -- AI: alias finder ----------------------------------------------------

    _MODEL_DEFAULTS = MODEL_DEFAULTS

    def _ai_model(self, kind: str) -> str:
        """kind: fast | strong | writing (see ai.client.resolve_model)."""
        return resolve_model(kind, self.project.meta if self.project else None)

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
        scene_text = scenemeta.blank(drafts.blank_pending(self.editor.text))
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
        self._stats_accepted(pending, body)
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
        if self._is_scene(self.current_path):  # whole-scene operation: keep a way back
            snapshots.create(self.project, self.current_path,
                             "before-accept-all" if accept else "before-reject-all",
                             self.editor.text)
            self._refresh_snapshot_time()
        for p in reversed(found):  # back to front so offsets hold
            if accept:
                text = self.editor.text
                self._stats_accepted(p, text[p.body_start:p.body_end])
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
                                originals=self._originals(text),
                                voice_samples=select_voice_samples(
                                    self.project, self.current_path, text,
                                    self.entities))
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
            insert, a, b = drafts.prepare_draft(text, mode, body, pos, pos)
            self.editor.replace_offsets(a, b, insert)
            return
        if text[start:end] != original:
            first = text.find(original)
            if first == -1 or text.find(original, first + 1) != -1:
                self.notify("The text changed while drafting — draft discarded",
                            severity="warning", timeout=5)
                return
            start, end = first, first + len(original)
        # sidecar first: a marker must never exist without its original
        draft_id = drafts.fresh_id(self.project.root, text)
        drafts.add_original(self.project.root, self.current_path, draft_id,
                            original)
        insert, a, b = drafts.prepare_draft(text, mode, body, start, end,
                                            draft_id)
        self.editor.replace_offsets(a, b, insert)

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
                learn_style, samples, self._ai_model("writing"),
                manuscript=manuscript_stats(self.project))
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
        """Established canon per entity (core.continuity.canon_map)."""
        return canon_map(self.entities)

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
        self.push_screen(ContinuityScreen(results), self._continuity_closed)

    def on_waive_toggled(self, message: WaiveToggled) -> None:
        if self.project is None:
            return
        if message.waived:
            save_waiver(self.project.root, message.waiver_key, message.scene)
        else:
            remove_waiver(self.project.root, message.waiver_key)

    def _continuity_closed(self, contradiction) -> None:
        """Enter in the report jumps to the evidence line (report closes)."""
        if contradiction is not None:
            self._jump_to(contradiction)

    def on_jump_to_contradiction(self, message: JumpToContradiction) -> None:
        self._jump_to(message.contradiction)

    def restore_waived(self) -> None:
        """Palette: un-waive this scene's continuity issues."""
        if self.project is None or not self._is_scene(self.current_path):
            self.notify("Open a scene first", severity="warning")
            return
        rel = str(self.current_path.relative_to(self.project.root))
        n = clear_scene_waivers(self.project.root, rel)
        if n:
            self.notify(f"Restored {n} waived continuity issue(s) — they will"
                        " be reported again by the next check", timeout=4)
        else:
            self.notify("No waived continuity issues recorded for this scene",
                        timeout=3)

    restore_waived_issues = restore_waived

    def _jump_to(self, c) -> None:
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
            part = self.project.default_part_for_new(self.current_path)
            path = self.project.next_scene_path(title, part)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {title}\n\n", encoding="utf-8")
            self.refresh_sidebar()
            self.open_file(path)

        self.push_screen(NamePrompt(f"New {self.project.unit} title:"), _create)

    # -- scene organization -----------------------------------------------------

    def _current_scene_path(self) -> Path | None:
        """The open file, if it's a manuscript scene (not an entity note)."""
        if self.project is None or self.current_path is None:
            return None
        if self.project.is_scene_path(self.current_path):
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
        unit = self.project.unit

        def _delete(ok: bool) -> None:
            if not ok:
                return
            rel = str(path.relative_to(self.project.root))
            self.project.delete_scene(path)  # to the Trash, with its draft sidecar
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
            self.notify(f"Moved '{title}' to the Trash", timeout=2)

        self.push_screen(
            ConfirmScreen(
                f"Move {unit} '{title}' to the Trash?\n"
                "You can restore it from Action · Open Trash.",
                confirm_label="Move to Trash"),
            _delete,
        )

    def _move_scene(self, delta: int) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self.save_current()
        new_path = self.project.move_scene(path, delta)
        if new_path is None:
            self.notify("Already at the edge of its part", severity="warning")
            return
        self.current_path = new_path  # content unchanged; only the name moved
        self.idx.rebuild(self.project)
        self.refresh_sidebar()
        self.update_status()
        self.notify(f"Moved to {new_path.name}", timeout=1)

    def move_scene_up(self) -> None:
        self._move_scene(-1)

    def move_scene_down(self) -> None:
        self._move_scene(1)

    # -- parts, unplaced scenes, trash ------------------------------------------

    def _part_options(self, include_top: bool = False) -> list[tuple[str, object]]:
        options: list[tuple[str, object]] = [
            (self.project.part_title(p), p) for p in self.project.list_parts()]
        if include_top:
            options.append(("(no part - top level)", "top"))
        return options

    def _with_part(self, prompt: str, then) -> None:
        """Ask which part, defaulting to the open scene's part; run then(part)."""
        options = self._part_options()
        if not options:
            self.notify("There are no parts yet - Action · New part",
                        severity="warning")
            return
        path = self._current_scene_path()
        current = self.project.part_of(path) if path else None
        self.push_screen(ChoiceScreen(prompt, options, initial=current),
                         lambda chosen: chosen is not None and then(chosen))

    def _structure_changed(self, reopen: Path | None = None) -> None:
        """After parts/scenes moved on disk: refresh index and sidebar and
        keep the open scene open at its (possibly new) path."""
        if reopen is not None:
            self.current_path = reopen
        self.idx.rebuild(self.project)
        self.refresh_sidebar()
        self.update_status()

    def new_part_prompt(self) -> None:
        def _create(title: str | None) -> None:
            if not title:
                return
            try:
                part = self.project.new_part(title)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self.refresh_sidebar()
            self.notify(f"Created part '{self.project.part_title(part)}'", timeout=2)

        self.push_screen(NamePrompt("New part title:"), _create)

    def rename_part_prompt(self) -> None:
        def _go(part: Path) -> None:
            def _rename(title: str | None) -> None:
                if not title:
                    return
                self.project.rename_part(part, title)
                self.refresh_sidebar()

            self.push_screen(
                NamePrompt(f"Rename part '{self.project.part_title(part)}' to:"), _rename)

        self._with_part("Rename which part?", _go)

    def _move_part(self, delta: int) -> None:
        def _go(part: Path) -> None:
            self.save_current()
            parts = self.project.list_parts()
            j = parts.index(part) + delta
            neighbor = parts[j] if 0 <= j < len(parts) else None
            new = self.project.move_part(part, delta)
            if new is None:
                self.notify("Already at the edge", severity="warning")
                return
            cur, reopen = self.current_path, None
            if cur is not None and cur.parent == part:
                reopen = new / cur.name
            elif cur is not None and neighbor is not None and cur.parent == neighbor:
                prefix = part.name.split("-", 1)[0]
                reopen = neighbor.with_name(
                    f"{prefix}-{neighbor.name.split('-', 1)[1]}") / cur.name
            self._structure_changed(reopen)
            self.notify(f"Moved part '{self.project.part_title(new)}'", timeout=1)

        self._with_part("Move which part?", _go)

    def move_part_up(self) -> None:
        self._move_part(-1)

    def move_part_down(self) -> None:
        self._move_part(1)

    def delete_part_confirm(self) -> None:
        def _go(part: Path) -> None:
            title = self.project.part_title(part)
            if self.project.part_scenes(part):
                self.notify(f"'{title}' still has scenes - move them out first",
                            severity="warning")
                return

            def _delete(ok: bool) -> None:
                if not ok:
                    return
                try:
                    self.project.delete_part(part)
                except ValueError as exc:
                    self.notify(str(exc), severity="warning")
                    return
                self.refresh_sidebar()
                self.notify(f"Deleted part '{title}'", timeout=2)

            self.push_screen(ConfirmScreen(f"Delete the empty part '{title}'?"), _delete)

        self._with_part("Delete which (empty) part?", _go)

    def _place_in(self, path: Path, prompt: str, done: str) -> None:
        """Ask for a part (or the top level) and move *path* to its end."""
        def _go(chosen) -> None:
            self.save_current()
            part = None if chosen == "top" else chosen
            new = self.project.move_scene_to_part(path, part)
            self._structure_changed(new if path == self.current_path else None)
            self.notify(done, timeout=2)

        self.push_screen(ChoiceScreen(prompt, self._part_options(include_top=True)),
                         lambda chosen: chosen is not None and _go(chosen))

    def move_scene_to_part_prompt(self) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self._place_in(path, f"Move '{self.project.scene_title(path)}' to which part?",
                       "Moved (at the end of the part)")

    def unplace_scene_action(self) -> None:
        """Move the open scene out of the book into Unplaced Scenes."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        if self.project.is_unplaced(path):
            self.notify("Already unplaced - use Action · Place scene in the book",
                        severity="warning")
            return
        self.save_current()
        new = self.project.unplace_scene(path)
        self._structure_changed(new)
        self.notify("Moved to Unplaced scenes (not counted in the book)", timeout=2)

    def place_scene_action(self) -> None:
        """Bring the open unplaced scene back into the book."""
        path = self._current_scene_path()
        if path is None or not self.project.is_unplaced(path):
            self.notify("Open an unplaced scene first", severity="warning")
            return
        self._place_in(path, "Place in which part?", "Placed in the book")

    def open_trash(self) -> None:
        items = self.project.list_trash()

        def _act(result) -> None:
            if result is None:
                return
            what, name = result
            if what == "restore":
                new = self.project.restore_scene(name)
                if new.parent == inspiration.inspiration_dir(self.project):   # reference images: no sidebar row
                    self.notify("Restored the inspiration image", timeout=3)
                elif research_notes.is_research_path(self.project, new):   # not indexed, no sidebar row
                    self.notify(f"Restored the research note to {new.relative_to(self.project.root)}", timeout=3)
                else:
                    self.idx.rebuild(self.project)
                    self.refresh_sidebar()
                    self.notify("Restored to "
                                f"{new.relative_to(self.project.manuscript_dir)}", timeout=2)
                self.open_trash()
            elif what == "delete":
                item = next((i for i in items if i.name == name), None)

                def _forever(ok: bool) -> None:
                    if ok:
                        self.project.delete_forever(name)
                    self.open_trash()

                self.push_screen(ConfirmScreen(
                    f"Delete '{item.title if item else name}' forever?\n"
                    "This cannot be undone.", confirm_label="Delete forever"), _forever)
            elif what == "empty":
                def _empty(ok: bool) -> None:
                    if ok:
                        n = self.project.empty_trash()
                        self.notify(f"Emptied the Trash ({n})", timeout=2)
                    self.open_trash()

                self.push_screen(ConfirmScreen(
                    f"Delete all {len(items)} item(s) in the Trash forever?\n"
                    "This cannot be undone.", confirm_label="Empty Trash"), _empty)

        self.push_screen(TrashScreen(items), _act)

    # -- snapshots (Wave 2.1) -----------------------------------------------------

    def _refresh_snapshot_time(self) -> None:
        path = self.current_path
        self._snapshot_at = (snapshots.latest_time(self.project, path)
                             if path is not None and self._is_scene(path) else None)

    def snapshot_scene_prompt(self) -> None:
        """Scene · Snapshot scene: a verbatim copy you can compare and restore."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return

        def _take(label: str | None) -> None:
            if label is None:
                return
            snapshots.create(self.project, path, label, self.editor.text)
            self._refresh_snapshot_time()
            self.update_status()
            self.notify("Snapshot taken" + (f": {label}" if label else ""), timeout=2)

        self.push_screen(LabelPrompt("Snapshot this scene (the text as it is now)"), _take)

    def snapshot_all_prompt(self) -> None:
        """Action · Snapshot all scenes: one label for every scene."""
        if self.project is None:
            return
        self.save_current()

        def _take(label: str | None) -> None:
            if label is None:
                return
            n = snapshots.snapshot_all(self.project, label)
            self._refresh_snapshot_time()
            self.update_status()
            self.notify(f"Snapshot taken of {n} scene(s)", timeout=2)

        self.push_screen(LabelPrompt("Snapshot every scene in the project"), _take)

    def open_snapshots(self) -> None:
        """Scene · Snapshots: list, compare, restore, delete."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self.save_current()
        text = self.editor.text
        words = _word_count(text, self._originals(text))
        items = snapshots.list_snapshots(self.project, path)
        title = self.project.scene_title(path)

        def _act(result) -> None:
            if result is None:
                return
            what, name = result
            if what == "new":
                self.snapshot_scene_prompt()
            elif what == "all":
                self.snapshot_all_prompt()
            elif what == "compare":
                self._compare_snapshot(path, name)
            elif what == "restore":
                self._confirm_restore(path, name)
            elif what == "delete":
                snap = next((s for s in items if s.name == name), None)

                def _gone(ok: bool) -> None:
                    if ok:
                        snapshots.delete(self.project, path, name)
                        self._refresh_snapshot_time()
                        self.update_status()
                    self.open_snapshots()

                self.push_screen(ConfirmScreen(
                    f"Delete the snapshot '{label_text(snap.label) if snap else name}'?\n"
                    "This cannot be undone.", confirm_label="Delete"), _gone)

        self.push_screen(SnapshotsScreen(title, items, words), _act)

    def _compare_snapshot(self, path: Path, name: str) -> None:
        old = snapshots.read_text(self.project, path, name)
        segs = snapshots.diff_words(old, self.editor.text)
        snap = next((x for x in snapshots.list_snapshots(self.project, path) if x.name == name), None)
        title = (f"{label_text(snap.label)}, {snap.when.strftime('%Y-%m-%d %H:%M')} ({snapshots.ago(snap.when)})"
                 if snap else name)

        def _back(result) -> None:
            if result == "restore":
                self._confirm_restore(path, name)
            else:
                self.open_snapshots()

        self.push_screen(CompareScreen(title, segs), _back)

    def _confirm_restore(self, path: Path, name: str) -> None:
        def _go(ok: bool) -> None:
            if not ok:
                self.open_snapshots()
                return
            self.save_current()
            # the current text is snapshotted first (before-restore), then replaced
            text = snapshots.restore(self.project, path, name, self.editor.text)
            self._stats_seen(text)  # restoring is not writing
            self.editor.load_text(text)
            self.save_current()
            self.editor.refresh_links()
            self.schedule_spelling(0.05)
            self.notify("Snapshot restored; the text from before is kept as "
                        "'before a restore'", timeout=4)

        self.push_screen(ConfirmScreen(
            "Replace this scene with the snapshot?\n"
            "The text as it is now is snapshotted first, so you can come back to it.",
            confirm_label="Restore"), _go)

    # -- git sync (Wave 2.3): the status is read-only; the actions run only when asked ----

    def _schedule_sync(self) -> None:
        """Refresh the git status 2.5 s after a save (trailing; one timer at a time)."""
        if self._sync_timer is None and self.project is not None:
            self._sync_timer = self.set_timer(2.5, self._sync_timer_fired)

    def _sync_timer_fired(self) -> None:
        self._sync_timer = None
        self.refresh_sync()

    @work(exclusive=True, group="sync-status")
    async def refresh_sync(self) -> None:
        if self.project is None:
            return
        root = self.project.root
        try:
            status = await asyncio.to_thread(sync.status, root)
        except Exception:  # a failing git must never disturb writing
            status = None
        self._sync = status
        self.update_status()

    def sync_visible(self, method: str) -> bool:
        """Which sync actions the palette lists: commit/push only inside a
        repository (push only with a remote), init only when there is none."""
        st = self._sync
        if method == "sync_commit_prompt":
            return st is not None
        if method == "sync_push_confirm":
            return st is not None and st.can_push
        if method == "sync_init_confirm":
            return st is None and sync.git_available() and self.project is not None \
                and not sync.in_repository(self.project.root)
        return True

    def _sync_run(self, fn, done) -> None:
        """Run a blocking git call off the UI thread; report the outcome."""
        async def go() -> None:
            try:
                result = await asyncio.to_thread(fn)
            except ValueError as exc:
                self.notify(str(exc), severity="warning", timeout=5)
            except Exception as exc:  # GitError and friends: git's own words
                self.notify(str(exc), severity="error", timeout=8)
            else:
                done(result)
            self.refresh_sync()

        self.run_worker(go(), group="sync-action")

    def sync_commit_prompt(self) -> None:
        """Action · Commit changes: message pre-filled, commits this project folder only."""
        if self.project is None or self._sync is None:
            self.notify("This project is not in a git repository", severity="warning")
            return
        if self._sync.changes == 0:
            self.notify("Nothing to commit: everything is already committed", timeout=3)
            return
        self.save_current()
        root = self.project.root
        st = self._sync

        def _go(message: str | None) -> None:
            if message is None:
                return
            self._sync_run(lambda: sync.commit(root, message),
                           lambda summary: self.notify(f"Committed: {summary}", timeout=4))

        self.push_screen(MessagePrompt(
            f"Commit {st.changes} change(s) in this project folder (enter commits, esc cancels)",
            sync.default_message(st)), _go)

    def sync_push_confirm(self) -> None:
        """Action · Push: asks first, naming the remote. Never forces."""
        st = self._sync
        if self.project is None or st is None or not st.can_push:
            self.notify("No remote is configured for this project", severity="warning")
            return
        root = self.project.root
        url = sync.remote_url(root, st.remote)
        where = f"{st.remote} ({url})" if url else st.remote

        def _go(ok: bool) -> None:
            if ok:
                self.notify("Pushing…", timeout=2)
                self._sync_run(lambda: sync.push(root), lambda s: self.notify(s, timeout=4))

        self.push_screen(ConfirmScreen(
            f"Push branch '{st.branch}' to the remote {where}?\n"
            "This sends your manuscript there. It is never forced.",
            confirm_label="Push"), _go)

    def sync_init_confirm(self) -> None:
        """Action · Initialize git for this project."""
        if self.project is None:
            return
        root = self.project.root

        def _go(ok: bool) -> None:
            if ok:
                self._sync_run(lambda: sync.init(root), lambda _: self.notify(
                    "This folder is now a git repository. Nothing is committed yet.", timeout=4))

        self.push_screen(ConfirmScreen(
            "Turn this project folder into a git repository?\n"
            "A .gitignore hides the index cache (.lorewrite/). Nothing is committed or pushed.",
            confirm_label="Initialize"), _go)

    def start_new_draft(self) -> None:
        """Action · Start new draft: snapshot every scene as end-of-draft-N, count up."""
        if self.project is None:
            return
        n = self.project.draft

        def _go(ok: bool) -> None:
            if not ok:
                return
            self.save_current()
            try:
                new = self.project.start_new_draft()
            except OSError as exc:
                self.notify(f"Could not start a new draft: {exc}", severity="error")
                return
            self._refresh_snapshot_time()
            self.update_status()
            self.notify(f"Draft {n} is saved as snapshots ('end of draft {n}'). "
                        f"You are now on draft {new}.", timeout=5)

        self.push_screen(ConfirmScreen(
            f"Start draft {n + 1}?\n"
            f"Every scene is snapshotted now as 'end of draft {n}'; your text is not changed.",
            confirm_label="Start new draft"), _go)

    def edit_details(self) -> None:
        """Scene · Edit details: POV, place, purpose, status, target."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        characters = [e.name for e in self.entities if e.type == "character"]
        places = [e.name for e in self.entities if e.type == "place"]

        def _save(values: dict | None) -> None:
            if values is None:
                return
            new = scenemeta.set_details(self.editor.text, **values)
            if new != self.editor.text:
                self.editor.load_text(new)  # the buffer owns the file: edit it, then save
                self.save_current()
                self.editor.refresh_links()
            self.notify("Details saved", timeout=1)

        self.push_screen(DetailsScreen(self.editor.text, characters, places), _save)

    # -- research notes (Wave 3.3): plain Markdown in research/, not scenes, not indexed ---------

    def new_research_note_prompt(self) -> None:
        def _create(title: str | None) -> None:
            if not title:
                return
            try:
                path = research_notes.new_note(self.project, title)
            except ValueError as exc:
                self.notify(str(exc), severity="warning")
                return
            self.open_file(path)

        self.push_screen(NamePrompt("New research note title:"), _create)

    def new_research_from_link_prompt(self) -> None:
        def _create(url: str | None) -> None:
            if not url:
                return
            try:
                path = research_notes.note_from_url(self.project, url)
            except ValueError as exc:
                self.notify(str(exc), severity="warning")
                return
            self.open_file(path)
            self.notify("Saved the link as a research note (the page is not downloaded)", timeout=3)

        self.push_screen(NamePrompt("Link (https://...):"), _create)

    def delete_research_note_confirm(self) -> None:
        path = self.current_path
        if path is None or not research_notes.is_research_path(self.project, path):
            self.notify("Open a research note first", severity="warning")
            return

        def _go(ok: bool) -> None:
            if not ok:
                return
            self._dirty = False          # a pending autosave must not bring the file back
            self.current_path = None
            research_notes.delete_note(self.project, path)   # to the Trash
            scenes = self.project.list_scenes()
            if scenes:
                self.open_file(scenes[0])
            self.notify("Research note moved to the Trash (Action · Open Trash restores it)", timeout=3)

        self.push_screen(ConfirmScreen(
            f"Move the research note '{research_notes.title_of(path)}' to the Trash?\n"
            "You can restore it from Action · Open Trash.", confirm_label="Move to Trash"), _go)

    # -- the assistant (chat + research), Wave 3.3 / 3.4 -------------------------------------

    def open_assistant(self, mode: str = "chat") -> None:
        """Action · Ask the assistant (ctrl+r inside switches to research mode)."""
        if self.project is None:
            return
        self.save_current()
        self._assistant_screen = AssistantScreen(
            self._chat_messages, mode,
            AssistantOps(self._assistant_submit,
                         lambda sid: self.open_file(self.project.root / sid),
                         self._save_reply_to_notes))
        self.push_screen(self._assistant_screen, self._assistant_closed)

    def _assistant_closed(self, result) -> None:
        if result == "history":
            self.open_chat_history()
        elif result == "new":
            self._new_chat()
            self.open_assistant()

    def _new_chat(self) -> None:
        self._chat_messages = []
        self._chat_id = None

    def _save_chat(self) -> None:
        """Keep the conversation (.assistant/chats/) after each answer."""
        rows = [{"id": f"m{i}", "role": m.role, "text": m.text,
                 **({"sources": [{"id": s, "title": t} for s, t in m.sources]} if m.sources else {})}
                for i, m in enumerate(self._chat_messages) if not m.error]
        if not rows:
            return
        scope = "scene" if self._current_scene_path() is not None else "project"
        try:
            self._chat_id = chats.save(self.project, self._chat_id, rows, scope).id
        except (OSError, ValueError) as exc:
            self.notify(f"Could not save the conversation: {exc}", severity="warning")

    def _save_reply_to_notes(self, prompt: str, reply: str) -> None:
        try:
            path = research_notes.append_assistant_note(self.project, prompt, reply)
        except (OSError, ValueError) as exc:
            self.notify(str(exc), severity="warning")
            return
        self.notify(f"Saved to {path.relative_to(self.project.root)}", timeout=3)

    def open_chat_history(self) -> None:
        """The saved conversations: open, rename, delete, or start a new one."""
        def _act(result) -> None:
            if result is None:
                self.open_assistant()
                return
            what, cid = result
            if what == "new":
                self._new_chat()
                self.open_assistant()
            elif what == "open":
                try:
                    chat = chats.load(self.project, cid)
                except (OSError, ValueError) as exc:
                    self.notify(str(exc), severity="warning")
                    self.open_chat_history()
                    return
                self._chat_id = chat.id
                self._chat_messages = [
                    ChatMsg(m["role"], m["text"], sources=[(s["id"], s["title"]) for s in m.get("sources", [])])
                    for m in chat.messages]
                self.open_assistant()
            elif what == "rename":
                def _rename(title: str | None) -> None:
                    if title:
                        try:
                            chats.rename(self.project, cid, title)
                        except (OSError, ValueError) as exc:
                            self.notify(str(exc), severity="warning")
                    self.open_chat_history()

                current = next((c.title for c in chats.list_chats(self.project) if c.id == cid), "")
                self.push_screen(NamePrompt("Rename the conversation:", current), _rename)
            elif what == "delete":
                def _gone(ok: bool) -> None:
                    if ok:
                        chats.delete(self.project, cid)
                        if self._chat_id == cid:
                            self._chat_id = None       # the next answer starts a new saved chat
                    self.open_chat_history()

                self.push_screen(ConfirmScreen("Delete this saved conversation?\n"
                                               "Answers you saved to notes stay in your notes.",
                                               confirm_label="Delete conversation"), _gone)

        self.push_screen(ChatsScreen(chats.list_chats(self.project), self._chat_id), _act)

    def open_research_question(self) -> None:
        self.open_assistant("research")

    def _assistant_submit(self, screen: AssistantScreen, prompt: str, mode: str) -> None:
        history = [{"role": m.role, "text": m.text} for m in screen.messages[:-1] if not m.error]
        entities = list(self.entities)
        canon = self._canon_map()
        try:
            if mode == "research":
                context, hits = research_context(self.project, entities, canon, prompt)
                sources = [(str(h.note.path.relative_to(self.project.root)), h.note.title) for h in hits]
            else:
                sources = []
                scene = self._current_scene_path()
                if scene is not None:
                    text = self.editor.text
                    context = build_context(text, self._cursor_offset(), entities, canon,
                                            load_style(self.project),
                                            originals=self._originals(text))
                else:
                    titles = [self.project.scene_title(p) for p in self.project.list_scenes()]
                    context = build_project_context(titles, entities, canon, load_style(self.project))
        except ValueError as exc:
            screen.add_message(ChatMsg("assistant", str(exc), error=True))
            return
        screen.set_busy(True)
        self._assistant_worker(screen, prompt, mode, context, sources, history,
                               self._ai_model("writing"))

    @work(exclusive=True, group="assistant")
    async def _assistant_worker(self, screen, prompt, mode, context, sources, history, model) -> None:
        calls = LEDGER.count()
        fn = research_answer if mode == "research" else ask_writer
        try:
            reply = await asyncio.to_thread(fn, prompt, context, model, history=history)
            msg = ChatMsg("assistant", reply, sources=sources)
        except Exception as exc:
            msg = ChatMsg("assistant", f"That request failed ({exc}). Nothing was changed.", error=True)
        cost = self._cost_note(calls)
        if screen.is_attached:
            screen.set_busy(False)
            screen.add_message(msg)
        else:                        # the window was closed while the model worked: keep the answer
            self._chat_messages.append(msg)
        self._save_chat()
        if cost:
            self.notify(f"Answered{cost}", timeout=3)

    # -- brainstorm (Wave 4.3): "unstuck" ideas, never written into the prose ----------------

    def brainstorm(self) -> None:
        """Action · Brainstorm: 3-5 ideas from the scene around the cursor, the canon and the
        style guide, in a list with Draft from this / Save to notes."""
        if self.project is None:
            return
        entities, canon = list(self.entities), self._canon_map()
        scene = self._current_scene_path()
        if scene is not None:
            text = self.editor.text
            offset = self._cursor_offset()
            context = build_context(text, offset, entities, canon, load_style(self.project),
                                    originals=self._originals(text))
        else:
            offset = 0
            titles = [self.project.scene_title(p) for p in self.project.list_scenes()]
            context = build_project_context(titles, entities, canon, load_style(self.project))
        self.notify("Brainstorming…", timeout=3)
        self._brainstorm_worker(context, self._ai_model("writing"), scene, offset)

    @work(exclusive=True, group="brainstorm")
    async def _brainstorm_worker(self, context, model, scene, offset) -> None:
        calls = LEDGER.count()
        try:
            ideas = await asyncio.to_thread(brainstorm_ideas, context, model)
        except Exception as exc:
            self.notify(f"Brainstorm failed: {exc}", severity="error", timeout=6)
            return
        cost = self._cost_note(calls)
        self._show_ideas(ideas, scene, offset)
        if cost:
            self.notify(f"Ideas ready{cost}", timeout=3)

    def _show_ideas(self, ideas: list[str], scene: Path | None, offset: int) -> None:
        def _act(result) -> None:
            if result is None:
                return
            what, idea = result
            if what == "save":
                try:
                    where = research_notes.append_assistant_note(
                        self.project, f"Brainstorm idea - {self.project.scene_title(scene)}"
                        if scene else "Brainstorm idea", idea)
                    self.notify(f"Saved to {where.relative_to(self.project.root)}", timeout=3)
                except (OSError, ValueError) as exc:
                    self.notify(f"Could not save the idea: {exc}", severity="error")
                self._show_ideas(ideas, scene, offset)
            elif what == "draft":
                if scene is None or self.current_path != scene:
                    self.notify("Open the scene you want to draft into first", severity="warning")
                    return
                pos = min(offset, len(self.editor.text))
                self.push_screen(
                    PromptScreen("What should the AI write here? (edit the idea if you like)", idea),
                    lambda instruction: self._start_generate("draft", instruction, pos, pos))

        self.push_screen(BrainstormScreen(ideas), _act)

    # -- comments (Wave 3.2): author notes in .comments/, never in the prose ----------

    def refresh_comments(self, reload: bool = False) -> None:
        """Underline the open scene's open comments (faintly) in the editor."""
        if self._editor is None:
            return
        path = self._current_scene_path()
        if path is None:
            self._comment_list, self._comment_scene = [], None
            self._editor.set_comments([])
            return
        if reload or self._comment_scene != path:
            self._comment_list = comments.load(self.project.root, path)
            self._comment_scene = path
        if not self._comment_list:
            self._editor.set_comments([])
            return
        live = [c for c in self._comment_list if not c.resolved]
        self._editor.set_comments([(p.start, p.end) for p in comments.place(
            self._editor.text, live) if not p.detached])

    def add_comment_prompt(self) -> None:
        """Scene · Add comment on selection."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        if not self.editor.selected_text.strip():
            self.notify("Select the passage to comment on first", severity="warning")
            return
        text = self.editor.text
        a, b = self.editor.selection
        lo = min(rowcol_to_offset(text, *a), rowcol_to_offset(text, *b))
        hi = max(rowcol_to_offset(text, *a), rowcol_to_offset(text, *b))

        def _add(body: str | None) -> None:
            if not body:
                return
            try:
                comments.add(self.project.root, path, text, lo, hi, body)
            except ValueError as exc:
                self.notify(str(exc), severity="warning")
                return
            self.refresh_comments(reload=True)
            self.notify("Comment added (it is kept beside the scene, not in the text)", timeout=3)

        self.push_screen(NamePrompt("Comment:"), _add)

    def open_comments(self, focus: str | None = None) -> None:
        """Scene · Comments: list, jump, resolve, edit, delete."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self.save_current()
        text = self.editor.text
        placed = comments.place(text, comments.load(self.project.root, path))
        lines = {p.comment.id: (None if p.start is None else text.count("\n", 0, p.start))
                 for p in placed}
        index = next((i for i, p in enumerate(placed) if p.comment.id == focus), 0)
        by_id = {p.comment.id: p for p in placed}

        def _act(result) -> None:
            if result is None:
                self.refresh_comments(reload=True)
                return
            what, cid = result
            root = self.project.root
            if what == "jump":
                p = by_id[cid]
                self.refresh_comments(reload=True)
                self.editor.selection = Selection(offset_to_rowcol(text, p.start),
                                                  offset_to_rowcol(text, p.end))
                self.editor.focus()
            elif what == "resolve":
                comments.resolve(root, path, cid, not by_id[cid].comment.resolved)
                self.open_comments(cid)
            elif what == "edit":
                def _edit(body: str | None) -> None:
                    if body:
                        comments.edit(root, path, cid, body)
                    self.open_comments(cid)

                self.push_screen(NamePrompt("Comment:", by_id[cid].comment.body), _edit)
            elif what == "delete":
                def _gone(ok: bool) -> None:
                    if ok:
                        comments.delete(root, path, cid)
                    self.open_comments(None if ok else cid)

                self.push_screen(ConfirmScreen(
                    "Delete this comment?\nThe text it was about is not touched.",
                    confirm_label="Delete comment"), _gone)

        self.push_screen(CommentsScreen(placed, lines, self.project.scene_title(path), index),
                         _act)

    def _scene_collection_names(self) -> dict[Path, list[str]]:
        """{scene: its collection names}, for the sidebar's #collection filter."""
        out: dict[Path, list[str]] = {}
        for c in coll.list_collections(self.project):
            for p in c.scenes:
                out.setdefault(p, []).append(c.name)
        return out

    def open_collections(self, focus: str | None = None) -> None:
        """Scene · Collections: tick the open scene's collections; add, rename,
        recolour or delete them. (Sidebar filter: type #name.)"""
        self.save_current()
        path = self._current_scene_path()
        members = (set(scenemeta.details(self.editor.text)["collections"])
                   if path is not None else None)
        items = coll.list_collections(self.project)
        index = next((i for i, c in enumerate(items) if c.name == focus), 0)
        title = self.project.scene_title(path) if path is not None else None

        def _act(result) -> None:
            if result is None:
                return
            what, name = result
            if what == "new":
                def _create(new: str | None) -> None:
                    if new:
                        try:
                            name = coll.create(self.project, new)
                        except ValueError as exc:
                            self.notify(str(exc), severity="warning")
                            name = None
                        self.refresh_sidebar()
                        self.open_collections(name)
                    else:
                        self.open_collections()

                self.push_screen(NamePrompt("New collection name:"), _create)
            elif what == "toggle":
                names = [n for n in (members or ()) if n != name]
                if name not in (members or ()):
                    names.append(name)
                new = scenemeta.set_details(self.editor.text, collections=names)
                if new != self.editor.text:
                    self.editor.load_text(new)  # the buffer owns the file: edit it, then save
                    self.save_current()
                    self.editor.refresh_links()
                self.open_collections(name)
            elif what == "recolor":
                found = coll.find(self.project, name)
                at = coll.COLORS.index(found.color) if found and found.color in coll.COLORS else -1
                coll.recolor(self.project, name, coll.COLORS[(at + 1) % len(coll.COLORS)])
                self.open_collections(name)
            elif what == "rename":
                def _rename(new: str | None) -> None:
                    if new:
                        try:
                            self._collection_op(lambda: coll.rename(self.project, name, new))
                            name_after = new
                        except (ValueError, LookupError) as exc:
                            self.notify(str(exc), severity="warning")
                            name_after = name
                        self.open_collections(name_after)
                    else:
                        self.open_collections(name)

                self.push_screen(NamePrompt(f"Rename '{name}' to:"), _rename)
            elif what == "delete":
                found = coll.find(self.project, name)
                count = len(found.scenes) if found else 0

                def _gone(ok: bool) -> None:
                    if ok:
                        self._collection_op(lambda: coll.delete(self.project, name))
                    self.open_collections()

                self.push_screen(ConfirmScreen(
                    f"Delete the collection '{name}'?\nIt is taken off its {count} "
                    f"scene{'' if count == 1 else 's'}; no scene is deleted.",
                    confirm_label="Delete collection"), _gone)

        self.push_screen(CollectionsScreen(items, members, title, index, self.project.unit),
                         _act)

    def _collection_op(self, run) -> None:
        """Rename / delete rewrite member scenes on disk: the open one is
        saved first and re-read afterwards."""
        self.save_current()
        changed = run()
        if self.current_path in changed:  # re-read it; open_file would save the stale buffer over it
            self.editor.load_text(self.current_path.read_text(encoding="utf-8"))
            self._dirty = False
            self.editor.refresh_links()
        self.refresh_sidebar()

    def toggle_unit(self) -> None:
        unit = "chapter" if self.project.unit == "scene" else "scene"
        self.project.update_manuscript_settings(unit=unit)
        self.refresh_sidebar()
        self.notify(f"Labels now say '{unit}'", timeout=2)

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
