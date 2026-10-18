"""Generated figures: trust, execution contract, staleness, provenance (plan 7.4). No matplotlib needed."""

import subprocess
import sys
import threading
import time

import pytest

from chisel.core import figscripts, settings
from chisel.core.project import Project

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-data"
WRITE_PNG = f"OUT.write_bytes({PNG!r})\n"


@pytest.fixture
def proj(tmp_path):
    p = Project.create(tmp_path / "paper", "Paper", "research")
    (p.root / "figures").mkdir(exist_ok=True)
    (p.root / "data").mkdir(exist_ok=True)
    (p.root / "data" / "flow.csv").write_text("x,y\n1,2\n", encoding="utf-8", newline="\n")
    return p


@pytest.fixture(autouse=True)
def interpreter(tmp_path):
    settings.set(figscripts.INTERPRETER_SETTING, sys.executable)


def make_figure(project, script_text=WRITE_PNG, label="flow", body="Notes here.\n"):
    folder = project.root / "figures"
    (folder / f"fig-{label}.py").write_text(script_text, encoding="utf-8", newline="\n")
    (folder / f"fig-{label}.md").write_text(
        f"---\ncaption: Flow\nsource: script\nscript: fig-{label}.py\ndata: [data/flow.csv]\n---\n{body}",
        encoding="utf-8", newline="\n")
    return label


def trust(project, label="flow"):
    figscripts.trust_figure(project, label, figscripts.script_sha(project, label))


def set_script(project, text, label="flow"):
    (project.root / "figures" / f"fig-{label}.py").write_text(text, encoding="utf-8", newline="\n")


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# -- trust -------------------------------------------------------------------------------


def test_untrusted_script_is_refused_and_nothing_runs(proj):
    make_figure(proj, "open(OUT.parent / 'ran', 'w').close()\n" + WRITE_PNG)
    assert figscripts.trust_state(proj, "flow") == "untrusted"
    res = figscripts.run_figure(proj, "flow")
    assert res.refused and res.status == "failed" and "confirmed" in res.error
    assert not (proj.root / "figures" / "fig-flow.png").exists()


def test_trust_then_run_writes_png_and_provenance(proj):
    make_figure(proj)
    trust(proj)
    assert figscripts.trust_state(proj, "flow") == "trusted"
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "current", res.error
    assert (proj.root / "figures" / "fig-flow.png").read_bytes() == PNG
    md = (proj.root / "figures" / "fig-flow.md").read_text(encoding="utf-8")
    assert md.endswith("---\nNotes here.\n")                 # body untouched
    assert "script_sha:" in md and "data_sha:" in md and "status: ok" in md
    assert res.provenance["python"].count(".") >= 1
    assert figscripts.figure_status(proj, "flow") == "current"
    assert figscripts.trust_state(proj, "flow") == "trusted"


def test_changed_script_asks_again(proj):
    make_figure(proj)
    trust(proj)
    set_script(proj, WRITE_PNG + "# edited\n")
    assert figscripts.trust_state(proj, "flow") == "changed"
    res = figscripts.run_figure(proj, "flow")
    assert res.refused and "changed" in res.error
    trust(proj)
    assert figscripts.trust_state(proj, "flow") == "trusted"


def test_trust_figure_refuses_a_hash_that_is_not_the_current_script(proj):
    make_figure(proj)
    sha = figscripts.script_sha(proj, "flow")
    set_script(proj, WRITE_PNG + "# edited after the dialog\n")
    with pytest.raises(ValueError):
        figscripts.trust_figure(proj, "flow", sha)
    assert figscripts.trust_state(proj, "flow") == "untrusted"


def test_trust_record_lives_only_in_the_state_folder(proj):
    from chisel.core.recents import default_state_dir
    make_figure(proj)
    trust(proj)
    assert list((default_state_dir() / "figure-trust").glob("*.json"))
    assert not [p for p in proj.root.rglob("*") if "trust" in p.name.lower()]


def test_trust_record_placed_in_the_project_is_ignored(proj):
    make_figure(proj)
    sha = figscripts.script_sha(proj, "flow")
    # a cloned project that tries to arrive pre-confirmed, in every shape one could think of
    (proj.root / ".chisel").mkdir(exist_ok=True)
    fake = f'{{"scripts": {{"figures/fig-flow.md": "{sha}"}}}}'
    for rel in (".chisel/figure-trust.json", "figure-trust.json", "figures/trust.json"):
        (proj.root / rel).write_text(fake, encoding="utf-8")
    md = proj.root / "figures" / "fig-flow.md"
    md.write_text(md.read_text(encoding="utf-8").replace(
        "---\nNotes", f"trusted: true\nrun: {{script_sha: {sha}, status: ok, trusted: true}}\n---\nNotes", 1),
        encoding="utf-8")
    assert figscripts.trust_state(proj, "flow") == "untrusted"
    assert figscripts.run_figure(proj, "flow").refused


