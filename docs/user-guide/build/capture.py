"""Capture real Lorewrite screens headlessly (Textual Pilot) for the guide.

Captures the code of the repository this script lives in:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
        .venv/bin/python docs/user-guide/build/capture.py

(build_guide.py --capture does exactly that.) The script refuses to run unless
`lorewrite.__file__` points into this repository. It works on COPIES of
examples/residual under a temp dir with a temp LOREWRITE_STATE_DIR, and every
AI or network function is monkeypatched with canned results: nothing goes out.
"""
import asyncio, json, os, re, shutil, sys, tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE / "shots"
REPO = HERE.parents[2]
REAL_DEMO = REPO / "examples" / "residual"

import lorewrite  # noqa: E402

assert Path(lorewrite.__file__).resolve().is_relative_to(REPO), lorewrite.__file__
print("capturing from", lorewrite.__file__)

TMP = Path(tempfile.mkdtemp(prefix="lwshots-", dir=os.environ.get("LW_SCRATCH")))
DEMO = TMP / "demo"
shutil.copytree(REAL_DEMO, DEMO)
STATE = TMP / "state"
STATE.mkdir()
os.environ["LOREWRITE_STATE_DIR"] = str(STATE)
os.environ.pop("OPENROUTER_API_KEY", None)


def reset_state(tour_seen=True):
    for f in STATE.glob("*"):
        f.unlink()
    (STATE / "settings.json").write_text(json.dumps({"tour_seen": tour_seen}))
    (STATE / "recent.json").write_text(json.dumps([
        {"path": str(DEMO), "title": "Residual", "opened_at": 1790000000.0},
        {"path": str(TMP / "the-salt-road"), "title": "The Salt Road", "opened_at": 1789000000.0},
    ]))


from lorewrite.core.project import Project  # noqa: E402

Project.create(TMP / "the-salt-road", title="The Salt Road")

import lorewrite.tui.app as app_mod  # noqa: E402
import lorewrite.ai.continuity as ai_cont  # noqa: E402
import lorewrite.tui.settingscreen as sset  # noqa: E402
from lorewrite.ai.links import Suggestion  # noqa: E402
from lorewrite.ai.client import ModelInfo  # noqa: E402
from lorewrite.ai.style import build_proposal  # noqa: E402
from lorewrite.ai.usage import LEDGER  # noqa: E402
from lorewrite.core.continuity import Contradiction  # noqa: E402
from lorewrite.ai.continuity import CanonUpdate  # noqa: E402
from lorewrite.tui.app import LorewriteApp  # noqa: E402

# no Omarchy theme: a neutral light theme prints better in grayscale
app_mod.omarchy_textual_theme = lambda *a, **k: None


# --- canned AI ---------------------------------------------------------------


def canned_aliases(text, entities, model, client=None):
    LEDGER.record(model, "links", 0.0008)
    out = []
    for surface, entity in (("The flyers", "Kessler-Voss"),
                            ("dead woman", "Imogen Sallow")):
        i = text.find(surface)
        if i >= 0:
            out.append(Suggestion(entity, i, i + len(surface), surface))
    return sorted(out, key=lambda s: s.start)


def canned_continuity(text, entities, canon, model, client=None):
    LEDGER.record(model, "continuity", 0.0061)
    if "green eyes" in text:
        return [Contradiction(
            "physical_attribute", "error", "Imogen Sallow",
            "Her green eyes were open, fixed on the ceiling screen",
            "Change to grey (established in her note)", "", 13)]
    return []


