"""Learn a style guide from the author's own prose (SPEC §7 M4).

The model reads sampled manuscript paragraphs (numbered) and describes the
author's voice, rhythm, diction and dialogue habits, and picks the paragraphs
that best exemplify them. Exemplars are quoted verbatim by the app from the
picked indexes — the model never writes them — and bad indexes are dropped.
Nothing is saved without the author's confirmation.

Uses the *writing* model, which may not support structured outputs: the
schema is requested but not required (no provider.require_parameters), and
the reply is parsed tolerantly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import datetime

from ..core.style import MAX_EXEMPLARS, exemplars_section, learned_note, style_markdown
from .client import usage_extra_body
from .usage import record_response

SCHEMA = {
    "type": "object",
    "properties": {
        "voice": {"type": "string"},
        "rhythm": {"type": "string"},
        "diction": {"type": "string"},
        "dialogue": {"type": "string"},
        "avoid": {"type": "string"},
        "exemplar_indexes": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["voice", "rhythm", "diction", "dialogue", "avoid",
                 "exemplar_indexes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are a literary editor writing a style guide for a novelist, so that a
drafting assistant can imitate the author's prose.

You are given numbered paragraphs sampled from the author's manuscript.
Describe what THIS author actually does — concrete, observable habits, not
generic writing advice. Fill these fields (short Markdown bullet lists, plain
text, no headings):
- voice: POV, tense, narrative distance, register
- rhythm: sentence length and variety, paragraphing, syntax habits
- diction: word choice, imagery, recurring vocabulary
- dialogue: tags, punctuation, how characters sound
- avoid: things the author evidently never does
- exemplar_indexes: the 2-3 paragraph numbers that best show the style

Reply with ONLY a JSON object with exactly those keys.
"""


@dataclass
class StyleProposal:
    voice: str = ""
    rhythm: str = ""
    diction: str = ""
    dialogue: str = ""
    avoid: str = ""
    exemplar_indexes: list[int] = field(default_factory=list)
    markdown: str = ""


def build_prompt(samples: list[tuple[str, str]]) -> str:
    blocks = [f"[{i}] ({rel})\n{paragraph}"
              for i, (rel, paragraph) in enumerate(samples)]
    return "MANUSCRIPT SAMPLES:\n\n" + "\n\n".join(blocks)


def parse_reply(raw: str) -> dict:
    """Tolerant JSON extraction: fenced or chatty replies still work.
    Returns {} on junk."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    for candidate in (raw, raw[raw.find("{"):raw.rfind("}") + 1]):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def validate_indexes(raw, count: int) -> list[int]:
    """Keep integer indexes inside [0, count), unique, at most three."""
    if not isinstance(raw, list):
        return []
    picks: list[int] = []
    for i in raw:
        if isinstance(i, bool) or not isinstance(i, int):
            continue
        if 0 <= i < count and i not in picks:
            picks.append(i)
    return picks[:MAX_EXEMPLARS]


def build_proposal(data: dict, samples: list[tuple[str, str]],
                   learned: str | None = None) -> StyleProposal:
    fields = {k: str(data.get(k) or "").strip()
              for k in ("voice", "rhythm", "diction", "dialogue", "avoid")}
    picks = validate_indexes(data.get("exemplar_indexes"), len(samples))
    return StyleProposal(
        **fields,
        exemplar_indexes=picks,
        markdown=style_markdown(fields, exemplars_section(samples, picks), learned),
    )


def learn_style(samples: list[tuple[str, str]], model: str,
                client=None, manuscript: tuple[int, int] | None = None
                ) -> StyleProposal:
    """Network call: propose a style guide from manuscript samples.

    Synchronous — run in a worker thread from the TUI. Raises ValueError if
    there is nothing to learn from or the reply is unusable.
    """
    if not samples:
        raise ValueError("no prose to learn from — write a few scenes first")
    if client is None:
        from .client import make_client

        client = make_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(samples)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "style_guide", "strict": True,
                            "schema": SCHEMA},
        },
        extra_body=usage_extra_body(),
    )
    record_response(response, model, "style")
    data = parse_reply(response.choices[0].message.content or "")
    if not data:
        raise ValueError("the model's reply wasn't a usable style guide")
    learned = None
    if manuscript is not None:  # provenance: when, and from how much prose
        learned = learned_note(sum(len(p.split()) for _, p in samples),
                               manuscript, datetime.date.today().isoformat())
    return build_proposal(data, samples, learned)
