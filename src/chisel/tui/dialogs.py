"""Small modal dialogs shared by ChiselApp and its mixins: a name prompt, a confirmation and an
entity-type picker. (Re-exported from ``chisel.tui.app``, where tests import them.)"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


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
