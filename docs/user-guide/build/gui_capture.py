#!/usr/bin/env python3
"""Capture the desktop-GUI figures headlessly (no window ever opens on the desktop).

    ~/chisel/.venv-gui/bin/python docs/user-guide/build/gui_capture.py

For each stage it copies examples/residual to a temp dir, starts
build/gui_server.py (the headless devserver with canned, local AI) on a free
port, drives headless Chromium over the DevTools protocol with
build/gui_capture.mjs (Node), and stops the server. Everything it starts is
stopped by PID/process group; it picks its own free debugging port, and it never touches other processes or windows.
Output: build/guishots/*.png (the guide converts them to grayscale).
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STAGES = ["launch", "window", "spell", "notes", "consistency", "style",
          "writing", "chat", "settings", "conflict",
          "structure", "history", "notes4", "aids", "export5", "insp5"]


def free_port() -> int:
    """A free local port for our own browser's debugging endpoint (other
    browsers on the machine are none of our business)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop(proc: subprocess.Popen, group: bool = False) -> None:
    if proc.poll() is not None:
        return
    try:
        (os.killpg(proc.pid, signal.SIGTERM) if group else proc.terminate())
        proc.wait(timeout=8)
    except Exception:
        try:
            (os.killpg(proc.pid, signal.SIGKILL) if group else proc.kill())
        except Exception:
            pass


def main() -> None:
    only = sys.argv[1:] or STAGES
    PORT = free_port()
    tmp = Path(tempfile.mkdtemp(prefix="lwgui-", dir=os.environ.get("LW_SCRATCH")))
    chrome = subprocess.Popen(
        ["chromium", "--headless=new", f"--remote-debugging-port={PORT}",
         f"--user-data-dir={tmp / 'profile'}", "--window-size=1280,800",
         "--hide-scrollbars", "--disable-gpu", "--no-first-run", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        for stage in only:
            work = tmp / stage
            state = work / "state"
            project = work / "residual"
            state.mkdir(parents=True)
            # a richer copy of the example: parts, snapshots, comments, research, stats, git
            project = work / "proj"
            subprocess.run([sys.executable, str(HERE / "rich_project.py"), str(project), str(state),
                            "--git", "--remote"] + (["--inspiration"] if stage in ("insp5", "export5") else []),
                           check=True,
                           env={**os.environ, "PYTHONPATH": str(REPO / "src"),
                                "PYTHONDONTWRITEBYTECODE": "1"})
            (state / "settings.json").write_text(json.dumps({"tour_seen": True}))
            args = [sys.executable, str(HERE / "gui_server.py")]
            if stage == "launch":
                novels = work / "novels"
                shutil.copytree(REPO / "examples" / "residual", novels / "residual")
                (novels / "the-salt-road").mkdir(parents=True)
                (novels / "the-salt-road" / "project.toml").write_text('title = "The Salt Road"\n')
                (state / "recent.json").write_text(json.dumps([
                    {"path": str(novels / "residual"), "title": "Residual", "opened_at": 1790000000.0},
                    {"path": str(novels / "the-salt-road"), "title": "The Salt Road", "opened_at": 1789000000.0}]))
            else:
                args.append(str(project))
            env = {**os.environ, "CHISEL_STATE_DIR": str(state),
                   "OPENROUTER_API_KEY": "sk-mock",
                   "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(REPO / "src")}
            server = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, text=True)
            try:
                url = server.stdout.readline().strip()
                assert url.startswith("http://127.0.0.1:"), url
                r = subprocess.run(["node", str(HERE / "gui_capture.mjs"), url, str(PORT),
                                    str(project), stage], check=False)
                if r.returncode:
                    sys.exit(f"stage {stage} failed")
            finally:
                stop(server)
    finally:
        stop(chrome, group=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