def canned_canon(text, entities, model, client=None):
    LEDGER.record(model, "canon", 0.0047)
    return [
        CanonUpdate(
            "Wren",
            ("Reads a building's ice the way a person reads handwriting.",
             "Recognizes the shard's architecture as Imogen Sallow's own work."),
            "Wren: \"I know it the way you know your own handwriting... She "
            "wrote me, Rook.\"",
            "- An AI construct; runs from the jack behind Rook's ear, not a body.\n"
            "- Can read building sensor logs and ice from inside a local node.\n"
            "- Recognizes Imogen Sallow's code \"like handwriting\": Sallow wrote her."),
        CanonUpdate(
            "Sallow's Shard",
            ("Stays cold in the warm, damp Meridian, as if kept elsewhere until recently.",),
            "\"The shard was cold. Everything in the Meridian was warm and damp.\"",
            "- Found by Rook in capsule 7-19; he pocketed it before Kuroda climbed up.\n"
            "- Its ice is Sallow's work; Wren recognizes it."),
    ]


DRAFT_TEXT = (
    "The flyer's searchlight swept the alley below and came back for the "
    "window. Rook killed the deck's glow with the heel of his hand and sat "
    "very still, listening to the rain tick against the glass like a clock "
    "someone else was winding.")
EXPAND_TEXT = (
    "The Meridian's lobby was awake at three in the morning and did not "
    "look glad of it: wet floor tiles, a vending wall humming to itself, "
    "and a night manager asleep upright behind the glass with his mouth "
    "a little open.")
REWRITE_TEXT = (
    "The shard sat in Rook's pocket, cold and exact, a coin from a country "
    "that no longer issued money.")


def canned_generate(mode, instruction, context, model, client=None,
                    selection=None):
    LEDGER.record(model, mode, 0.0042)
    return {"draft": DRAFT_TEXT, "expand": EXPAND_TEXT,
            "rewrite": REWRITE_TEXT}[mode]


STYLE_FIELDS = {
    "voice": "- Close third person, past tense, anchored in Rook's senses.\n"
             "- Dry, weary narration; the world is described as he would "
             "notice it.",
    "rhythm": "- Mostly medium sentences, broken by short flat ones for "
              "emphasis.\n- Short paragraphs; dialogue carries the pace.",
    "diction": "- Concrete, worn objects: copper, ozone, noodle steam, "
               "fiberglass.\n- Similes drawn from the city itself.",
    "dialogue": "- Plain `said` tags; Wren's lines often arrive by jack, "
                "unattributed.\n- Understatement over explanation.",
    "avoid": "- Adverbs on dialogue tags.\n- Explaining the technology; "
             "it is simply there.",
}


def canned_learn_style(samples, model, client=None, manuscript=None):
    LEDGER.record(model, "style", 0.0153)
    picks = [min(1, len(samples) - 1), min(4, len(samples) - 1),
             min(7, len(samples) - 1)]
    data = dict(STYLE_FIELDS, exemplar_indexes=picks)
    learned = None
    if manuscript is not None:   # the provenance line, as the real call writes it
        from lorewrite.core.style import learned_note
        learned = learned_note(sum(len(p.split()) for _, p in samples),
                               manuscript, "2026-10-01")
    return build_proposal(data, samples, learned)


app_mod.suggest_links = canned_aliases
app_mod.generate = canned_generate
app_mod.learn_style = canned_learn_style
ai_cont.check_scene = canned_continuity
ai_cont.propose_canon_updates = canned_canon

MODEL_ROWS = [
    # id, name, $in, $out, ctx, structured outputs?
    ("anthropic/claude-sonnet-4.5", "Anthropic: Claude Sonnet 4.5", 3.0, 15.0, 1000000, True),
    ("google/gemini-2.5-flash", "Google: Gemini 2.5 Flash", 0.30, 2.50, 1048576, True),
    ("google/gemini-2.5-pro", "Google: Gemini 2.5 Pro", 1.25, 10.0, 1048576, True),
    ("meta-llama/llama-3.3-70b-instruct", "Meta: Llama 3.3 70B Instruct", 0.10, 0.32, 131072, False),
    ("mistralai/mistral-small-3.2", "Mistral: Mistral Small 3.2", 0.06, 0.18, 128000, True),
    ("nousresearch/hermes-4-70b", "Nous: Hermes 4 70B", 0.11, 0.38, 131072, False),
    ("openai/gpt-4o-mini", "OpenAI: GPT-4o mini", 0.15, 0.60, 128000, True),
]


