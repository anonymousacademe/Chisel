"""LinkedTextArea: a TextArea that visually highlights [[wiki-links]].

Plain-text mentions of known names (see core.links.find_mentions) are colored
quietly, and the brackets of explicit links are faded so they don't distract.
Pending AI drafts (core.drafts) are shown in a distinct italic color with their
marker comments faded, and ``{{expand: ...}}`` markers are faded like brackets.

Highlighting works by post-processing rendered lines (see SPEC §6: this touches
Textual internals, so everything is wrapped in a fallback — any internal API
drift degrades to a plain TextArea, never a crash).
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Callable

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widgets import TextArea

from textual.binding import Binding

from ..core import scenemeta
from ..core.drafts import find_expand_markers, find_pending
from ..core.links import find_all_links, offset_to_rowcol

RESOLVED_STYLE = Style(color="cyan", bold=True, underline=True)
UNRESOLVED_STYLE = Style(color="orange1", bold=True, underline=True)
MENTION_STYLE = Style(color="cyan")
BRACKET_STYLE = Style(dim=True)
AI_STYLE = Style(color="green", bgcolor="grey19", italic=True)
MISSPELLED_STYLE = Style(underline=True, color="red")
COMMENT_STYLE = Style(underline=True, dim=True)  # faint: an author note is attached here


def _style_cell_range(
    segments: list[Segment], start: int, end: int, style: Style
) -> list[Segment]:
    """Apply *style* over the cell range [start, end) across segments."""
    out: list[Segment] = []
    pos = 0
    for seg in segments:
        n = seg.cell_length
        seg_start, seg_end = pos, pos + n
        pos = seg_end
        if n == 0 or seg.is_control or seg_end <= start or seg_start >= end:
            out.append(seg)
            continue
        current = seg
        left_cut = max(start - seg_start, 0)
        right_cut = min(end - seg_start, n)
        if left_cut > 0:
            left, current = current.split_cells(left_cut)
            out.append(left)
        mid_width = right_cut - left_cut
        if mid_width < current.cell_length:
            mid, right = current.split_cells(mid_width)
        else:
            mid, right = current, None
        if mid.text:
            combined = (mid.style + style) if mid.style else style
            out.append(Segment(mid.text, combined))
        else:
            out.append(mid)
        if right is not None:
            out.append(right)
    return out


class LinkedTextArea(TextArea):
    """TextArea with [[wiki-link]] highlighting and pending-AI-draft marking."""

    # TextArea binds f7 to select-all, which would shadow accepting a draft;
    # select-all moves to f5. f6 (select-line in TextArea) is the spell check.
    BINDINGS = [
        Binding("f6", "app.spell_next", "Next misspelling", show=False),
        Binding("f7", "app.accept_draft", "Accept AI draft", show=False),
        Binding("f8", "app.reject_draft", "Reject AI draft", show=False),
        Binding("f5", "select_all", "Select all", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("soft_wrap", True)
        kwargs.setdefault("show_line_numbers", True)
        super().__init__(*args, **kwargs)
        try:
            self.language = "markdown"
        except Exception:
            pass  # tree-sitter unavailable: plain text, links still highlight
        #: callable(target: str) -> bool, set by the app
        self.link_resolver: Callable[[str], bool] | None = None
        #: entity names/aliases recognized without brackets; set by the app
        #: (empty for entity notes, where only explicit links count)
        self.mention_names: list[str] = []
        self.scene_mode = False  # scene file: details block faded, not scanned
        # row -> [(start_col, end_col, kind, target)], kind in
        # "bracket" | "link" | "mention" | "ai" | "marker"
        self._spans: dict[int, list[tuple[int, int, str, str]]] = {}
        # row -> [(start_col, end_col)] misspelled words (lowest priority)
        self._spelling: dict[int, list[tuple[int, int]]] = {}
        self.misspelled_style = MISSPELLED_STYLE
        self.comment_style = COMMENT_STYLE
        # row -> [(start_col, end_col)] passages with an open comment (lowest priority)
        self._comments: dict[int, list[tuple[int, int]]] = {}
        # overridable by the app to follow the system theme
        self.resolved_style = RESOLVED_STYLE
        self.unresolved_style = UNRESOLVED_STYLE
        self.mention_style = MENTION_STYLE
        self.bracket_style = BRACKET_STYLE
        self.ai_style = AI_STYLE

    def refresh_links(self) -> None:
        """Re-scan the document for links and repaint."""
        text = self.text
        spans: dict[int, list[tuple[int, int, str, str]]] = {}

        lines = text.split("\n")

        def add_range(start: int, end: int, kind: str) -> None:
            """Add a span for [start, end), split per row (drafts span lines)."""
            row, col = offset_to_rowcol(text, start)
            end_row, end_col = offset_to_rowcol(text, end)
            for r in range(row, end_row + 1):
                lo = col if r == row else 0
                hi = end_col if r == end_row else len(lines[r])
                if hi > lo:
                    spans.setdefault(r, []).append((lo, hi, kind, ""))

        # AI spans first so mention/link colors layer on top of the AI italic
        for p in find_pending(text):
            add_range(p.start, p.body_start, "marker")
            add_range(p.body_start, p.body_end, "ai")
            add_range(p.body_end, p.end, "marker")
        for marker in find_expand_markers(text):
            add_range(marker.start, marker.end, "marker")
        if self.scene_mode:  # scene details: faded, and never scanned for names
            head = scenemeta.body_offset(text)
            if head:
                add_range(0, head, "marker")
        scan = scenemeta.blank(text) if self.scene_mode else text
        for link in find_all_links(scan, self.mention_names):
            row, col = offset_to_rowcol(text, link.start)
            _, end_col = offset_to_rowcol(text, link.end)
            row_spans = spans.setdefault(row, [])
            if not link.explicit:
                row_spans.append((col, end_col, "mention", link.target))
                continue
            # [[Name]] / [[Name|display]]: fade everything but the shown text
            inner = text[link.start + 2:link.end - 2]
            shown = col + 2 + (inner.index("|") + 1 if "|" in inner else 0)
            row_spans.append((col, shown, "bracket", link.target))
            row_spans.append((shown, end_col - 2, "link", link.target))
            row_spans.append((end_col - 2, end_col, "bracket", link.target))
        self._spans = spans
        # TextArea caches rendered strips without link state in the cache key;
        # clear it so resolution changes (e.g. a new entity note turning an
        # orange link cyan) repaint immediately. Private API, hence defensive.
        try:
            self._line_cache.clear()
        except AttributeError:
            pass
        self.refresh()

    def set_misspellings(self, misspellings) -> None:
        """Underline these core.spelling.Misspelling spans (None/[] clears)."""
        text = self.text
        spans: dict[int, list[tuple[int, int]]] = {}
        # line start offsets once: offset_to_rowcol per word is O(n) each
        starts = [0] + [i + 1 for i, c in enumerate(text) if c == "\n"]
        for m in misspellings or []:
            row = bisect_right(starts, m.start) - 1
            col = m.start - starts[row]
            spans.setdefault(row, []).append((col, col + (m.end - m.start)))
        if spans == self._spelling:
            return
        self._spelling = spans
        try:
            self._line_cache.clear()
        except AttributeError:
            pass
        self.refresh()

    def set_comments(self, ranges: list[tuple[int, int]]) -> None:
        """Underline faintly the (start, end) text offsets that carry an open
        comment ([] clears)."""
        text = self.text
        lines = text.split("\n")
        starts = [0] + [i + 1 for i, c in enumerate(text) if c == "\n"]
        spans: dict[int, list[tuple[int, int]]] = {}
        for start, end in ranges:
            row = bisect_right(starts, start) - 1
            end_row = bisect_right(starts, end) - 1
            for r in range(row, end_row + 1):
                lo = start - starts[r] if r == row else 0
                hi = end - starts[r] if r == end_row else len(lines[r])
                if hi > lo:
                    spans.setdefault(r, []).append((lo, hi))
        if spans == self._comments:
            return
        self._comments = spans
        try:
            self._line_cache.clear()
        except AttributeError:
            pass
        self.refresh()

    def replace_offsets(self, start: int, end: int, new: str) -> None:
        """Replace text[start:end] with *new*, keeping undo history."""
        text = self.text
        self.replace(new, offset_to_rowcol(text, start),
                     offset_to_rowcol(text, end), maintain_selection_offset=False)

    # -- private rendering hook (with hard fallback) ------------------------

    def _render_line(self, y: int) -> Strip:
        strip = super()._render_line(y)
        try:
            return self._apply_link_styles(strip, y)
        except Exception:
            return strip

    def _apply_link_styles(self, strip: Strip, y: int) -> Strip:
        if not self._spans and not self._spelling and not self._comments:
            return strip
        y_offset = y + int(self.scroll_offset.y)
        line_info = self.wrapped_document._offset_to_line_info[y_offset]
        if line_info is None:
            return strip
        line_index, section_offset = line_info
        row_spans = [(lo, hi, "comment", "")
                     for lo, hi in self._comments.get(line_index, ())]
        row_spans += [(lo, hi, "misspelled", "")
                      for lo, hi in self._spelling.get(line_index, ())]
        row_spans += self._spans.get(line_index, [])
        if not row_spans:
            return strip
        line = self.get_line(line_index).plain

        wrap_offsets = self.wrapped_document.get_offsets(line_index)
        section_start = wrap_offsets[section_offset - 1] if section_offset > 0 else 0
        section_end = (
            wrap_offsets[section_offset]
            if section_offset < len(wrap_offsets)
            else len(line)
        )
        gutter = self.gutter_width if self.show_line_numbers else 0
        cell = lambda c: len(line[:c].expandtabs(self.indent_width))  # noqa: E731

        segments = list(strip)
        styled = False
        for col, end_col, kind, target in row_spans:
            if end_col <= section_start or col >= section_end or end_col <= col:
                continue
            lo = max(col, section_start)
            hi = min(end_col, section_end)
            cell_lo = gutter + cell(lo) - cell(section_start)
            cell_hi = gutter + cell(hi) - cell(section_start)
            if kind == "comment":
                style = self.comment_style
            elif kind == "misspelled":
                style = self.misspelled_style
            elif kind in ("bracket", "marker"):
                style = self.bracket_style
            elif kind == "ai":
                style = self.ai_style
            elif kind == "mention":
                style = self.mention_style
            elif self.link_resolver and self.link_resolver(target):
                style = self.resolved_style
            else:
                style = self.unresolved_style
            segments = _style_cell_range(segments, cell_lo, cell_hi, style)
            styled = True
        if not styled:
            return strip
        return Strip(segments, cell_length=strip.cell_length)
