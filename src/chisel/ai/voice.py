"""Voice checks (script mode): does a character's dialogue in this scene sound like that character elsewhere?

The same shape as the continuity check: ``plan_voice`` decides what is sent before any network call (through
the context budget), ``check_voice`` makes one structured call with the strong model, ``parse_findings``
validates the reply. Who says what is exact (core.voice reads the cues), so the model only judges lines the
app has already located, and a finding whose quote is not a line that character speaks in the scene is dropped.
Nothing here edits the script: findings are suggestions, reviewed like continuity issues.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..core import scenemeta
from ..core import voice as dialogue
from ..core.continuity import Contradiction, SEVERITIES
from ..core.entities import Entity
from .budget import Budget, Item, Section, SentReport, fit, preflight, render
from .client import openrouter_extra_body
from .usage import record_response

KINDS = ("vocabulary", "register", "rhythm", "verbal_habit", "out_of_character")
TYPE_PREFIX = "voice_"

REFERENCE_CAP = 3500   # one character's reference lines in a request (the farthest scenes are cut first)
NOTE_CAP = 1200        # a character note taken into a request

VOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "character": {"type": "string"},
                    "evidence": {"type": "string"},
                    "reason": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["id", "kind", "severity", "character", "evidence", "reason", "suggested_fix"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You check whether a character's dialogue in ONE scene of a script sounds like that same character elsewhere in
the script. You are given, for each character who speaks in the scene, lines they speak in other scenes (the
closest scenes first), then the scene. You may also be given notes about the characters and the author's style
guide.

Flag a line only when it clearly departs from how the character speaks in the reference lines:
- vocabulary: words or idioms the character does not use, or avoids
- register: formality, politeness or education that does not match
- rhythm: sentence length and shape (clipped or flowing) plainly unlike the character
- verbal_habit: a tic, catchphrase or dialect feature the reference lines show consistently, missing or contradicted
- out_of_character: an attitude or way of putting things this character would not say

Rules:
- "character" is the name exactly as the reference section gives it.
- "evidence" MUST be words one character speaks in the scene, copied verbatim from the scene (a whole line, or a
  stretch of it). Never quote the reference lines, action or another character.
- "suggested_fix" is that same line rewritten in the character's voice: same meaning, about the same length,
  plain text (no cue, no parenthetical).
- "reason" is one short sentence: what differs, and how the reference lines sound instead.
- Do not flag a line because it differs from other characters, because the situation is new (grief, anger, a
  lie), or for a style choice the author may intend. Characters change register with who they talk to: flag only
  when this character's habits are plainly contradicted.
- Do not flag a character who has no reference lines. If every line fits, return an empty list.
"""


@dataclass(frozen=True)
class VoicePlan:
    """What a voice check sends, decided before the network call."""
    context: str                          # the request's context text (references, notes, style, scene)
    checked: tuple[str, ...]              # speakers whose lines are judged
    skipped: tuple[tuple[str, int], ...]  # (speaker, reference lines) of speakers with too little to compare
    report: SentReport
    dropped: tuple[str, ...] = ()         # speakers with enough lines whose references did not fit the window


def plan_voice(scene_text: str, scene_path, project, entities: list[Entity],
               canon_by_name: dict[str, str], style_md: str | None, budget: Budget) -> VoicePlan:
    """Decide what a voice check sends. *scene_text* has its pending AI drafts already stripped; *scene_path*
    is the scene's file (never its own reference). Speakers with fewer than ``MIN_REFERENCE_LINES`` lines
    elsewhere are returned in ``skipped``, not guessed at. Raises ``BudgetError`` when the scene alone does not
    fit, and ``ValueError`` when nobody speaks in it."""
    spoken = dialogue.by_speaker(scene_text, entities)
    if not spoken:
        raise ValueError("Nobody speaks in this scene: a voice check needs character cues with dialogue")
    refs = dialogue.gather_references(project, entities, scene_path, set(spoken))
    judged = {name: refs[name] for name in spoken
              if name in refs and dialogue.reference_lines(refs[name]) >= dialogue.MIN_REFERENCE_LINES}
    skipped = tuple((name, dialogue.reference_lines(refs.get(name, []))) for name in spoken if name not in judged)
    if not judged:
        return VoicePlan("", (), skipped, SentReport("voice", (), 0, budget.window_tokens, budget.output_reserve, False))

    by_lines = sorted(judged, key=lambda n: (-dialogue.line_count(spoken[n]), n))
    rank = {name: i for i, name in enumerate(by_lines)}
    ref_items = tuple(
        Item(name, dialogue.format_reference(judged[name]),
             f"### {name} (speaks {dialogue.line_count(spoken[name])} line"
             f"{'' if dialogue.line_count(spoken[name]) == 1 else 's'} in this scene)",
             rank[name], REFERENCE_CAP)
        for name in by_lines)
    notes = tuple(Item(name, canon_by_name[name].strip(), f"### {name}", rank[name], NOTE_CAP)
                  for name in by_lines if canon_by_name.get(name, "").strip())
    sections = [
        Section("Instructions and question", SYSTEM_PROMPT + json.dumps(VOICE_SCHEMA), visible=False),
        Section("Reference lines", priority=0, droppable=True, items=ref_items,
                head="LINES EACH CHARACTER SPEAKS IN OTHER SCENES (closest scenes first):\n\n"),
    ]
    if style_md and style_md.strip():
        sections.append(Section("Style guide", "STYLE GUIDE:\n" + style_md.strip(), priority=1, droppable=True))
    if notes:
        sections.append(Section("Character notes", priority=2, droppable=True, items=notes,
                                head="CHARACTER NOTES:\n\n"))
    sections.append(Section("Scene", "SCENE:\n" + scenemeta.strip(scene_text)))
    fitted, report = fit(sections, budget, "voice")
    preflight(report)
    kept = {it.name for it in next(s for s in fitted if s.name == "Reference lines").items}
    checked = tuple(n for n in by_lines if n in kept)
    # a character whose references did not fit is not "too few lines": it is named apart, and the report
    # says what was cut
    dropped = tuple(n for n in by_lines if n not in kept)
    return VoicePlan(render(fitted), checked, skipped, report, dropped)


