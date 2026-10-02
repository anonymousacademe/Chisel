"""The packaged apps' --self-test (the real checks run against the built bundles in CI)."""

import json
import tomllib
from pathlib import Path

import lorewrite
from lorewrite import selftest


def test_report_lists_every_check_and_exit_status_follows_it(monkeypatch, capsys):
    monkeypatch.setattr(selftest, "CHECKS", [("fine", lambda: "ok"), ("broken", lambda: 1 / 0)])
    report = selftest.run()
    assert report["ok"] is False and report["version"] == lorewrite.__version__
    assert [(c["name"], c["ok"]) for c in report["checks"]] == [("fine", True), ("broken", False)]
    assert "ZeroDivisionError" in report["checks"][1]["detail"]
    assert selftest.main() == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
    monkeypatch.setattr(selftest, "CHECKS", [("fine", lambda: "ok")])
    assert selftest.main() == 0


def test_the_data_checks_that_need_no_built_ui_pass():
    names = dict(selftest.CHECKS)
    for name in ("fonts", "spelling", "hyphenation", "textual", "tls", "export layouts", "pdf export"):
        assert names[name]()


def test_version_has_a_single_source():
    cfg = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in cfg["project"]["dynamic"] and "version" not in cfg["project"]
    assert cfg["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "lorewrite.__version__"}
