"""The Export manuscript form (M7): format, layout, page size, headings, a few
switches and the live summary. Dismisses with the chosen ExportOptions or None.
Self-contained: its CSS is here, not in app.py."""

from __future__ import annotations

from dataclasses import replace

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label, Select

from ..core.export.manuscript import ExportOptions

PAGE_LABEL = {"trade": "Trade 6 x 9 in", "a5": "A5", "letter": "US Letter", "a4": "A4"}


class ExportScreen(ModalScreen["ExportOptions | None"]):
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "export", "Export")]

    DEFAULT_CSS = """
    ExportScreen { align: center middle; }
    #export-box { width: 84; height: auto; max-height: 96%; background: $surface;
                  border: solid $primary; padding: 1 2; }
    #export-header { text-style: bold; }
    #export-summary { color: $text; padding-bottom: 1; }
    #export-scroll { height: auto; max-height: 22; }
    .export-row { height: auto; }
    .export-label { color: $text-muted; width: 24; padding-top: 1; }
    .export-row Select, .export-row Input { width: 1fr; }
    #export-box Checkbox { border: none; height: 1; padding: 0; margin: 0 0 0 24; background: transparent; }
    #export-warn { color: $warning; padding-top: 1; width: 100%; }
    #export-hint { color: $text-muted; padding-top: 1; }
    """

    def __init__(self, info: dict, options: ExportOptions, summary_line: str,
                 notes: list[str], unit: str = "scene") -> None:
        super().__init__()
        self._info, self._opts, self._unit = info, options, unit
        self._summary, self._notes = summary_line, notes
        self._formats = {f["key"]: f for f in info["formats"]}
        self._layouts = {l["name"]: l for l in info["layouts"]}

    # -- helpers ---------------------------------------------------------------

    def _layout(self, name: str | None = None):
        return self._layouts.get(name or self._opts.layout) or next(iter(self._layouts.values()), None)

    def _format_choices(self):
        return [(f["label"] + ("" if f["available"] else f" ({f['reason']})"), f["key"])
                for f in self._info["formats"]]

    def _page_choices(self):
        layout = self._layout()
        return [(PAGE_LABEL.get(p, p), p) for p in (layout["page_sizes"] if layout else ())]

    # -- layout --------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        o, word = self._opts, self._unit.capitalize()
        layout = self._layout()
        with Vertical(id="export-box"):
            yield Label("Export manuscript", id="export-header")
            yield Label(self._summary, id="export-summary")
            with VerticalScroll(id="export-scroll"):
                with Horizontal(classes="export-row"):
                    yield Label("Format", classes="export-label")
                    yield Select(self._format_choices(), value=o.format, allow_blank=False, id="export-format")
                with Horizontal(classes="export-row"):
                    yield Label("Layout (PDF)", classes="export-label")
                    yield Select([(l["label"], l["name"]) for l in self._layouts.values()] or [("-", "book")],
                                 value=layout["name"] if layout else "book", allow_blank=False,
                                 id="export-layout", disabled=not self._layouts)
                pages = self._page_choices() or [("-", "trade")]
                with Horizontal(classes="export-row"):
                    yield Label("Page size (PDF)", classes="export-label")
                    yield Select(pages, value=o.page_size if o.page_size in {v for _, v in pages} else pages[0][1],
                                 allow_blank=False, id="export-page")
                with Horizontal(classes="export-row"):
                    yield Label(f"{word} headings", classes="export-label")
                    yield Select([(f"“{word} 3”", "words"), ("Numbers", "numbers"),
                                  ("Titles only", "titles-only")], value=o.numbering,
                                 allow_blank=False, id="export-numbering")
                yield Checkbox("Table of contents", o.toc, id="export-toc")
                yield Checkbox("Include front matter", o.include_front_matter, id="export-front")
                yield Checkbox(f"Run {self._unit}s on with a break ornament", o.continuous, id="export-continuous")
                yield Checkbox("Include pending AI drafts", o.include_drafts, id="export-drafts")
                with Horizontal(classes="export-row"):
                    yield Label("Copyright line (PDF)", classes="export-label")
                    yield Input(o.copyright, placeholder="First edition, 2026", id="export-copyright")
            if self._notes:
                yield Label("\n".join(self._notes), id="export-warn")
            yield Label("tab next · ctrl+s export · esc cancel · saved in exports/", id="export-hint")

    def on_mount(self) -> None:
        self.query_one("#export-format", Select).focus()
        self._sync_pdf_fields()

    def _sync_pdf_fields(self) -> None:
        pdf = self.query_one("#export-format", Select).value == "pdf" and bool(self._layouts)
        for wid in ("export-layout", "export-page", "export-copyright"):
            self.query_one(f"#{wid}").disabled = not pdf
        layout = self._layout(self.query_one("#export-layout", Select).value) if pdf else None
        self.query_one("#export-toc", Checkbox).disabled = bool(layout) and not layout["toc"]

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "export-layout":
            layout = self._layout(str(event.value))
            page = self.query_one("#export-page", Select)
            keep = page.value
            page.set_options([(PAGE_LABEL.get(p, p), p) for p in layout["page_sizes"]])
            page.value = keep if keep in layout["page_sizes"] else layout["page_sizes"][0]
        self._sync_pdf_fields()

    # -- result ----------------------------------------------------------------------

    def action_export(self) -> None:
        q = lambda wid, kind: self.query_one(f"#{wid}", kind)  # noqa: E731
        fmt = str(q("export-format", Select).value)
        if not self._formats[fmt]["available"]:
            self.notify(self._formats[fmt]["reason"].capitalize(), severity="warning")
            return
        layout = str(q("export-layout", Select).value) if self._layouts else self._opts.layout
        self.dismiss(replace(
            self._opts, format=fmt, layout=layout, page_size=str(q("export-page", Select).value),
            numbering=str(q("export-numbering", Select).value),
            toc=q("export-toc", Checkbox).value, include_front_matter=q("export-front", Checkbox).value,
            continuous=q("export-continuous", Checkbox).value,
            include_drafts=q("export-drafts", Checkbox).value,
            copyright=q("export-copyright", Input).value.strip()))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_export()

    def action_cancel(self) -> None:
        self.dismiss(None)