def canned_models(timeout=10, structured_only=True):
    return [ModelInfo(*r[:5]) for r in MODEL_ROWS if r[5] or not structured_only]


sset.list_models = canned_models
sset.get_api_key = lambda: "sk-or-v1-demo-0000-a1b2"

SIZE = (100, 32)

# The palette-results-off-screen bug of Edition 1 is fixed on the branch; this
# capture no longer patches the CSS. shot() asserts the results are on screen.


def mk(project):
    app = LorewriteApp(project)
    app.theme = "textual-light"
    app.animation_level = "none"
    return app


def svg2png(name):
    svg = OUT / f"{name}.svg"
    png = OUT / f"{name}.png"
    txt = svg.read_text()
    txt = re.sub(r'font-family:[^;"]*', "font-family: Liberation Mono", txt)
    txt = txt.replace("<svg ", '<svg xml:space="preserve" ', 1)
    svg.write_text(txt)
    os.system(f'rsvg-convert -z 1.6 "{svg}" -o "{png}"')
    svg.unlink()


CROPS = json.loads((OUT / "crops.json").read_text()) if (
    "--help-only" in sys.argv and (OUT / "crops.json").exists()) else {}


def shot(app, name, modal=False, max_rows=None):
    cols, rows = app.size
    entry = {"cols": cols, "rows": rows, "box": None}
    if modal:
        regs = [w.region for w in app.screen.children if w.region.width]
        if regs:
            x0 = min(r.x for r in regs); y0 = min(r.y for r in regs)
            x1 = max(r.x + r.width for r in regs)
            y1 = max(r.y + r.height for r in regs)
            if max_rows:
                y1 = min(y1, y0 + max_rows)
            x0, y0 = max(0, x0 - 1), max(0, y0 - 1)
            x1, y1 = min(cols, x1 + 1), min(rows, y1 + 1)
            entry["box"] = [x0, y0, x1, y1]
    CROPS[name] = entry
    app.save_screenshot(f"{name}.svg", path=str(OUT))
    svg2png(name)
    (OUT / "crops.json").write_text(json.dumps(CROPS, indent=1))
    print("shot", name)


def find_pos(text, needle, nth=0):
    i = -1
    for _ in range(nth + 1):
        i = text.index(needle, i + 1)
    return text.count("\n", 0, i), i - (text.rfind("\n", 0, i) + 1)


def offset_of(text, needle):
    return text.index(needle)


def cursor_to_offset(app, off):
    t = app.editor.text
    r = t.count("\n", 0, off)
    c = off - (t.rfind("\n", 0, off) + 1)
    app.editor.move_cursor((r, c))


