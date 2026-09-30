"""First-run tour: five pages, one concept each. Shown once (settings.tour_seen)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, Markdown

PAGES = [
    """\
# 1/5 — Your project is just files

A lorewrite project is a plain folder:

  project.toml       settings
  manuscript/        your scenes, numbered 01-, 02-, ...
  entities/          notes on characters, places, ...

Everything is Markdown. You can read, edit, git-commit, or back up
the folder with any tool — lorewrite never locks you in.
""",
    """\
# 2/5 — Writing

The center pane is your editor. It understands Markdown:
# headings, *italic*, **bold** all render as you type.

Your work autosaves constantly. The bottom status bar shows
the file, saved/modified state, word count, and cursor position.

  ctrl+n   new scene        f11   writer mode (hide everything else)
  ctrl+s   save now         ?     all keybindings
""",
    """\
# 3/5 — Links: the heart of lorewrite

No brackets needed. Select a character or place name the first
time you write it and press ctrl+j to make a note for it. From
then on every mention of that name (or its aliases) is colored.

Put the cursor on a name and press ctrl+j to open its note.
The right panel previews the note under your cursor and lists
every scene that mentions it (backlinks).
""",
    """\
# 4/5 — AI writing help (optional)

Bring an OpenRouter key (ctrl+p -> Settings) and the AI can write
for you - but never on its own. Everything it writes is shown in
color and stays a draft until you accept it.

  ctrl+g   draft at the cursor - or expand {{expand: a note}} -
           or, with text selected, rewrite it in your style
  f7 / f8  accept / reject the draft under the cursor
  ctrl+l   find other names your prose uses for your characters

ctrl+p -> "learn style guide" teaches it your voice first.
""",
    """\
# 5/5 — Finding things

  ctrl+p            the palette: scenes, entities, actions — just type
  alt+left/right    previous / next scene
  ctrl+b            hide/show the sidebar

The left sidebar lists scenes and entities; the filter box at the
top narrows them as you type.

That's everything. Press esc and go write something.
""",
]


class TourScreen(ModalScreen[None]):
    """Paged onboarding modal. Space/enter/right advances, esc closes."""

    BINDINGS = [
        Binding("escape", "close"),
        Binding("space", "next"),
        Binding("enter", "next"),
        Binding("right", "next"),
        Binding("left", "back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._page = 0

    def compose(self) -> ComposeResult:
        yield Markdown(PAGES[0], id="tour-page")
        yield Label("space: next · esc: close", id="tour-hint")

    def _show(self) -> None:
        self.query_one("#tour-page", Markdown).update(PAGES[self._page])

    def action_next(self) -> None:
        if self._page >= len(PAGES) - 1:
            self.dismiss(None)
        else:
            self._page += 1
            self._show()

    def action_back(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._show()

    def action_close(self) -> None:
        self.dismiss(None)
