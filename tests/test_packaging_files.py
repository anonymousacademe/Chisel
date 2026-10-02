"""The packaging files stay in step with the code (the builds run in CI, not here)."""

import ast
import re
from pathlib import Path

import pytest

import lorewrite

ROOT = Path(__file__).resolve().parents[1]


def test_spec_and_entry_compile():
    for name in ("packaging/lorewriter.spec", "packaging/entry.py", "packaging/build.py"):
        ast.parse((ROOT / name).read_text(encoding="utf-8"), name)


def test_inno_script_is_per_user_and_names_both_executables():
    iss = (ROOT / "packaging/lorewriter.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss
    assert "LoreWriter.exe" in iss and "lorewrite.exe" in iss
    assert "windows-setup" in iss


def test_build_script_reads_the_one_version():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lw_build", ROOT / "packaging/build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.version() == lorewrite.__version__


def test_release_workflow_is_valid_yaml_with_pinned_actions():
    yaml = pytest.importorskip("yaml")
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    on = wf.get(True) or wf["on"]  # PyYAML reads the key `on` as True
    assert "workflow_dispatch" in on and on["push"]["tags"] == ["v*"]
    for uses in re.findall(r"uses:\s*(\S+)", text):
        assert re.search(r"@(v\d+|[0-9a-f]{40})", uses), f"unpinned action: {uses}"
    assert "contents: write" in text  # only the release job needs it


def test_icons_exist_for_every_os():
    icons = ROOT / "gui/src-tauri/icons"
    for name in ("icon.ico", "icon.icns", "icon.png"):
        assert (icons / name).is_file()