async def main():
    import lorewrite.tui.launch as launch_mod
    from lorewrite.core.recents import Recent
    from lorewrite.tui.app import ConfirmScreen, HELP_TEXT
    from lorewrite.tui.linkreview import AliasReviewScreen
    from lorewrite.tui.promptscreen import PromptScreen
    from lorewrite.tui.stylereview import StyleReviewScreen
    from lorewrite.tui.noteupdates import NoteUpdateScreen
    from lorewrite.tui.continuityscreen import ContinuityScreen
    from lorewrite.core import drafts

    (OUT / "help_text.txt").write_text(HELP_TEXT, encoding="utf-8")

    # 1. launch screen (paths shown are stand-ins: a tidy home directory)
    real_load, real_is = launch_mod.load_recents, Project.is_project
    launch_mod.load_recents = lambda: [
        Recent(Path("/home/writer/novels/residual"), "Residual", 1790000000.0),
        Recent(Path("/home/writer/novels/the-salt-road"), "The Salt Road", 1789000000.0)]
    Project.is_project = classmethod(lambda cls, root: True)
    Path.home = classmethod(lambda cls: Path("/home/writer"))
    reset_state()
    app = mk(None)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        shot(app, "launch", modal=True)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press(*"The Salt Road")
        await pilot.pause()
        shot(app, "newproject", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        shot(app, "settings_nokey_launch", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("q")
    launch_mod.load_recents = real_load
    Project.is_project = real_is

    # 2. tour (five pages on the branch)
    reset_state(tour_seen=False)
    app = mk(Project.open(DEMO))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.5)
        await pilot.press("right", "right", "right")
        await pilot.pause()
        shot(app, "tour4", modal=True)
        await pilot.press("escape")

    # 3. main window and the pre-M4 features
    reset_state()
    s1 = DEMO / "manuscript" / "01-rain-on-the-spur.md"
    t = s1.read_text()
    s1.write_text(t.replace("Lin's counter", "[[Lin]]'s counter", 1)
                  .replace("Kuroda.\n\n\"Don't,\"", "[[Kuroda]].\n\n\"Don't,\"", 1))
    app = mk(Project.open(DEMO))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.5)
        r, c = find_pos(app.editor.text, "Kessler-Voss")
        app.editor.move_cursor((r, c + 3))
        await pilot.pause()
        shot(app, "main_scene1")
        app.open_file(DEMO / "manuscript" / "02-capsule-7-19.md")
        await pilot.pause()
        r, c = find_pos(app.editor.text, "Dr. Sallow")
        app.editor.move_cursor((r, c + 4))
        await pilot.pause(0.3)
        shot(app, "main")
        app.open_file(s1)
        await pilot.pause()
        text = app.editor.text
        idx = [i for i in range(len(text)) if text.startswith("Lin", i)
               and text[i - 2:i] != "[[" and not text[i:i + 4] == "Link"]
        i = idx[0]
        r = text.count("\n", 0, i); c = i - (text.rfind("\n", 0, i) + 1)
        app.editor.move_cursor((r, c))
        app.editor.move_cursor((r, c + 3), select=True)
        await pilot.pause()
        shot(app, "selected_name")
        await pilot.press("ctrl+j")
        await pilot.pause()
        shot(app, "typeprompt", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        app.open_file(DEMO / "entities" / "characters" / "dace-kuroda.md")
        await pilot.pause()
        shot(app, "entitynote")
        app.open_file(DEMO / "manuscript" / "02-capsule-7-19.md")
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause(2.0)
        # the Edition-1 bug (results pushed below the window) must be gone
        from textual.command import CommandList
        cl = app.screen.query_one(CommandList)
        assert cl.region.y + cl.region.height <= app.size.height, cl.region
        assert cl.region.height >= 3, cl.region
        shot(app, "palette")
        await pilot.press(*"ai")
        await pilot.pause(2.0)
        shot(app, "palette_ai")
        await pilot.press("escape")
        await pilot.pause()
        app.sidebar.query_one("#filter").focus()
        await pilot.press(*"ku")
        await pilot.pause()
        shot(app, "filter")
        app.sidebar.query_one("#filter").value = ""
        await pilot.pause()
        app.editor.focus()
        app.action_writer_mode()
        await pilot.pause(0.4)
        shot(app, "writer")
        app.action_writer_mode()
        await pilot.pause()
        app.action_new_scene()
        await pilot.pause()
        await pilot.press(*"Neon Lullaby")
        await pilot.pause()
        shot(app, "newscene", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        app.delete_scene_confirm()
        await pilot.pause()
        shot(app, "deleteconfirm", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        # alias finder (scene 3), then the note that gained the aliases
        app.open_file(DEMO / "manuscript" / "03-the-stairwell.md")
        await pilot.pause()
        before = app.editor.text
        app.action_find_aliases()
        await pilot.pause(1.5)
        assert isinstance(app.screen, AliasReviewScreen), app.screen
        shot(app, "aliasreview", modal=True)
        await pilot.press("enter")
        await pilot.pause(1.0)
        assert app.editor.text == before  # the scene is never edited
        app.open_file(DEMO / "entities" / "factions" / "kessler-voss.md")
        await pilot.pause()
        shot(app, "aliasnote")
        # continuity on scene 2
        app.open_file(DEMO / "manuscript" / "02-capsule-7-19.md")
        await pilot.pause()
        app.action_check_continuity()
        await pilot.pause(1.5)
        assert isinstance(app.screen, ContinuityScreen), app.screen
        shot(app, "continuity", modal=True)
        await pilot.press("space")
        await pilot.pause()
        shot(app, "continuity_waived", modal=True)
        await pilot.press("enter")          # jump: closes the report
        await pilot.pause(0.5)
        assert not isinstance(app.screen, ContinuityScreen)
        shot(app, "continuity_jump")
        # story bible: additions only
        app.action_update_bible()
        await pilot.pause(1.5)
        assert isinstance(app.screen, NoteUpdateScreen), app.screen
        shot(app, "bible", modal=True)
        await pilot.press("escape")
        await pilot.pause()

    # 4. AI writing: style guide, ctrl+g, pending drafts (fresh demo copy)
    shutil.rmtree(DEMO)
    shutil.copytree(REAL_DEMO, DEMO)
    reset_state()
    LEDGER.clear()
    s2 = DEMO / "manuscript" / "02-capsule-7-19.md"
    s2.write_text(s2.read_text().replace(
        "Rook climbed the ladder and looked in.",
        "{{expand: the lobby of the Meridian at 3 a.m., wet and humming}}\n\n"
        "Rook climbed the ladder and looked in.", 1))
    app = mk(Project.open(DEMO))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.5)
        # style guide
        app.action_learn_style()
        await pilot.pause(1.5)
        assert isinstance(app.screen, StyleReviewScreen), app.screen
        shot(app, "stylereview", modal=True)
        await pilot.press("enter")
        await pilot.pause(0.8)
        app.action_open_style_guide()
        await pilot.pause(0.6)
        shot(app, "styleguide")
        # draft at the cursor: end of scene 4
        app.open_file(DEMO / "manuscript" / "04-ghost-in-the-ice.md")
        await pilot.pause()
        app.editor.text  # noqa
        app.editor.load_text(app.editor.text.rstrip("\n") + "\n\n")
        await pilot.pause()
        app.editor.move_cursor(app.editor.document.end)
        await pilot.pause()
        app.action_generate()
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen), app.screen
        from textual.widgets import TextArea
        app.screen.query_one("#prompt-input", TextArea).load_text(
            "One paragraph: the company flyer's searchlight finds the "
            "window. Rook goes still. Dread, not panic.")
        await pilot.pause()
        shot(app, "prompt_draft", modal=True)
        await pilot.press("ctrl+g")
        await pilot.pause(2.0)
        assert drafts.find_pending(app.editor.text), "no draft inserted"
        app.editor.scroll_cursor_visible()
        await pilot.pause(0.5)
        shot(app, "draft")
        body_before = app.editor.text
        await pilot.press("f7")
        await pilot.pause(0.4)
        assert not drafts.find_pending(app.editor.text)
        shot(app, "draft_accepted")
        # expand marker in scene 2
        app.open_file(s2)
        await pilot.pause()
        text = app.editor.text
        cursor_to_offset(app, text.index("{{expand:") + 5)
        await pilot.pause()
        shot(app, "expand_marker")
        app.action_generate()
        await pilot.pause(2.0)
        assert drafts.find_pending(app.editor.text), "no expand draft"
        shot(app, "expand_draft")
        await pilot.press("f8")            # reject: the marker comes back
        await pilot.pause(0.4)
        assert "{{expand:" in app.editor.text
        # rewrite a selection in scene 3
        app.open_file(DEMO / "manuscript" / "03-the-stairwell.md")
        await pilot.pause()
        text = app.editor.text
        sent = "The shard sat in Rook's pocket like a coin from another country."
        a = text.index(sent)
        cursor_to_offset(app, a)
        r, c = find_pos(text, sent)
        app.editor.move_cursor((r, c))
        app.editor.move_cursor((r, c + len(sent)), select=True)
        await pilot.pause()
        app.action_generate()
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen), app.screen
        shot(app, "prompt_rewrite", modal=True)
        await pilot.press("ctrl+g")
        await pilot.pause(2.0)
        assert drafts.find_pending(app.editor.text)
        shot(app, "rewrite_draft")
        files = sorted(p.name for p in (DEMO / ".drafts").glob("*"))
        print("sidecars:", files)
        print((DEMO / ".drafts" / "03-the-stairwell.md.json").read_text())
        (OUT / "sidecar_example.txt").write_text(
            (DEMO / ".drafts" / "03-the-stairwell.md.json").read_text(),
            encoding="utf-8")
        marker = re.search(r'<!--ai id="[a-z0-9]{6}"-->', app.editor.text)
        (OUT / "marker_example.txt").write_text(marker.group(0))
        await pilot.press("f8")            # reject: original restored exactly
        await pilot.pause(0.4)
        assert sent in app.editor.text

    # 5. settings and its pickers (taller window: three model rows)
    reset_state()
    app = mk(Project.open(DEMO))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.5)
        app.action_settings()
        await pilot.pause()
        shot(app, "settings", modal=True)
        await pilot.click("#pick-writing")
        await pilot.pause(1.0)
        await pilot.press(*"llama")
        await pilot.pause(0.5)
        shot(app, "modelpicker_writing", modal=True, max_rows=14)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.click("#pick-fast")
        await pilot.pause(1.0)
        await pilot.press(*"gemini")
        await pilot.pause(0.5)
        shot(app, "modelpicker_fast", modal=True, max_rows=14)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        from lorewrite.tui.settingscreen import KeyPrompt
        app.push_screen(KeyPrompt())
        await pilot.pause()
        await pilot.press(*"sk-or-v1-example")
        await pilot.pause()
        shot(app, "keyprompt", modal=True)