def test_a_moved_project_is_not_trusted(proj, tmp_path):
    import shutil
    make_figure(proj)
    trust(proj)
    clone = tmp_path / "clone"
    shutil.copytree(proj.root, clone)
    assert figscripts.trust_state(Project.open(clone), "flow") == "untrusted"


# -- interpreter -------------------------------------------------------------------------


def test_interpreter_inside_the_project_is_refused(proj):
    make_figure(proj)
    trust(proj)
    fake = proj.root / "python.exe"
    fake.write_bytes(b"not a python")
    settings.set(figscripts.INTERPRETER_SETTING, str(fake))
    res = figscripts.run_figure(proj, "flow")
    assert res.refused and "inside the project" in res.error
    sub = proj.root / "tools" / "bin"
    sub.mkdir(parents=True)
    (sub / "py").write_bytes(b"x")
    settings.set(figscripts.INTERPRETER_SETTING, str(sub / "py"))
    assert figscripts.run_figure(proj, "flow").refused


def test_no_interpreter_names_the_setting(proj):
    make_figure(proj)
    trust(proj)
    settings.set(figscripts.INTERPRETER_SETTING, "")
    res = figscripts.run_figure(proj, "flow")
    assert res.refused and figscripts.INTERPRETER_SETTING in res.error


# -- execution contract ------------------------------------------------------------------


def test_planted_module_is_not_imported(proj):
    (proj.root / "figures" / "json.py").write_text("raise RuntimeError('planted')\n", encoding="utf-8")
    (proj.root / "data" / "json.py").write_text("raise RuntimeError('planted')\n", encoding="utf-8")
    make_figure(proj, "import json\nprint(json.__file__)\n" + WRITE_PNG)
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "current", res.error
    assert "planted" not in res.stderr
    assert str(proj.root.resolve()).lower() not in res.stdout.lower()


def test_runs_a_copy_in_a_temp_folder_not_the_project(proj):
    make_figure(proj, "import os, sys\nprint('CWD=' + os.getcwd())\nprint('ARGV=' + sys.argv[0])\n" + WRITE_PNG)
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "current", res.error
    root = str(proj.root.resolve()).lower()
    assert root not in res.stdout.lower()
    assert "chisel-fig-" in res.stdout


def test_timeout_kills_the_whole_process_tree(proj):
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "(DATA_DIR / 'pid.txt').write_text(str(child.pid))\n"
        "time.sleep(120)\n"
    )
    make_figure(proj, script)
    trust(proj)
    t0 = time.monotonic()
    res = figscripts.run_figure(proj, "flow", timeout=4)
    assert res.timed_out and res.status == "failed" and "seconds" in res.error
    assert time.monotonic() - t0 < 60
    pid_file = proj.root / "data" / "pid.txt"
    assert pid_file.exists(), "the script did not get to start its child"
    pid = int(pid_file.read_text())
    for _ in range(50):
        if not alive(pid):
            break
        time.sleep(0.2)
    assert not alive(pid)


def test_cancel_stops_the_run_and_leaves_the_figure_alone(proj):
    make_figure(proj, "import time\ntime.sleep(120)\n")
    trust(proj)
    md = proj.root / "figures" / "fig-flow.md"
    before = md.read_bytes()
    stop = threading.Event()
    threading.Timer(1.5, stop.set).start()
    res = figscripts.run_figure(proj, "flow", timeout=60, cancel=stop)
    assert res.cancelled and res.status == "failed"
    assert md.read_bytes() == before


def test_stdout_and_stderr_are_capped(proj):
    make_figure(proj, "import sys\nsys.stdout.write('o' * 2_000_000)\nsys.stderr.write('e' * 2_000_000)\n"
                + WRITE_PNG)
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "current", res.error
    assert len(res.stdout) <= figscripts.OUTPUT_CAP and len(res.stderr) <= figscripts.OUTPUT_CAP
    assert len(res.stdout) > 1000


