"""Cheap static check: every third-party import in src/ is declared."""
import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# distribution name -> top-level modules it provides (including the ones we
# import from its own hard dependencies: rich via textual, PIL via reportlab)
PROVIDES = {
    "textual": {"textual", "rich"},
    "pyyaml": {"yaml"},
    "openai": {"openai"},
    "keyring": {"keyring"},
    "pyspellchecker": {"spellchecker"},
    "platformdirs": {"platformdirs"},
    "pywebview": {"webview"},
    "reportlab": {"reportlab", "PIL"},
    "pyphen": {"pyphen"},
}


def _names(lines) -> set[str]:
    out = set()
    for line in lines:
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        out.add(re.split(r"[\[<>=!~; ]", line, maxsplit=1)[0].lower())
    return out


def _requirements() -> set[str]:
    return _names((ROOT / "requirements.txt").read_text().splitlines())


def test_every_import_is_declared():
    modules = set().union(*(PROVIDES[n] for n in _requirements() if n in PROVIDES))
    missing = {}
    for path in (ROOT / "src" / "lorewrite").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                tops = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                tops = [node.module.split(".")[0]]
            else:
                continue
            for top in tops:
                if top in sys.stdlib_module_names or top in ("lorewrite", "__future__") or top in modules:
                    continue
                missing.setdefault(top, set()).add(path.name)
    assert not missing, f"imported but not in requirements.txt: {missing}"


def test_requirements_cover_pyproject():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    declared = _names(project["dependencies"])
    for extra in ("gui", "export"):
        declared |= _names(project["optional-dependencies"][extra])
    assert declared <= _requirements(), declared - _requirements()
    dev = _names(project["optional-dependencies"]["dev"])
    assert dev <= _names((ROOT / "requirements-dev.txt").read_text().splitlines())
    assert set(PROVIDES) >= _requirements()