async def spell_shots():
    """Spell check (TUI): the underline, the f6 window, the project dictionary."""
    from lorewrite.tui.spellscreen import SpellScreen
    shutil.rmtree(DEMO)
    shutil.copytree(REAL_DEMO, DEMO)
    reset_state()
    s1 = DEMO / "manuscript" / "01-rain-on-the-spur.md"
    t = s1.read_text()
    assert "receive" not in t
    t = t.replace("Rook", "Rook", 1)
    # plant two typos in a paragraph near the top
    t = t.replace("It's unattractive in a man", "It's unnattractive in a man", 1)
    t = t.replace("owes Lin four hundred", "owes Lin four hundered", 1)
    s1.write_text(t)
    assert "unnattractive" in t and "hundered" in t
    app = mk(Project.open(DEMO))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(1.2)
        r, c = find_pos(app.editor.text, "unnattractive")
        app.editor.move_cursor((r, 0))
        await pilot.pause(1.2)
        shot(app, "spell_underline")
        await pilot.press("f6")
        await pilot.pause(0.6)
        assert isinstance(app.screen, SpellScreen), app.screen
        shot(app, "spell_fix", modal=True)
        await pilot.press("1")
        await pilot.pause(0.5)
        assert "unnattractive" not in app.editor.text
        await pilot.press("f6")
        await pilot.pause(0.6)
        await pilot.press("a")             # add "hundered" to the project dictionary
        await pilot.pause(0.5)
        print((DEMO / "dictionary.txt").read_text())
        (OUT / "dictionary_example.txt").write_text(
            (DEMO / "dictionary.txt").read_text(), encoding="utf-8")
    reset_state()
    app = mk(Project.open(DEMO))
    async with app.run_test(size=(100, 44)) as pilot:
        await pilot.pause(0.5)
        app.action_settings()
        await pilot.pause()
        shot(app, "settings_v3", modal=True)


async def help_shot():
    reset_state()
    app = mk(Project.open(DEMO))
    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause(0.5)
        app.action_help()
        await pilot.pause(0.6)
        shot(app, "help", modal=True)


if "--help-only" not in sys.argv:
    asyncio.run(main())
    asyncio.run(spell_shots())
asyncio.run(help_shot())
print("TMP", TMP)
