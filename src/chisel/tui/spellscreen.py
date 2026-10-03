"""f6: fix one misspelled word (suggestions, add to a dictionary, ignore)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, Static

MAX_SUGGESTIONS = 5


class SpellScreen(ModalScreen["tuple[str, str] | None"]):
    """Dismisses with ("replace", word) | ("project", "") | ("personal", "")
    | ("ignore", "") or None (cancel)."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "pick(1)", "Replace with 1"),
        Binding("a", "choose('project')", "Add to project dictionary"),
        Binding("p", "choose('personal')", "Add to personal dictionary"),
        Binding("i", "choose('ignore')", "Ignore this session"),
        *[Binding(str(n), f"pick({n})", show=False)
          for n in range(1, MAX_SUGGESTIONS + 1)],
    ]

    def __init__(self, word: str, suggestions: list[str]) -> None:
        super().__init__()
        self._word = word
        self._suggestions = suggestions[:MAX_SUGGESTIONS]

    def compose(self) -> ComposeResult:
        yield Label(Text(f'Misspelled: "{self._word}"'), id="spell-header")
        body = Text()
        if self._suggestions:
            for n, s in enumerate(self._suggestions, 1):
                body.append(f"{n}  {s}\n")
        else:
            body.append("no suggestions\n", style="dim")
        yield Static(body, id="spell-suggestions")
        yield Label("1-5 / enter replace · a add to project dictionary · "
                    "p add to my dictionary · i ignore · esc cancel",
                    id="spell-hint")

    def action_pick(self, n: int) -> None:
        if 1 <= n <= len(self._suggestions):
            self.dismiss(("replace", self._suggestions[n - 1]))

    def action_choose(self, what: str) -> None:
        self.dismiss((what, ""))

    def action_cancel(self) -> None:
        self.dismiss(None)
