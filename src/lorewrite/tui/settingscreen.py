"""Settings screen: AI key + models (global), editor prefs (per project)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from ..ai.client import (
    DEFAULT_FAST_MODEL,
    DEFAULT_STRONG_MODEL,
    ModelInfo,
    clear_api_key,
    get_api_key,
    list_models,
    set_api_key,
)
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
            with Horizontal(classes="model-row"):
                yield Input(id="fast-model", placeholder=DEFAULT_FAST_MODEL)
                yield Button("Choose…", id="pick-fast")
            yield Label("Strong model (continuity):")
            with Horizontal(classes="model-row"):
                yield Input(id="strong-model", placeholder=DEFAULT_STRONG_MODEL)
                yield Button("Choose…", id="pick-strong")
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
        elif bid in ("pick-fast", "pick-strong"):
            field = self.query_one(
                "#fast-model" if bid == "pick-fast" else "#strong-model", Input)

            def _picked(model_id: str | None) -> None:
                if model_id:
                    field.value = model_id

            self.app.push_screen(ModelPicker(field.value.strip()), _picked)
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


def _price(value: float | None) -> str:
    if value is None:
        return "?"
    return "free" if value == 0 else f"${value:.2f}"


def model_label(m: ModelInfo) -> Text:
    """One picker row; Text so brackets in names aren't eaten as markup."""
    row = Text(m.name)
    row.append(f"  {m.id}", style="dim")
    detail = f"  {_price(m.prompt_per_m)} in / {_price(m.completion_per_m)} out per M"
    if m.context_length:
        detail += f" · {m.context_length // 1000}k ctx"
    row.append(detail, style="dim italic")
    return row


class ModelPicker(ModalScreen[str | None]):
    """Filterable list of OpenRouter models. Dismisses with a model id or None.

    Only models supporting structured outputs are listed (every lorewrite AI
    call requires them).
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    ModelPicker { align: center middle; }
    #picker { width: 100; height: 80%; border: solid $primary; background: $surface; padding: 0 1; }
    #picker-filter { margin: 1 0 0 0; }
    #picker-list { height: 1fr; }
    #picker-status { color: $text-muted; }
    """

    def __init__(self, current: str = "") -> None:
        super().__init__()
        self._current = current
        self._models: list[ModelInfo] = []
        self._shown: list[ModelInfo] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Input(placeholder="type to filter (name or id)", id="picker-filter")
            yield Label("Loading models from OpenRouter…", id="picker-status")
            yield OptionList(id="picker-list")

    def on_mount(self) -> None:
        self.query_one("#picker-filter", Input).focus()
        self._load()

    @work(exclusive=True)
    async def _load(self) -> None:
        status = self.query_one("#picker-status", Label)
        try:
            self._models = await asyncio.to_thread(list_models)
        except Exception as exc:
            status.update(Text(
                f"Couldn't load models ({exc}). Type a model id in Settings instead."))
            return
        self._refilter()

    def _refilter(self) -> None:
        needle = self.query_one("#picker-filter", Input).value.strip().lower()
        self._shown = [m for m in self._models
                       if needle in m.id.lower() or needle in m.name.lower()]
        options = self.query_one("#picker-list", OptionList)
        options.clear_options()
        options.add_options([Option(model_label(m), id=m.id) for m in self._shown])
        ids = [m.id for m in self._shown]
        if self._current in ids and not needle:
            options.highlighted = ids.index(self._current)
        elif ids:
            options.highlighted = 0
        self.query_one("#picker-status", Label).update(
            f"{len(self._shown)} of {len(self._models)} models · "
            "↑/↓ move · enter choose · esc cancel")

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._models:
            self._refilter()

    def on_key(self, event) -> None:
        # Arrow keys drive the list while typing stays in the filter box.
        if event.key in ("up", "down", "pageup", "pagedown"):
            options = self.query_one("#picker-list", OptionList)
            {"up": options.action_cursor_up,
             "down": options.action_cursor_down,
             "pageup": options.action_page_up,
             "pagedown": options.action_page_down}[event.key]()
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        options = self.query_one("#picker-list", OptionList)
        if options.highlighted is not None and self._shown:
            self.dismiss(self._shown[options.highlighted].id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
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
