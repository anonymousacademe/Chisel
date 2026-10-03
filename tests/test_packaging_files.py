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
    assert "Chisel.exe" in iss and "lorewrite.exe" in iss
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
    release = text.split("  release:", 1)[1]
    needs = re.search(r"needs: \[(.*?)\]", release).group(1)
    assert "macos-arm64" in needs and "macos-intel" in needs
    assert "needs.macos-arm64.result == 'success'" in release
    assert "needs.macos-intel.result" not in release          # Intel is best effort: never required
    assert "pattern: release-*" in release                    # and web-ui is not attached
    assert "sha256sum *" not in release and "release/*" in release  # only the flattened release files


def test_icons_exist_for_every_os():
    icons = ROOT / "gui/src-tauri/icons"
    for name in ("icon.ico", "icon.icns", "icon.png"):
        assert (icons / name).is_file()


def test_window_icon_matches_the_platform():
    """pywebview's WinForms backend only accepts an .ico; the other backends take the PNG."""
    gui = ROOT / "src/lorewrite/gui"
    assert (gui / "icon.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"   # an ICO header, not a renamed PNG
    assert (gui / "icon.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    src = (gui / "app.py").read_text(encoding="utf-8")
    assert '"icon.ico" if sys.platform == "win32" else "icon.png"' in src
    assert '"icon.ico"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _build_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lw_build", ROOT / "packaging/build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_appimagetool_is_pinned_and_verified(tmp_path, monkeypatch):
    mod = _build_module()
    assert "continuous" not in mod.APPIMAGETOOL_URL and mod.APPIMAGETOOL_VERSION in mod.APPIMAGETOOL_URL
    assert re.fullmatch(r"[0-9a-f]{64}", mod.APPIMAGETOOL_SHA256)
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    def fake(url, dest):  # a download with the wrong content
        Path(dest).write_bytes(b"tampered")
    monkeypatch.setattr(mod.urllib.request, "urlretrieve", fake)
    with pytest.raises(SystemExit, match="SHA-256"):
        mod.appimagetool()
    assert not list((tmp_path / "build").glob("appimagetool*"))   # nothing kept, nothing executable
    # a cached file that does not verify is discarded, not trusted
    cached = tmp_path / "build" / f"appimagetool-{mod.APPIMAGETOOL_VERSION}-x86_64.AppImage"
    cached.write_bytes(b"old")
    with pytest.raises(SystemExit):
        mod.appimagetool()
    assert not cached.exists()
    # the right bytes pass
    data = b"genuine"
    monkeypatch.setattr(mod, "APPIMAGETOOL_SHA256", __import__("hashlib").sha256(data).hexdigest())
    monkeypatch.setattr(mod.urllib.request, "urlretrieve", lambda u, d: Path(d).write_bytes(data))
    assert mod.appimagetool().read_bytes() == data


def test_workflow_downloads_nothing_unpinned():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "continuous" not in text and not re.search(r"\b(curl|wget)\b", text)
    assert "choco install innosetup --version=" in text


def test_render_env_is_set_only_on_the_linux_job():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    head, linux_on = text.split("  linux:", 1)
    assert "LOREWRITE_SELFTEST_RENDER" not in head                    # not workflow-wide
    assert "LOREWRITE_SELFTEST_RENDER" in linux_on.split("  windows:", 1)[0]
    assert "LOREWRITE_SELFTEST_RENDER" not in linux_on.split("  windows:", 1)[1]
