"""Real exports of a temp copy of the Residual example, for the Fifth Edition.

    PYTHONPATH=src .venv/bin/python docs/user-guide/build/export_samples.py WORKDIR

Builds the rich project (rich_project.py) in WORKDIR, sets an author, runs the
real exporter for every format (no AI, no network), checks the files and
renders sample pages of the three PDF layouts to build/exportshots/*.png.
"""
import json, os, re, subprocess, sys, tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
work = Path(sys.argv[1])
work.mkdir(parents=True, exist_ok=True)
state = work / "state"
proj = work / "proj"
os.environ["CHISEL_STATE_DIR"] = str(state)
subprocess.run([sys.executable, str(HERE / "rich_project.py"), str(proj), str(state)], check=True,
               env={**os.environ, "PYTHONPATH": str(REPO / "src")})
import chisel
assert Path(chisel.__file__).resolve().is_relative_to(REPO)
toml = proj / "project.toml"
toml.write_text(toml.read_text().replace('author = ""', 'author = "Mara Vale"'))

from chisel.core.export import ExportOptions, run_export  # noqa: E402
from chisel.core.project import Project  # noqa: E402

p = Project.open(proj)
OUT = HERE / "exportshots"
OUT.mkdir(exist_ok=True)
runs = {
    "book": dict(format="pdf", layout="book", toc=True, copyright="First edition, October 2026"),
    "manuscript": dict(format="pdf", layout="manuscript"),
    "plain": dict(format="pdf", layout="plain"),
    "docx": dict(format="docx"), "epub": dict(format="epub"),
    "md": dict(format="md"), "tex": dict(format="tex"),
}
results = {}
for key, kw in runs.items():
    r = run_export(p, ExportOptions.from_dict(kw))
    results[key] = r
    print(key, r.rel, r.pages, r.words, r.warnings)
    assert r.path.stat().st_size > 0


def render(key, page, name, dpi=130):
    pdf = results[key].path
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png",
                    "-singlefile", str(pdf), str(OUT / name)], check=True)


def find_page(key, needle):
    pdf = results[key].path
    n = results[key].pages
    for i in range(1, n + 1):
        t = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), str(pdf), "-"],
                           capture_output=True, text=True).stdout
        if needle in t:
            return i
    return 2


render("book", 1, "pdf_book_title")
render("book", find_page("book", "Contents"), "pdf_book_toc")
render("book", find_page("book", "The rain in the Hollow"), "pdf_book_page")
render("manuscript", 1, "pdf_ms_title")
render("manuscript", find_page("manuscript", "The rain in the Hollow"), "pdf_ms_page")
render("plain", find_page("plain", "The rain in the Hollow"), "pdf_plain_page")
json.dump({k: {"rel": v.rel, "pages": v.pages, "words": v.words, "warnings": v.warnings}
           for k, v in results.items()}, open(OUT / "results.json", "w"), indent=1)
for f in sorted((proj / "exports").iterdir()):
    print(f.name, f.stat().st_size)