def _norm(text: str) -> str:
    return " ".join(str(text).replace("’", "'").replace("“", '"').replace("”", '"').split()).strip(" \"'").casefold()


MIN_EVIDENCE = 4     # characters of evidence (after trimming quote marks): a bare quote or a letter proves nothing
_FENCE_RE = re.compile(r"\A\s*```[A-Za-z]*\s*\n(.*?)\n?```\s*\Z", re.DOTALL)


def _find_line(speeches_: list[dialogue.Speech], key: str) -> tuple[int, str] | None:
    """(row, line) of the spoken line where the normalised quote *key* starts, when the quote lies inside one
    line or runs on through the rest of ONE speech; None when it is not words that speaker says (a quote that
    joins two speeches, or two characters, does not count)."""
    for s in speeches_:
        for row, line in zip(s.rows, s.lines):
            if key in _norm(line):
                return row, line
        joined = " ".join(_norm(line) for line in s.lines)
        at = joined.find(key)
        if at != -1:
            seen = 0
            for row, line in zip(s.rows, s.lines):
                seen += len(_norm(line)) + 1
                if at < seen:
                    return row, line
    return None


def parse_findings(raw: str, scene_text: str, entities: list[Entity], checked: tuple[str, ...] | None = None,
                   scene_rel: str = "") -> list[Contradiction]:
    """The model's JSON (a reply wrapped in a code fence is unwrapped) as ``Contradiction`` s of type
    ``voice_<kind>``. Tolerant (bad input gives []). A finding is kept only when its character speaks in the scene
    (and is one of *checked*, when given) and its evidence is words that character speaks there, verbatim, inside
    one speech: anything else is dropped. The evidence kept is the spoken line itself as written (so the editor
    finds it), and its row is that line's row."""
    raw = raw if not isinstance(raw, str) else (_FENCE_RE.match(raw).group(1) if _FENCE_RE.match(raw) else raw)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    spoken = dialogue.by_speaker(scene_text, entities)
    names = {n.casefold(): n for n in spoken if checked is None or n in checked}
    out: list[Contradiction] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            kind, severity = str(item["kind"]), str(item["severity"])
            character, evidence = str(item["character"]).strip(), str(item["evidence"]).strip()
            reason, fix = str(item["reason"]).strip(), str(item["suggested_fix"]).strip()
        except (KeyError, TypeError):
            continue
        name = names.get(character.casefold())
        if kind not in KINDS or severity not in SEVERITIES or name is None or not evidence:
            continue
        key = _norm(evidence)
        if len(key) < MIN_EVIDENCE or not any(ch.isalnum() for ch in key):
            continue
        hit = _find_line(spoken[name], key)
        if hit is None:
            continue                        # not something this character says in this scene
        row, line = hit
        c = Contradiction(TYPE_PREFIX + kind, severity, name, line.strip(), fix, scene_rel, row, reason)
        if c.waiver_key() not in seen:
            seen.add(c.waiver_key())
            out.append(c)
    return out


def check_voice(scene_text: str, plan: VoicePlan, entities: list[Entity], model: str, client=None,
                scene_rel: str = "") -> list[Contradiction]:
    """Network call: judge the lines of ``plan.checked`` against their reference lines. Synchronous (a worker
    thread in the terminal app, an AI job in the desktop one). Returns [] without a call when nothing can be judged."""
    if not plan.checked:
        return []
    if client is None:
        from .client import make_client

        client = make_client(model)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": plan.context + "\n\nCheck the dialogue of: " + ", ".join(plan.checked)
             + ". Reply with the findings JSON."},
        ],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "voice_findings", "strict": True, "schema": VOICE_SCHEMA}},
        extra_body=openrouter_extra_body({"provider": {"require_parameters": True}}, model=model),
    )
    record_response(response, model, "voice")
    raw = response.choices[0].message.content or ""
    return parse_findings(raw, scene_text, entities, plan.checked, scene_rel)
