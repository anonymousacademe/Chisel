"""Canned AI for headless screenshots and demos: ``devserver --mock-ai``.

Replaces the AI functions Api calls with deterministic fakes (and an API key
that "exists"). No network, no cost — the spend ledger records a fixed amount
so the status bar has something to show. Never used by the real app.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from ..ai.continuity import CanonUpdate
from ..ai.links import Suggestion
from ..ai.usage import LEDGER
from ..core.continuity import Contradiction
from ..core.style import style_markdown

COST = 0.0031


def _spend(feature: str) -> None:
    LEDGER.record("mock/model", feature, COST, 100, 50)


def _first_sentence_with(text: str, names: list[str]) -> str | None:
    text = re.sub(r"\A\s*# .*\n", "", text)  # not the scene title
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        if any(n in sentence for n in names) and 25 < len(sentence) < 200:
            return sentence
    return None


def install(api_module) -> None:
    def get_api_key():
        return "mock-key"

    def suggest_links(scene_text, entities, model):
        _spend("links")
        phrases = [("the jack behind his ear", "Wren"), ("the noodle stalls", "Hollow Market"),
                   ("the caller", "Dace Kuroda"), ("the company", "Kessler-Voss")]
        known = {e.name for e in entities}
        out = []
        for phrase, who in phrases:
            i = scene_text.find(phrase)
            if i != -1 and who in known:
                out.append(Suggestion(who, i, i + len(phrase), phrase))
        if not out and entities:  # always offer one, so the review UI has content
            m = re.search(r"\b[a-z]{4,} [a-z]{4,}\b", scene_text)
            if m:
                out.append(Suggestion(entities[0].name, m.start(), m.end(), m.group(0)))
        return out

    def check_scene(scene_text, entities, canon, model):
        _spend("continuity")
        names = [n for e in entities for n in e.names]
        sentence = _first_sentence_with(scene_text, names)
        if sentence is None:
            return []
        who = next((e.name for e in entities if any(n in sentence for n in e.names)), entities[0].name)
        return [Contradiction(
            "physical_attribute", "error", who, sentence,
            f"Check this against {who}'s note: the established details differ.")]

    def propose_canon_updates(scene_text, entities, model):
        _spend("canon")
        if not entities:
            return []
        e = entities[0]
        return [CanonUpdate(e.name, ("Appears in the opening scene of the manuscript",),
                            "from the first paragraphs", "")]

    def learn_style(samples, model):
        _spend("style")
        fields = {
            "voice": "- Close third person, past tense; dry, wry narrative distance.",
            "rhythm": "- Short paragraphs; one-line dialogue beats between longer runs.",
            "diction": "- Concrete nouns, tech and weather imagery used together.",
            "dialogue": "- Plain tags (said); characters interrupt each other.",
            "avoid": "- Adverbs on dialogue tags; explaining the joke.",
        }
        return SimpleNamespace(markdown=style_markdown(fields, "## Exemplars\n\n"))

    def generate_text(mode, instruction, context, model, selection=None, **_):
        _spend(mode)
        if mode == "rewrite":
            return "The rain kept on, warm and metallic, drumming the spur above the stalls."
        if mode == "expand":
            return f"(expanded) {instruction.strip().rstrip('.')}, and nobody in the market looked up."
        return "The rain thinned to a whisper against the glass, and for a moment the market held its breath."

    def ask_writer(prompt, context, model, history=None, client=None):
        _spend("ask")
        return ("Three options that keep the scene's quiet dread:\n"
                "1. Let a stranger at the counter echo Rook's last sentence.\n"
                "2. Have the holo koi turn toward him, just once.\n"
                "3. Cut to the caller ID going dark.")

    api_module.get_api_key = get_api_key
    api_module.suggest_links = suggest_links
    api_module.check_scene = check_scene
    api_module.propose_canon_updates = propose_canon_updates
    api_module.learn_style = learn_style
    api_module.generate_text = generate_text
    api_module.ask_writer = ask_writer
