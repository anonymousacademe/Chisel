"""Capture the terminal screens of the four feature waves (Fourth Edition).

    LW_SCRATCH=<tmp> PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python docs/user-guide/build/capture4.py

Builds a rich copy of examples/residual (build/rich_project.py) in a temp dir
with a temp CHISEL_STATE_DIR, patches every AI function with a canned
answer, and saves screens through Textual Pilot into build/shots/ (merged into
crops.json). Nothing touches the network or the real state folder.
"""
import asyncio, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE / "shots"
REPO = HERE.parents[2]

import chisel  # noqa: E402

assert Path(chisel.__file__).resolve().is_relative_to(REPO), chisel.__file__

TMP = Path(tempfile.mkdtemp(prefix="lwshots4-", dir=os.environ.get("LW_SCRATCH")))
PROJ = TMP / "proj"
STATE = TMP / "state"
STATE.mkdir()
os.environ["CHISEL_STATE_DIR"] = str(STATE)
os.environ.pop("OPENROUTER_API_KEY", None)
os.environ.update(GIT_AUTHOR_NAME="Residual Author", GIT_AUTHOR_EMAIL="author@example.com",
                  GIT_COMMITTER_NAME="Residual Author", GIT_COMMITTER_EMAIL="author@example.com",
                  GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")


def build_project():
    subprocess.run([sys.executable, str(HERE / "rich_project.py"), str(PROJ), str(STATE), "--git", "--inspiration"],
                   check=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")})


from chisel.core import research as research_notes, settings as user_settings  # noqa: E402
from chisel.core.project import Project  # noqa: E402

import chisel.tui.app as app_mod  # noqa: E402
from chisel.ai.usage import LEDGER  # noqa: E402
from chisel.tui.app import ChiselApp  # noqa: E402

app_mod.omarchy_textual_theme = lambda *a, **k: None


def canned_ask(prompt, context, model, history=None, client=None):
    LEDGER.record(model, "ask", 0.0028)
    return ("Three ways to raise the dread without a new event:\n"
            "1. Let the searchlight pause on the window a beat too long.\n"
            "2. Have Wren go quiet on the jack, which she never does.\n"
            "3. End the scene on the sound of the caller's line going dead.")


def canned_research(prompt, context, model, history=None, client=None):
    LEDGER.record(model, "research", 0.0036)
    return ("Real capsule hotels stack units two high and guests keep their shoes in "
            "lockers at the door [1]. The Meridian's forty-high stack is a deliberate "
            "exaggeration, so lean on the smell and the hum [1].")


def canned_brainstorm(context, model, client=None):
    LEDGER.record(model, "brainstorm", 0.0039)
    return ["What if the caller ID did not go dark, but showed Rook's own number?",
            "Let the rain stop mid-sentence, so the market hears what it was covering.",
            "Wren is lying about something small; let Rook notice and say nothing.",
            "The holo koi turns toward the door a beat before anyone walks in."]


app_mod.ask_writer = canned_ask
app_mod.research_answer = canned_research
app_mod.brainstorm_ideas = canned_brainstorm

SIZE = (100, 32)
CROPS = json.loads((OUT / "crops.json").read_text()) if (OUT / "crops.json").exists() else {}


def mk(project):
    app = ChiselApp(project)
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


def reset_state():
    for f in STATE.glob("*"):
        if f.name != "stats":
            shutil.rmtree(f) if f.is_dir() else f.unlink()
    (STATE / "settings.json").write_text(json.dumps({"tour_seen": True}))


async def main():
    from chisel.tui.snapshotscreens import CompareScreen, SnapshotsScreen
    from chisel.tui.structurescreens import TrashScreen

    build_project()
    reset_state()
    project = Project.open(PROJ)
    scenes = project.list_scenes()
    project = Project.open(PROJ)

    app = mk(project)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(1.0)
        scenes = app.project.list_scenes()
        app.open_file(scenes[2])          # Capsule 7-19 (scene details, collection)
        await pilot.pause(0.8)
        shot(app, "tui_parts")
        await pilot.resize_terminal(100, 40)
        await pilot.pause(0.4)
        app.edit_details()
        await pilot.pause(0.5)
        shot(app, "tui_details", modal=True)
        await pilot.press("escape")
        await pilot.resize_terminal(100, 32)
        await pilot.pause(0.4)
        app.open_collections()
        await pilot.pause(0.5)
        shot(app, "tui_collections", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        app.open_trash()
        await pilot.pause(0.5)
        assert isinstance(app.screen, TrashScreen), app.screen
        shot(app, "tui_trash", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        # comments: Capsule 7-19 has a detached one, the Stairwell an anchored one
        app.open_file(scenes[2])
        await pilot.pause(0.6)
        app.open_comments()
        await pilot.pause(0.5)
        shot(app, "tui_comments", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        # snapshots of Capsule 7-19, then compare
        app.open_file(scenes[2])
        await pilot.pause(0.6)
        app.open_snapshots()
        await pilot.pause(0.5)
        assert isinstance(app.screen, SnapshotsScreen), app.screen
        shot(app, "tui_snapshots", modal=True)
        await pilot.press("enter")
        await pilot.pause(0.6)
        assert isinstance(app.screen, CompareScreen), app.screen
        shot(app, "tui_compare", modal=True)
        await pilot.press("escape")
        await pilot.pause(0.3)
        await pilot.press("escape")
        await pilot.pause(0.3)
        # git: the commit prompt
        app.sync_commit_prompt()
        await pilot.pause(0.6)
        shot(app, "tui_commit", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        # stats
        app.open_stats()
        await pilot.pause(0.5)
        shot(app, "tui_stats", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        # sprint: the length choice, then a running sprint in the status bar
        app.focus_sprint()
        await pilot.pause(0.4)
        shot(app, "tui_sprint", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        app._start_sprint(25, False)
        await pilot.resize_terminal(124, 32)
        await pilot.pause(1.2)
        shot(app, "tui_statusbar")
        await pilot.resize_terminal(100, 32)
        await pilot.pause(0.3)
        app._end_sprint(cancelled=True)
        await pilot.pause(0.4)
        # brainstorm
        app.brainstorm()
        await pilot.pause(1.5)
        shot(app, "tui_brainstorm", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        # the assistant: a chat answer, then a research answer with its cited note
        app.open_assistant()
        await pilot.pause(0.5)
        await pilot.press(*"How can I make the stairwell scene more tense?")
        await pilot.press("enter")
        await pilot.pause(1.5)
        shot(app, "tui_assistant", modal=True)
        await pilot.press("escape")
        await pilot.pause()
        app.open_chat_history()
        await pilot.pause(0.5)
        shot(app, "tui_chats", modal=True)
        await pilot.press("escape")
        await pilot.pause()

    reset_state()
    app = mk(Project.open(PROJ))
    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause(0.6)
        app.action_settings()
        await pilot.pause()
        shot(app, "settings_v4", modal=True)


def canned_describe(context, model, client=None):
    LEDGER.record(model, "image-prompt", 0.0009)
    return ("A capsule hotel corridor at night: stacked fiberglass pods lit the color of weak tea, "
            "a ladder to the seventh tier, police tape, wet floor, one uniformed man arguing "
            "with the night manager.")


def canned_image(prompt, model, client=None, style=None):
    from chisel.gui.mockai import placeholder_png
    LEDGER.record("mock/image", "image", 0.0336)
    return [(placeholder_png(prompt), "png")]


app_mod.suggest_image_prompt = canned_describe
app_mod.generate_image = canned_image


async def v5():
    if os.environ.get("ONLY_V5"):
        build_project()
    reset_state()
    project = Project.open(PROJ)
    app = mk(project)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(1.0)
        scenes = app.project.list_scenes()
        app.open_file(scenes[2])
        await pilot.pause(0.8)
        app.export_manuscript()
        await pilot.pause(0.8)
        shot(app, "tui_export", modal=True)
        await pilot.press("ctrl+s")
        await pilot.pause(3.0)
        shot(app, "tui_export_done")
        app.inspiration_prompt("")
        await pilot.pause(0.5)
        await pilot.press(*"A rain-slick night market under a rail spur")
        await pilot.pause(0.3)
        shot(app, "tui_insp_prompt", modal=True)
        await pilot.press("escape")
        await pilot.pause(0.3)
        app.open_inspiration()
        await pilot.pause(0.6)
        shot(app, "tui_insp_list", modal=True)
        await pilot.press("escape")
        await pilot.pause(0.3)
    reset_state()
    app = mk(Project.open(PROJ))
    async with app.run_test(size=(100, 52)) as pilot:
        await pilot.pause(0.6)
        app.action_settings()
        await pilot.pause()
        shot(app, "tui_settings_images", modal=True)


if not os.environ.get("ONLY_V5"):
    asyncio.run(main())
asyncio.run(v5())
print("TMP", TMP)
shutil.rmtree(TMP, ignore_errors=True)
