"""LinkedTextArea: a TextArea that visually highlights [[wiki-links]].

Highlighting works by post-processing rendered lines (see SPEC §6: this touches
Textual internals, so everything is wrapped in a fallback — any internal API
drift degrades to a plain TextArea, never a crash).
"""

from __future__ import annotations

from typing import Callable

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widgets import TextArea

from ..core.links import Link, find_links, offset_to_rowcol

RESOLVED_STYLE = Style(color="cyan", bold=True, underline=True)
UNRESOLVED_STYLE = Style(color="orange1", bold=True, underline=True)


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
    """TextArea with [[wiki-link]] highlighting."""

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
        self._links: list[Link] = []
        # overridable by the app to follow the system theme
        self.resolved_style = RESOLVED_STYLE
        self.unresolved_style = UNRESOLVED_STYLE

    def refresh_links(self) -> None:
        """Re-scan the document for links and repaint."""
        self._links = find_links(self.text)
        # TextArea caches rendered strips without link state in the cache key;
        # clear it so resolution changes (e.g. a new entity note turning an
        # orange link cyan) repaint immediately. Private API, hence defensive.
        try:
            self._line_cache.clear()
        except AttributeError:
            pass
        self.refresh()

    # -- private rendering hook (with hard fallback) ------------------------

    def _render_line(self, y: int) -> Strip:
        strip = super()._render_line(y)
        try:
            return self._apply_link_styles(strip, y)
        except Exception:
            return strip

    def _apply_link_styles(self, strip: Strip, y: int) -> Strip:
        if not self._links:
            return strip
        y_offset = y + int(self.scroll_offset.y)
        line_info = self.wrapped_document._offset_to_line_info[y_offset]
        if line_info is None:
            return strip
        line_index, section_offset = line_info
        line = self.get_line(line_index).plain

        wrap_offsets = self.wrapped_document.get_offsets(line_index)
        section_start = wrap_offsets[section_offset - 1] if section_offset > 0 else 0
        section_end = (
            wrap_offsets[section_offset]
            if section_offset < len(wrap_offsets)
            else len(line)
        )
        gutter = self.gutter_width if self.show_line_numbers else 0

        text = self.text
        segments = list(strip)
        styled = False
        for link in self._links:
            row, col = offset_to_rowcol(text, link.start)
            _, end_col = offset_to_rowcol(text, link.end)
            if row != line_index or end_col <= section_start or col >= section_end:
                continue
            lo = max(col, section_start)
            hi = min(end_col, section_end)
            cell = lambda c: len(line[:c].expandtabs(self.indent_width))  # noqa: E731
            cell_lo = gutter + cell(lo) - cell(section_start)
            cell_hi = gutter + cell(hi) - cell(section_start)
            resolved = bool(self.link_resolver and self.link_resolver(link.target))
            segments = _style_cell_range(
                segments, cell_lo, cell_hi,
                self.resolved_style if resolved else self.unresolved_style,
            )
            styled = True
        if not styled:
            return strip
        return Strip(segments, cell_length=strip.cell_length)
