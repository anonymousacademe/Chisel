"""Settings screen: AI key + models (global), editor prefs (per project)."""

from __future__ import annotations

import shutil
import subprocess

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static

from ..ai.client import clear_api_key, get_api_key, set_api_key
from ..core import settings as user_settings


class SettingsScreen(ModalScreen[None]):
    """Adjust app settings. Changes apply on Save; esc discards."""

    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, project=None) -> None:
        super().__init__()
        self._project = project  # None: launched without a project open

    def compose(self) -> ComposeResult:
        with Vertical(id="settings"):
            yield Static("Settings", id="settings-title")
            yield Label("AI (OpenRouter)", classes="settings-heading")
            yield Label("", id="key-status")
            yield Button("Set API key…", id="set-key")
            yield Button("Clear API key", id="clear-key", variant="error")
            yield Label("Fast model (linking):")
            yield Input(id="fast-model")
            yield Label("Strong model (continuity):")
            yield Input(id="strong-model")
            if self._project is not None:
                yield Label("Editor (this project)", classes="settings-heading")
                yield Label("Side padding (0–8):")
                yield Input(id="padding")
                yield Checkbox("Line numbers", id="line-numbers")
            yield Button("Save", id="save", variant="primary")
            yield Label("enter a field, then Save · esc closes without saving",
                        id="settings-hint")

    def on_mount(self) -> None:
        self._refresh_key_status()
        self.query_one("#fast-model", Input).value = user_settings.get(
            "fast_model", "")
        self.query_one("#strong-model", Input).value = user_settings.get(
            "strong_model", "")
        if self._project is not None:
            prefs = self._project.editor_settings()
            self.query_one("#padding", Input).value = str(prefs["padding"])
            self.query_one("#line-numbers", Checkbox).value = prefs[
                "line_numbers"]

    def _refresh_key_status(self) -> None:
        key = get_api_key()
        if key:
            masked = f"…{key[-4:]}" if len(key) > 4 else "set"
            self.query_one("#key-status", Label).update(
                f"API key: set ({masked})")
        else:
            self.query_one("#key-status", Label).update(
                "API key: not set — AI features won't work")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "set-key":
            self.app.push_screen(
                KeyPrompt(),
                lambda key: self._store_key(key),
            )
        elif bid == "clear-key":
            clear_api_key()
            self._refresh_key_status()
        elif bid == "save":
            self._save()
            self.dismiss(None)

    def _store_key(self, key: str | None) -> None:
        if not key:
            return
        try:
            set_api_key(key)
        except Exception as exc:
            self.app.notify(
                f"Keyring unavailable ({exc}). Set OPENROUTER_API_KEY "
                "in the environment instead.",
                severity="error", timeout=8,
            )
        self._refresh_key_status()

    def _save(self) -> None:
        fast = self.query_one("#fast-model", Input).value.strip()
        strong = self.query_one("#strong-model", Input).value.strip()
        user_settings.set("fast_model", fast or None)
        user_settings.set("strong_model", strong or None)
        if self._project is not None:
            raw = self.query_one("#padding", Input).value.strip()
            try:
                padding = int(raw)
            except ValueError:
                padding = None
            self._project.update_editor_settings(
                padding=padding,
                line_numbers=self.query_one("#line-numbers", Checkbox).value,
            )
        self.app.notify("Settings saved", timeout=2)

    def action_close(self) -> None:
        self.dismiss(None)


def read_system_clipboard() -> str | None:
    """System clipboard text via wl-paste/xclip/xsel, or None if unavailable."""
    for cmd in (["wl-paste", "--no-newline"],
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"]):
        if not shutil.which(cmd[0]):
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return result.stdout
    return None


class _ClipboardInput(Input):
    """Input whose ctrl+v reads the system clipboard.

    Textual's Input binds ctrl+v to its app-local clipboard, which is empty
    unless something was copied inside lorewrite; terminal paste
    (ctrl+shift+v) already works via bracketed paste.
    """

    def action_paste(self) -> None:
        text = read_system_clipboard()
        if text is None:
            super().action_paste()
            return
        lines = text.splitlines()
        start, end = self.selection
        self.replace(lines[0].strip() if lines else "", start, end)


class KeyPrompt(ModalScreen[str | None]):
    """Password-style single input for the API key."""

    CSS = """
    KeyPrompt { align: center middle; }
    KeyPrompt > * { width: 60; }
    KeyPrompt Label { padding: 1; background: $surface; border: solid $primary; }
    KeyPrompt Input { border: solid $primary; }
    """

    def compose(self) -> ComposeResult:
        yield Label("OpenRouter API key (paste with ctrl+v), then enter:")
        yield _ClipboardInput(password=True, id="key-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)

    def key_escape(self) -> None:
        self.dismiss(None)
