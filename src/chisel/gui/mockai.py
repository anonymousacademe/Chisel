"""Canned AI for headless screenshots and demos: ``devserver --mock-ai``.

Replaces the AI functions Api calls with deterministic fakes (and an API key
that "exists"). No network, no cost — the spend ledger records a fixed amount
so the status bar has something to show. Never used by the real app.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import struct
import zlib
from types import SimpleNamespace

from ..ai.client import ModelInfo
from ..ai.continuity import CanonUpdate
from ..ai.links import Suggestion
from ..ai.relationships import Suggestion as RelSuggestion
from ..ai.stream import Cancelled
from ..ai.usage import LEDGER
from ..core.continuity import Contradiction
from ..core.style import style_markdown

COST = 0.0031
IMAGE_COST = 0.0336   # what a real image costs, so the status bar looks honest


def _spend(feature: str) -> None:
    LEDGER.record("mock/model", feature, COST, 100, 50)


WORD_DELAY = 0.04   # seconds between streamed words, so the live states are visible


def _pause(seconds: float) -> None:
    """Pretend the model is thinking - only inside an AI job (tests and the plain
    bridge calls stay instant); a Stop ends the wait."""
    from . import aijobs

    job = aijobs.current()
    if job is None:
        return
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if job.cancel.is_set():
            raise Cancelled()
        time.sleep(0.05)


def _stream(text: str, on_delta=None, cancel=None) -> str:
    """Hand *text* to *on_delta* word by word (with small delays) like a real stream;
    a set *cancel* raises Cancelled between words. Without either it returns at once."""
    if on_delta is None and cancel is None:
        return text
    for word in re.findall(r"\S+\s*", text):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if on_delta is not None:
            on_delta(word)
        time.sleep(WORD_DELAY)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    return text


def _first_sentence_with(text: str, names: list[str]) -> str | None:
    text = re.sub(r"\A\s*# .*\n", "", text)  # not the scene title
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        if any(n in sentence for n in names) and 25 < len(sentence) < 200:
            return sentence
    return None


def placeholder_png(prompt: str, size: tuple[int, int] = (704, 384)) -> bytes:
    """A small generated picture for the mock image model: a dusk gradient whose
    colours come from the prompt, with its first words on it when Pillow is there
    (it is optional: without it the picture is the plain gradient). No network."""
    w, h = size
    seed = hashlib.sha256((prompt or "").encode("utf-8")).digest()
    top = (20 + seed[0] % 60, 20 + seed[1] % 50, 50 + seed[2] % 90)
    bottom = (90 + seed[3] % 120, 60 + seed[4] % 100, 70 + seed[5] % 100)
    try:
        from PIL import Image, ImageDraw
        import io

        img = Image.new("RGB", size)
        px = ImageDraw.Draw(img)
        for y in range(h):
            t = y / (h - 1)
            px.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
        words = " ".join((prompt or "mock image").split()[:7])
        px.text((24, h - 44), words, fill=(255, 255, 255))
        px.text((24, 20), "mock image - no real generation", fill=(230, 230, 230))
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()
    except ImportError:
        pass
    # without Pillow: a plain gradient, one colour per row, written as a PNG by hand
    raw = b"".join(b"\x00" + bytes(int(a + (b - a) * (y / (h - 1))) for a, b in zip(top, bottom)) * w
                   for y in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def install(api_module) -> None:
    keys = {"key": "mock-key"}  # an in-memory "keyring": never touches the real one

    def get_api_key():
        return keys.get("key")

    def list_models(timeout=10, structured_only=True, output_modality=None):
        models = [
            ModelInfo("mock/aria-large", "Aria Large", 3.0, 15.0, 200000),
            ModelInfo("mock/brook-fast", "Brook Fast", 0.1, 0.4, 128000),
            ModelInfo("mock/cedar-writer", "Cedar Writer", 1.0, 5.0, 64000),
        ]
        images = [
            ModelInfo("mock/lumen-image", "Lumen Image", 0.1, 30.0, 32000, ("image", "text"), None),
            ModelInfo("mock/dusk-image", "Dusk Image", 0.2, 60.0, 32000, ("image", "text"), 0.04),
        ]
        if output_modality == "image":
            return images
        return models if not structured_only else models[:2]

    def list_local_models(base_url=None, timeout=5.0):
        return [
            ModelInfo("local:mockwriter", "mockwriter", None, None, 8192),
            ModelInfo("local:mockfast", "mockfast", None, None, None),
        ]

    def suggest_links(scene_text, entities, model):
        _pause(1.5)
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

    def suggest_relationships(entity, others, model, client=None):
        _pause(1.5)
        _spend("relationships")
        labels = ["owes them a favour", "kept them from the tide"]
        return [RelSuggestion(o.name, label) for o, label in zip(others, labels)]

    def check_scene(scene_text, entities, canon, model):
        _pause(1.5)
        _spend("continuity")
        names = [n for e in entities for n in e.names]
        sentence = _first_sentence_with(scene_text, names)
        if sentence is None:
            return []
        who = next((e.name for e in entities if any(n in sentence for n in e.names)), entities[0].name)
        return [Contradiction(
            "physical_attribute", "error", who, sentence,
            f"Check this against {who}'s note: the established details differ.")]

    def voice_check(scene_text, plan, entities, model, client=None, scene_rel=""):
        """Canned: the first judged speaker's first line is 'off', with a plausible rewrite."""
        from ..core import voice as dialogue
        _pause(1.5)
        _spend("voice")
        spoken = dialogue.by_speaker(scene_text, entities)
        name = next((n for n in plan.checked if n in spoken), None)
        if name is None:
            return []
        line = spoken[name][0].lines[0]
        return [Contradiction(
            "voice_register", "warning", name, line,
            "Keep it short and plain: " + " ".join(line.split()[:4]).rstrip(".,!?") + ".", scene_rel, None,
            f"{name} speaks more formally here than in the other scenes.")]

    def propose_canon_updates(scene_text, entities, model):
        _pause(1.5)
        _spend("canon")
        if not entities:
            return []
        e = entities[0]
        return [CanonUpdate(e.name, ("Appears in the opening scene of the manuscript",),
                            "from the first paragraphs", "")]

    def learn_style(samples, model, client=None, manuscript=None):
        _pause(1.5)
        _spend("style")
        fields = {
            "voice": "- Close third person, past tense; dry, wry narrative distance.",
            "rhythm": "- Short paragraphs; one-line dialogue beats between longer runs.",
            "diction": "- Concrete nouns, tech and weather imagery used together.",
            "dialogue": "- Plain tags (said); characters interrupt each other.",
            "avoid": "- Adverbs on dialogue tags; explaining the joke.",
        }
        return SimpleNamespace(markdown=style_markdown(fields, "## Exemplars\n\n"))

    def generate_text(mode, instruction, context, model, selection=None, client=None,
                      on_delta=None, cancel=None, script=False):
        if script:   # a script project: canned Fountain, never prose
            body = {"rewrite": "The rain keeps on, warm and metallic, drumming the spur above the stalls.",
                    "expand": f"{instruction.strip().rstrip('.')}. Nobody in the market looks up."}.get(
                mode, "A vendor laughs at nothing. The neon koi turn once in the haze.\n\n"
                      "ROOK\n(under his breath)\nThat is not a good sign.")
            _stream(body, on_delta, cancel)
            _spend(mode)
            return body
        if mode == "rewrite":
            body = "The rain kept on, warm and metallic, drumming the spur above the stalls."
        elif mode == "expand":
            body = f"(expanded) {instruction.strip().rstrip('.')}, and nobody in the market looked up."
        else:
            body = ("The rain thinned to a whisper against the glass, and for a moment the market "
                    "held its breath. Somewhere below, a vendor laughed at nothing, and the neon "
                    "koi turned once in the haze.")
        _stream(body, on_delta, cancel)
        _spend(mode)
        return body

    def ask_writer(prompt, context, model, history=None, client=None, on_delta=None, cancel=None):
        reply = ("Three options that keep the scene's quiet dread:\n"
                "1. Let a stranger at the counter echo Rook's last sentence.\n"
                "2. Have the holo koi turn toward him, just once.\n"
                "3. Cut to the caller ID going dark.")
        _stream(reply, on_delta, cancel)
        _spend("ask")
        return reply

    def research_writer(prompt, context, model, history=None, client=None, on_delta=None, cancel=None):
        if "[1]" not in context:
            reply = ("None of your research notes covers that. You could look it up and save what "
                     "you find as a note.")
        else:
            reply = ("Your notes say the spur floods when the tide table and the storm drains "
                     "disagree [1]. That fits the way the canon has the market built under it.")
        _stream(reply, on_delta, cancel)
        _spend("research")
        return reply

    def brainstorm_writer(context, model, client=None, on_delta=None, cancel=None, system=None, ask=None):
        if ask:   # a Brainstorm about a selected passage
            ideas = ["Give the habit an origin: someone they admired used to say it, and they kept it after that "
                     "person let them down.",
                     "Let the phrase land wrong once, with someone who takes it literally, and show what it costs.",
                     "What if the line is a shield: the more serious things get, the more they lean on it?"]
        else:
            ideas = ["What if the caller ID did not go dark, but showed Rook's own number?",
                     "Let the rain stop mid-sentence, so the market hears what it was covering.",
                     "Wren is lying about something small; let Rook notice and say nothing.",
                     "The holo koi turns toward the door a beat before anyone walks in."]
        _stream("\n".join(f"{i}. {idea}" for i, idea in enumerate(ideas, 1)), on_delta, cancel)
        _spend("brainstorm")
        return ideas

    def generate_images(prompt, model, client=None, style=None):
        _pause(2.5)
        LEDGER.record("mock/image", "image", IMAGE_COST, 20, 1120)
        return [(placeholder_png(prompt), "png")]

    def suggest_image_prompt(scene_context, model, client=None):
        _pause(1.5)
        _spend("image-prompt")
        place = re.search(r"place:\s*(.+)", scene_context)
        where = place.group(1).strip() if place else "a rain-slick night market under a rail spur"
        return (f"{where[:80]}, wet pavement shining with neon, steam rising from noodle stalls, "
                "holographic koi drifting overhead, a lone figure under an awning, warm lamplight "
                "against cold blue rain, late night, near-future.")

    def suggest_latex(description, *, model, cancel=None):
        _pause(1.5)
        _spend("latex")
        return _stream(r"E = m c^{2}", None, cancel)

    def suggest_plot_code(description, columns, *, model, cancel=None):
        _pause(1.5)
        _spend("plot-code")
        return _stream("import sys\nimport matplotlib\nmatplotlib.use('Agg')\n"
                       "import matplotlib.pyplot as plt\n\n"
                       "fig, ax = plt.subplots(figsize=(4, 3), dpi=300)\n"
                       "ax.set_xlabel('x')\nax.set_ylabel('y')\n"
                       "fig.savefig(sys.argv[-1])\n", None, cancel)

    def suggest_outline(context, model, client=None, cancel=None, on_delta=None):
        _pause(1.5)
        _spend("outline")
        ids = re.findall(r"^- (\S+\.md) \| ([^|\n]+?) \|", context, re.MULTILINE)
        items = []
        if ids:
            first_id, first_title = ids[0]
            items.append({"id": "1", "action": "rename", "title": first_title.strip(), "section": first_id,
                          "newTitle": first_title.strip() + " and aims",
                          "why": "The title can say what the section is for."})
        if "limitations" not in context.casefold().split("current outline")[-1]:
            items.append({"id": "2", "action": "add", "title": "Limitations", "part": "", "after": "",
                          "purpose": "State what the study cannot show.",
                          "why": "Reviewers expect the limits to be stated before the conclusion."})
        items.append({"id": "3", "action": "advice", "title": "Keep the scope tight",
                      "why": "Each section should serve the question in the scope statement."})
        return _stream(json.dumps({"items": items}, indent=1), on_delta, cancel)

    def suggest_requirements(context, model, client=None, cancel=None, on_delta=None):
        _pause(1.5)
        _spend("requirements")
        names = re.findall(r"^GUIDELINE DOCUMENT (\S+) ", context, re.MULTILINE)
        src = names[0] if names else ""
        body = context.split("GUIDELINE DOCUMENT", 1)[-1].split("\n", 1)[-1].strip()
        first = re.split(r"(?<=[.!?])\s+", body)[0][:200] if body else ""
        items = [
            {"id": "abstract-words", "group": "Abstract", "title": "Abstract is at most 250 words",
             "kind": "check", "check": "section-words-max", "section": ["abstract"], "max": 250,
             "severity": "warn", "source": src, "quote": first,
             "why": "The guideline limits the abstract."},
            {"id": "keywords-count", "group": "Keywords", "title": "3 to 6 keywords", "kind": "check",
             "check": "list-count", "section": ["keywords"], "min": 3, "max": 6, "severity": "warn",
             "source": src, "quote": "Authors must supply between three and six keywords after the abstract.",
             "why": "The guideline asks for a short keyword list."},
            {"id": "cover-letter", "group": "Submission", "title": "Prepare a cover letter", "kind": "advice",
             "severity": "info", "source": src, "quote": first, "why": "It cannot be checked in the text."},
        ]
        return _stream(json.dumps({"items": items}, indent=1), on_delta, cancel)

    api_module.suggest_outline = suggest_outline
    api_module.suggest_requirements = suggest_requirements
    api_module.generate_images = generate_images
    api_module.suggest_image_prompt = suggest_image_prompt
    api_module.suggest_latex = suggest_latex
    api_module.suggest_plot_code = suggest_plot_code
    api_module.get_api_key = get_api_key
    api_module._set_api_key = lambda k: keys.__setitem__("key", k)
    api_module._clear_api_key = lambda: keys.pop("key", None)
    api_module._list_models = list_models
    api_module._list_local_models = list_local_models
    api_module.suggest_links = suggest_links
    api_module.suggest_relationships = suggest_relationships
    api_module.check_scene = check_scene
    api_module.voice_check = voice_check
    api_module.propose_canon_updates = propose_canon_updates
    api_module.learn_style = learn_style
    api_module.generate_text = generate_text
    api_module.ask_writer = ask_writer
    api_module.research_writer = research_writer
    api_module.brainstorm_writer = brainstorm_writer