def test_environment_is_scrubbed(proj, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    monkeypatch.setenv("CHISEL_SOMETHING", "x")
    monkeypatch.setenv("LOREWRITE_STATE_DIR", "x")
    monkeypatch.setenv("PYTHONSTARTUP", "x")
    monkeypatch.setenv("KEEP_ME", "yes")
    make_figure(proj, "import os\nprint('|'.join(sorted(os.environ)))\nprint(os.environ.get('MPLBACKEND'))\n"
                + WRITE_PNG)
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "current", res.error
    names = res.stdout.splitlines()[0].split("|")
    assert not [n for n in names if n.upper().startswith(("CHISEL_", "LOREWRITE_", "PYTHON")) or n == "OPENROUTER_API_KEY"]
    assert "KEEP_ME" in names
    assert res.stdout.splitlines()[1] == "Agg"
    assert "sk-secret" not in res.stdout + res.stderr


def test_failed_run_keeps_the_old_png_byte_identical(proj):
    make_figure(proj)
    trust(proj)
    assert figscripts.run_figure(proj, "flow").status == "current"
    png = proj.root / "figures" / "fig-flow.png"
    old = png.read_bytes()
    set_script(proj, "raise RuntimeError('boom here')\n")
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "failed" and "boom here" in res.error and not res.refused
    assert png.read_bytes() == old
    assert figscripts.figure_status(proj, "flow") == "failed"
    # a wrong output also leaves it alone: not a PNG, and no output at all
    set_script(proj, "OUT.write_bytes(b'GIF89a not a png')\n")
    trust(proj)
    assert "not a PNG" in figscripts.run_figure(proj, "flow").error
    set_script(proj, "pass\n")
    trust(proj)
    assert "did not write" in figscripts.run_figure(proj, "flow").error
    assert png.read_bytes() == old


def test_oversized_output_is_rejected(proj, monkeypatch):
    monkeypatch.setattr("chisel.core.objects.MAX_IMAGE_BYTES", 100)
    make_figure(proj, "OUT.write_bytes(b'\\x89PNG\\r\\n\\x1a\\n' + b'x' * 500)\n")
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "failed" and "10 MB" in res.error
    assert not (proj.root / "figures" / "fig-flow.png").exists()


# -- status ------------------------------------------------------------------------------


def test_status_missing_current_stale(proj):
    make_figure(proj)
    assert figscripts.figure_status(proj, "flow") == "missing"
    trust(proj)
    figscripts.run_figure(proj, "flow")
    assert figscripts.figure_status(proj, "flow") == "current"
    (proj.root / "data" / "flow.csv").write_text("x,y\n1,3\n", encoding="utf-8", newline="\n")
    assert figscripts.figure_status(proj, "flow") == "stale"
    figscripts.run_figure(proj, "flow")
    assert figscripts.figure_status(proj, "flow") == "current"
    set_script(proj, WRITE_PNG + "# more\n")
    assert figscripts.figure_status(proj, "flow") == "stale"


def test_png_without_a_run_record_is_stale(proj):
    make_figure(proj)
    (proj.root / "figures" / "fig-flow.png").write_bytes(PNG)
    assert figscripts.figure_status(proj, "flow") == "stale"


def test_ids_may_be_label_prefixed_or_path(proj):
    make_figure(proj)
    for ident in ("flow", "fig:flow", "fig-flow", "figures/fig-flow.md"):
        assert figscripts.trust_state(proj, ident) == "untrusted"
    with pytest.raises(ValueError):
        figscripts.trust_state(proj, "../flow")


def test_script_must_stay_inside_the_project(proj):
    make_figure(proj)
    md = proj.root / "figures" / "fig-flow.md"
    md.write_text(md.read_text(encoding="utf-8").replace("script: fig-flow.py", "script: ../../evil.py"),
                  encoding="utf-8")
    assert figscripts.trust_state(proj, "flow") == "untrusted"
    assert figscripts.run_figure(proj, "flow").refused


def test_starter_template_and_style_are_package_data():
    assert "make_figure" in figscripts.starter_script()
    assert figscripts.STYLE_FILE.is_file() and figscripts.RUNNER_FILE.is_file()


# -- fiction projects --------------------------------------------------------------------


def test_fiction_projects_are_unaffected(tmp_path):
    story = Project.create(tmp_path / "novel", "Novel")
    before = sorted(p.relative_to(story.root).as_posix() for p in story.root.rglob("*"))
    for fn in (figscripts.trust_state, figscripts.figure_status):
        with pytest.raises(ValueError):
            fn(story, "flow")
    with pytest.raises(ValueError):
        figscripts.run_figure(story, "flow")
    with pytest.raises(ValueError):
        figscripts.trust_figure(story, "flow", "0" * 64)
    assert sorted(p.relative_to(story.root).as_posix() for p in story.root.rglob("*")) == before


# -- hardening: links, interpreter path, bounded reads -----------------------------------


def _symlink_or_skip(link, target):
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks here")


def test_write_atomic_uses_random_exclusive_temp_names(tmp_path, monkeypatch):
    from chisel.core import objects
    seen = []
    real = objects.tempfile.mkstemp

    def spy(*a, **kw):
        fd, name = real(*a, **kw)
        seen.append(name)
        return fd, name
    monkeypatch.setattr(objects.tempfile, "mkstemp", spy)
    target = tmp_path / "x.png"
    objects.write_atomic(target, b"one")
    objects.write_atomic(target, b"two")
    assert target.read_bytes() == b"two"
    assert len(seen) == 2 and seen[0] != seen[1]
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())
    # a file already sitting at the old fixed temp name is neither used nor touched
    fixed = tmp_path / ".x.png.tmp"
    fixed.write_bytes(b"mine")
    objects.write_atomic(target, b"three")
    assert fixed.read_bytes() == b"mine" and target.read_bytes() == b"three"


