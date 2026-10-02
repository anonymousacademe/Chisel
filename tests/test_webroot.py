"""The built UI is found in the package first, then in the repo's gui/dist."""

import pytest

from lorewrite.gui import app, devserver, webroot
from lorewrite.gui.api import Api


def _fake(tmp_path, name):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "index.html").write_text("<html></html>")
    return folder


def test_packaged_build_wins_over_repo_dist(tmp_path, monkeypatch):
    packaged, repo = _fake(tmp_path, "web"), _fake(tmp_path, "dist")
    monkeypatch.setattr(webroot, "PACKAGED", packaged)
    monkeypatch.setattr(webroot, "REPO_DIST", repo)
    assert webroot.find_dist() == packaged


def test_repo_dist_is_the_fallback(tmp_path, monkeypatch):
    repo = _fake(tmp_path, "dist")
    monkeypatch.setattr(webroot, "PACKAGED", tmp_path / "nothing")
    monkeypatch.setattr(webroot, "REPO_DIST", repo)
    assert webroot.find_dist() == repo


def test_missing_build_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(webroot, "PACKAGED", tmp_path / "a")
    monkeypatch.setattr(webroot, "REPO_DIST", tmp_path / "b")
    assert webroot.find_dist() is None
    with pytest.raises(SystemExit, match="not built"):
        webroot.require_dist("lorewrite-gui")
    with pytest.raises(SystemExit, match="not built"):
        devserver.serve(Api())
    with pytest.raises(SystemExit, match="lorewrite-gui: the UI is not built"):
        app.main([])
