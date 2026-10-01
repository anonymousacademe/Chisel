"""Headless GUI backend for the guide's figures (never the real app).

    PYTHONPATH=src .venv-gui/bin/python docs/user-guide/build/gui_server.py PROJECT_COPY

This is `python -m lorewrite.gui.devserver --project COPY --mock-ai` with one
difference: after `mockai.install()` it replaces the generic canned answers by
ones written for the Residual story (the same slips the TUI figures show), and
it records the prices of a few canned calls. Everything is local; no network
call is made. Prints the URL, then serves until it is stopped (SIGTERM by PID).
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
import lorewrite  # noqa: E402

assert Path(lorewrite.__file__).resolve().is_relative_to(REPO), lorewrite.__file__

from lorewrite.ai.client import ModelInfo  # noqa: E402
from lorewrite.ai.continuity import CanonUpdate  # noqa: E402
from lorewrite.ai.links import Suggestion  # noqa: E402
from lorewrite.ai.usage import LEDGER  # noqa: E402
from lorewrite.core.continuity import Contradiction  # noqa: E402
from lorewrite.core.style import learned_note, style_markdown, sample_manuscript  # noqa: E402
from lorewrite.ai.style import build_proposal  # noqa: E402
from lorewrite.gui import api as api_module  # noqa: E402
from lorewrite.gui import mockai  # noqa: E402
from lorewrite.gui.api import Api  # noqa: E402
from lorewrite.gui.devserver import serve  # noqa: E402

mockai.install(api_module)

DRAFT = ("The flyer's searchlight swept the alley below and came back for the "
         "window. Rook killed the deck's glow with the heel of his hand and sat "
         "very still, listening to the rain tick against the glass like a clock "
         "someone else was winding.")
EXPAND = ("The Meridian's lobby was awake at three in the morning and did not "
          "look glad of it: wet floor tiles, a vending wall humming to itself, "
          "and a night manager asleep upright behind the glass with his mouth "
          "a little open.")
REWRITE = ("The shard sat in Rook's pocket, cold and exact, a coin from a "
           "country that no longer issued money.")


def spend(what: str, cost: float) -> None:
    LEDGER.record("anthropic/claude-sonnet-4.5", what, cost, 900, 300)


def suggest_links(text, entities, model):
    spend("links", 0.0008)
    out = []
    for surface, who in (("The flyers", "Kessler-Voss"), ("dead woman", "Imogen Sallow")):
        i = text.find(surface)
        if i >= 0 and who in {e.name for e in entities}:
            out.append(Suggestion(who, i, i + len(surface), surface))
    return sorted(out, key=lambda s: s.start)


def check_scene(text, entities, canon, model):
    spend("continuity", 0.0061)
    if "green eyes" in text:
        return [Contradiction(
            "physical_attribute", "error", "Imogen Sallow",
            "Her green eyes were open, fixed on the ceiling screen",
            "Change to grey (established in her note)", "", 13)]
    return []


def propose_canon(text, entities, model):
    spend("canon", 0.0047)
    return [
        CanonUpdate(
            "Wren",
            ("Reads a building's ice the way a person reads handwriting.",
             "Recognizes the shard's architecture as Imogen Sallow's own work."),
            "Wren: \"I know it the way you know your own handwriting...\"", ""),
    ]


FIELDS = {
    "voice": "- Close third person, past tense, anchored in Rook's senses.\n"
             "- Dry, weary narration; the world is described as he would notice it.",
    "rhythm": "- Mostly medium sentences, broken by short flat ones for emphasis.\n"
              "- Short paragraphs; dialogue carries the pace.",
    "diction": "- Concrete, worn objects: copper, ozone, noodle steam, fiberglass.\n"
               "- Similes drawn from the city itself.",
    "dialogue": "- Plain `said` tags; Wren's lines often arrive by jack, unattributed.\n"
                "- Understatement over explanation.",
    "avoid": "- Adverbs on dialogue tags.\n- Explaining the technology; it is simply there.",
}


def learn(samples, model, client=None, manuscript=None):
    spend("style", 0.0153)
    picks = [min(1, len(samples) - 1), min(4, len(samples) - 1), min(7, len(samples) - 1)]
    learned = None
    if manuscript is not None:
        learned = learned_note(sum(len(p.split()) for _, p in samples), manuscript, "2026-10-01")
    return build_proposal(dict(FIELDS, exemplar_indexes=picks), samples, learned)


def generate(mode, instruction, context, model, selection=None, **_):
    spend(mode, 0.0042)
    return {"draft": DRAFT, "expand": EXPAND, "rewrite": REWRITE}[mode]


def ask(prompt, context, model, history=None, client=None):
    spend("ask", 0.0028)
    return ("Three ways to raise the dread without a new event:\n"
            "1. Let the searchlight pause on the window a beat too long.\n"
            "2. Have Wren go quiet on the jack, which she never does.\n"
            "3. End the scene on the sound of the caller's line going dead.")


def research_answer(prompt, context, model, history=None, client=None):
    spend("research", 0.0036)
    if "[1]" not in context:
        return ("None of your research notes covers that. You could look it up "
                "and save what you find as a note.")
    return ("Real capsule hotels stack units two high and guests keep their shoes "
            "in lockers at the door [1]. The Meridian's forty-high stack is a "
            "deliberate exaggeration, so lean on the smell and the hum rather "
            "than the engineering [1].")


def brainstorm(context, model, client=None):
    spend("brainstorm", 0.0039)
    return ["What if the caller ID did not go dark, but showed Rook's own number?",
            "Let the rain stop mid-sentence, so the market hears what it was covering.",
            "Wren is lying about something small; let Rook notice and say nothing.",
            "The holo koi turns toward the door a beat before anyone walks in."]


MODELS = [
    ("anthropic/claude-sonnet-4.5", "Anthropic: Claude Sonnet 4.5", 3.0, 15.0, 1000000, True),
    ("google/gemini-2.5-flash", "Google: Gemini 2.5 Flash", 0.30, 2.50, 1048576, True),
    ("google/gemini-2.5-pro", "Google: Gemini 2.5 Pro", 1.25, 10.0, 1048576, True),
    ("meta-llama/llama-3.3-70b-instruct", "Meta: Llama 3.3 70B Instruct", 0.10, 0.32, 131072, False),
    ("mistralai/mistral-small-3.2", "Mistral: Mistral Small 3.2", 0.06, 0.18, 128000, True),
    ("openai/gpt-4o-mini", "OpenAI: GPT-4o mini", 0.15, 0.60, 128000, True),
]


def list_models(timeout=10, structured_only=True):
    return [ModelInfo(*r[:5]) for r in MODELS if r[5] or not structured_only]


api_module.suggest_links = suggest_links
api_module.check_scene = check_scene
api_module.propose_canon_updates = propose_canon
api_module.learn_style = learn
api_module.generate_text = generate
api_module.ask_writer = ask
api_module._list_models = list_models
api_module.research_writer = research_answer
api_module.brainstorm_writer = brainstorm

if __name__ == "__main__":
    project = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    api = Api()
    if project is not None:
        api.open_project(str(project))
    server = serve(api)
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    print(f"http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
