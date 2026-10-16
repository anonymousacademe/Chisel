"""Pipe tables (docs/dev/plan-research-mode.md 7.3): parse and serialise in one canonical form.

All table parsing and serialising lives here; the GUI grid only shows and edits cells. The canonical form is:
``| a | b |`` rows, ``|`` escaped as ``\\|``, no newlines in cells, and a delimiter row whose dash count is
``max(3, widest cell of the column)`` so the bytes depend only on the content (pandoc derives column widths from
the dash counts once a line is longer than ``--columns``). ``to_pipe(parse_pipe(s)) == s`` for canonical ``s``.
"""

from __future__ import annotations

from dataclasses import dataclass

ALIGNS = ("default", "left", "right", "center")
MIN_DASHES = 3


@dataclass(frozen=True)
class Table:
    cells: list[list[str]]     # row 0 is the header; every row has len(align) cells
    align: list[str]           # per column: "default" | "left" | "right" | "center"


def _split_row(line: str) -> list[str]:
    """Cells of one pipe row; ``\\|`` is a literal pipe, outer pipes are optional."""
    line = line.strip()
    cells, cur, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur))
    if line.startswith("|"):
        cells = cells[1:]
    if line.endswith("|") and not line.endswith("\\|") and cells:
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _delim_align(cell: str) -> str | None:
    c = cell.strip()
    if not c or set(c) - set("-:") or "-" not in c:
        return None
    left, right = c.startswith(":"), c.endswith(":")
    return "center" if left and right else "left" if left else "right" if right else "default"


def parse_pipe(text: str) -> Table:
    """The first pipe table in *text*; ValueError when there is none."""
    lines = text.replace("\r\n", "\n").split("\n")
    for i in range(len(lines) - 1):
        if "|" not in lines[i]:
            continue
        aligns = [_delim_align(c) for c in _split_row(lines[i + 1])]
        if not aligns or None in aligns:
            continue
        header = _split_row(lines[i])
        if len(header) != len(aligns):
            continue
        rows = [header]
        for ln in lines[i + 2:]:
            if not ln.strip() or "|" not in ln:
                break
            rows.append(_split_row(ln))
        n = len(aligns)
        rows = [(r + [""] * n)[:n] for r in rows]
        return Table(rows, [a or "default" for a in aligns])
    raise ValueError("no pipe table found")


def _cell(text: str) -> str:
    return " ".join(str(text).replace("\r", "").split("\n")).replace("|", "\\|").strip()


def to_pipe(table: Table) -> str:
    """The canonical pipe-table text (no trailing newline)."""
    n = len(table.align)
    if n == 0 or not table.cells:
        raise ValueError("a table needs a header row and at least one column")
    rows = [[_cell(c) for c in (list(r) + [""] * n)[:n]] for r in table.cells]
    widths = [max([MIN_DASHES] + [len(r[c]) for r in rows]) for c in range(n)]
    delim = []
    for c, a in enumerate(table.align):
        if a not in ALIGNS:
            raise ValueError(f"unknown alignment: {a}")
        d = "-" * widths[c]
        delim.append((":" if a in ("left", "center") else "") + d + (":" if a in ("right", "center") else ""))
    out = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(delim) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)
