"""AI proposals for research mode: a LaTeX equation from a description, and
matplotlib plotting code from a description (plan 7.3 and 7.4).

Both are *pending proposals*. The text returned is shown to the author in the
panel; nothing is run, saved or inserted here, and running a script is a
separate, trusted step (7.4). A stopped call raises ``stream.Cancelled`` and
returns nothing. The data column names are sent only when the author ticked
them (``columns`` is None otherwise), and they are a budget section, so they
show in the "What was sent" report like everything else.

``plan_latex`` / ``plan_plot_code`` return the ``SentReport`` for the same
request without any network call, so a bridge can show what would be sent
before the author confirms. They raise ``budget.BudgetError`` when the request
does not fit the model's window.
"""

from __future__ import annotations

import re

from .budget import Budget, Item, Section, SentReport, fit, preflight, render
from .client import make_client
from .stream import stream_text

LATEX_FEATURE = "latex"
PLOT_FEATURE = "plot-code"

LATEX_SYSTEM_PROMPT = """\
You write LaTeX for one display equation in a research paper, from the
author's plain-language description.

Output only the LaTeX body of the equation: no $ or $$ delimiters, no
\\begin{equation} wrapper, no \\label, no prose, no code fence. Use standard
LaTeX math commands. Do not invent symbols the description does not mention;
if a definition is needed, put it on its own line after the equation, starting
with a LaTeX comment (%) so it is easy to remove."""

PLOT_SYSTEM_PROMPT = """\
You write a complete Python script that draws one research figure with
matplotlib, from the author's plain-language description.

Output one Python script and nothing else, inside a single ```python block.
Contract the script must follow:
- It reads data only from the data folder given as the first command-line
  argument (sys.argv[1]); the output PNG path is the last argument (sys.argv[-1]).
- It writes exactly one PNG to that output path, at 300 dpi, and does nothing else.
- It uses matplotlib only (no network, no other packages, no writes outside
  the output path).
- Label axes and units from the description; if a column name is unclear, say so
  in a comment rather than guessing silently."""

_FENCE_RE = re.compile(r"\A\s*```[^\n]*\n(.*?)\n?```\s*\Z", re.DOTALL)


def _clean(raw: str) -> str:
    """The model's answer without a surrounding code fence, trimmed."""
    text = (raw or "").strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1)
    return text.strip()


def _latex_sections(description: str) -> list[Section]:
    return [
        Section("Instructions and question", LATEX_SYSTEM_PROMPT, visible=False),
        Section("Description", "DESCRIPTION OF THE EQUATION:\n" + description.strip()),
    ]


def _plot_sections(description: str, columns: list[str] | None) -> list[Section]:
    sections = [
        Section("Instructions and question", PLOT_SYSTEM_PROMPT, visible=False),
        Section("Description", "DESCRIPTION OF THE PLOT:\n" + description.strip()),
    ]
    if columns:  # ticked by the author only; None means "not sent"
        items = tuple(Item(str(c), head=f"- {c}", priority=0) for c in columns)
        sections.append(Section("Data columns", priority=1, droppable=True, items=items,
                                head="DATA COLUMNS (names only):\n", sep="\n"))
    return sections


def _plan(sections: list[Section], model: str, feature: str) -> tuple[list[Section], SentReport]:
    fitted, report = fit(sections, Budget.for_model(model), feature)
    preflight(report)
    return fitted, report


def plan_latex(description: str, *, model: str) -> SentReport:
    """What ``suggest_latex`` would send. No network call; raises BudgetError."""
    return _plan(_latex_sections(description), model, LATEX_FEATURE)[1]


def plan_plot_code(description: str, columns: list[str] | None, *, model: str) -> SentReport:
    """What ``suggest_plot_code`` would send. No network call; raises BudgetError."""
    return _plan(_plot_sections(description, columns), model, PLOT_FEATURE)[1]


def _run(system: str, sections: list[Section], model: str, feature: str, cancel) -> str:
    fitted, _ = _plan(sections, model, feature)
    client = make_client(model)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": render(fitted)},
    ]
    raw = stream_text(client, model, messages, feature, None, cancel)
    return _clean(raw)


def suggest_latex(description: str, *, model, cancel) -> str:
    """Network call: a LaTeX equation body proposed from *description*. A pending
    proposal only; the caller shows it and the author decides. Raises
    ``stream.Cancelled`` when stopped (nothing is returned)."""
    return _run(LATEX_SYSTEM_PROMPT, _latex_sections(description), model, LATEX_FEATURE, cancel)


def suggest_plot_code(description: str, columns: list[str] | None, *, model, cancel) -> str:
    """Network call: a matplotlib script proposed from *description*. *columns* is
    sent only when the author ticked it (pass None otherwise). A pending proposal
    only: never run here. Raises ``stream.Cancelled`` when stopped."""
    return _run(PLOT_SYSTEM_PROMPT, _plot_sections(description, columns), model, PLOT_FEATURE,
                cancel)