def test_write_atomic_refuses_a_link_target(tmp_path):
    from chisel.core import objects
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"keep")
    link = tmp_path / "l.png"
    _symlink_or_skip(link, outside)
    with pytest.raises(OSError):
        objects.write_atomic(link, b"evil")
    assert outside.read_bytes() == b"keep"


def test_symlinked_png_or_planted_temp_never_writes_outside(proj, tmp_path):
    make_figure(proj)
    trust(proj)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"keep")
    png = proj.root / "figures" / "fig-flow.png"
    _symlink_or_skip(png, outside)
    res = figscripts.run_figure(proj, "flow")
    assert res.refused and "link" in res.error
    assert outside.read_bytes() == b"keep"


def test_planted_temp_symlink_is_not_followed(proj, tmp_path):
    make_figure(proj)
    trust(proj)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"keep")
    _symlink_or_skip(proj.root / "figures" / ".fig-flow.png.tmp", outside)
    _symlink_or_skip(proj.root / "figures" / ".fig-flow.md.tmp", outside)
    assert figscripts.run_figure(proj, "flow").status == "current"
    assert outside.read_bytes() == b"keep"


def test_symlinked_figures_folder_is_refused(tmp_path):
    p = Project.create(tmp_path / "paper2", "Paper", "research")
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "fig-flow.py").write_text(WRITE_PNG, encoding="utf-8", newline="\n")
    (real / "fig-flow.md").write_text("---\ncaption: F\nsource: script\nscript: fig-flow.py\n---\n",
                                      encoding="utf-8", newline="\n")
    folder = p.root / "figures"
    if folder.exists():
        folder.rmdir()
    _symlink_or_skip(folder, real)
    try:
        trust(p)
        res = figscripts.run_figure(p, "flow")
    except ValueError:
        return                                   # already refused earlier (path leaves the project)
    assert res.refused
    assert not (real / "fig-flow.png").exists()


def test_relative_interpreter_is_refused(proj):
    make_figure(proj)
    trust(proj)
    settings.set(figscripts.INTERPRETER_SETTING, "python")
    res = figscripts.run_figure(proj, "flow")
    assert res.refused and "full path" in res.error


def test_oversized_file_that_grows_after_the_size_check_is_bounded(proj, monkeypatch):
    monkeypatch.setattr("chisel.core.objects.MAX_IMAGE_BYTES", 100)
    make_figure(proj, "OUT.write_bytes(b'\\x89PNG\\r\\n\\x1a\\n' + b'x' * 5000)\n")
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.status == "failed" and "10 MB" in res.error


def test_data_hash_is_chunked_and_capped(proj, monkeypatch):
    make_figure(proj)
    small = figscripts._data_sha(proj, [proj.root / "data" / "flow.csv"])
    assert len(small) == 64
    monkeypatch.setattr(figscripts, "DATA_CAP_BYTES", 4)
    with pytest.raises(figscripts.DataTooLarge):
        figscripts._data_sha(proj, [proj.root / "data" / "flow.csv"])
    assert figscripts.figure_status(proj, "flow") in ("missing", "stale")
    trust(proj)
    res = figscripts.run_figure(proj, "flow")
    assert res.refused and "larger" in res.error
