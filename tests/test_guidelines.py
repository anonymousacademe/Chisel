"""Guideline documents: core/paper/guidelines.py and gui/research_guidelines_api.py."""

import io
import zipfile

import pytest

from chisel.ai import continuity, links, writing
from chisel.ai.budget import Budget, fit, render
from chisel.core import entities as ent
from chisel.core import research as research_notes
from chisel.core.paper import guidelines as gl
from chisel.core.project import Project
from chisel.gui.api import Api

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@pytest.fixture
def project(tmp_path):
    return Project.create(tmp_path / "paper", "Paper", "research")


def make_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def make_docx(body_xml: str, doctype: str = "") -> bytes:
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>{doctype}'
           f'<w:document xmlns:w="{W}"><w:body>{body_xml}</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def para(t):
    return f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>"


def test_docx_paragraphs_and_tables_in_order(project):
    table = ("<w:tbl><w:tr><w:tc>" + para("Item") + "</w:tc><w:tc>" + para("Limit") + "</w:tc></w:tr>"
             "<w:tr><w:tc>" + para("Abstract") + "</w:tc><w:tc>" + para("250 words") + "</w:tc></w:tr></w:tbl>")
    name = gl.add_bytes(project, "Author Guide.docx", make_docx(para("First") + table + para("Last")))
    assert name == "author-guide.docx"
    out = gl.read_text(project, name)
    assert out["text"].splitlines() == ["First", "Item | Limit", "Abstract | 250 words", "Last"]
    assert out["truncated"] is False
    assert (project.root / ".chisel" / "guidelines").is_dir()


def test_hostile_docx_refused(project):
    evil = '<!DOCTYPE d [<!ENTITY x "boom">]>'
    name = gl.add_bytes(project, "x.docx", make_docx(para("&x;"), evil))
    row = gl.list_files(project)[0]
    assert row["name"] == name and row["extracted"] is False and "unsafe" in row["message"]
    with pytest.raises(gl.GuidelineError):
        gl.read_text(project, name)


def test_zip_bomb_stand_in(project, monkeypatch):
    data = make_docx(para("hello"))
    monkeypatch.setattr(gl, "MAX_UNCOMPRESSED", 10)          # declared sizes over the cap
    name = gl.add_bytes(project, "big.docx", data)
    with pytest.raises(gl.GuidelineError, match="too large"):
        gl.read_text(project, name)
    monkeypatch.setattr(gl, "MAX_UNCOMPRESSED", 50 * 1024 * 1024)
    monkeypatch.setattr(gl, "MAX_ZIP_ENTRIES", 1)
    with pytest.raises(gl.GuidelineError, match="too large"):
        gl.read_text(project, name)


def test_fake_pdf_and_odd_zip_refused(project):
    with pytest.raises(gl.GuidelineError):
        gl.add_bytes(project, "fake.pdf", b"just some words")
    with pytest.raises(gl.GuidelineError):
        gl.add_bytes(project, "fake.docx", b"just some words")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "x")
    with pytest.raises(gl.GuidelineError):
        gl.add_bytes(project, "a.docx", buf.getvalue())
    with pytest.raises(gl.GuidelineError):
        gl.add_bytes(project, "bin.txt", b"\x00\x01\x02binary")
    with pytest.raises(gl.GuidelineError):
        gl.add_bytes(project, "latin.txt", "caf\xe9".encode("latin-1"))
    assert gl.list_files(project) == []


def test_text_files_and_collisions(project):
    a = gl.add_bytes(project, "Rules.md", b"# Rules\nbe brief")
    b = gl.add_bytes(project, "Rules.md", b"second")
    c = gl.add_bytes(project, "rules.txt", b"third")
    assert (a, b, c) == ("rules.md", "rules-2.md", "rules.txt")
    assert (project.root / "guidelines" / "rules.md").read_bytes() == b"# Rules\nbe brief"
    types = {r["name"]: r["type"] for r in gl.list_files(project)}
    assert types == {"rules.md": "md", "rules-2.md": "md", "rules.txt": "txt"}


def test_pasted_note(project):
    name = gl.add_text(project, "Funder call", "Page limit: 5.")
    assert name == "funder-call.md"
    row = gl.list_files(project)[0]
    assert row["type"] == "note" and row["extracted"] is True
    text = gl.read_text(project, name)["text"]
    assert "Page limit: 5." in text and "pasted" not in text
    with pytest.raises(gl.GuidelineError):
        gl.add_text(project, "Empty", "   ")


@pytest.mark.parametrize("bad", ["../x.md", "a/b.md", "a\\b.md", "..", ".", "", ".hidden.md", "x.exe",
                                 "C:evil.md", "nul\x00.md"])
def test_names_must_be_plain(project, bad):
    gl.add_bytes(project, "ok.md", b"fine")
    with pytest.raises(gl.GuidelineError):
        gl.read_text(project, bad)
    with pytest.raises(gl.GuidelineError):
        gl.remove(project, bad)
    assert (project.root / "guidelines" / "ok.md").exists()


def test_stored_name_is_sanitised(project):
    name = gl.add_bytes(project, "..\\..\\evil name!.md", b"x")
    assert name == "evil-name.md"
    assert (project.root / "guidelines" / name).is_file()


def test_symlink_out_of_folder_refused(project, tmp_path):
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")
    folder = project.root / "guidelines"
    folder.mkdir()
    try:
        (folder / "link.md").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    with pytest.raises((gl.GuidelineError, FileNotFoundError)):
        gl.read_text(project, "link.md")
    assert gl.list_files(project) == []


def test_oversize_refused(project, monkeypatch):
    monkeypatch.setattr(gl, "MAX_BYTES", 100)
    with pytest.raises(gl.GuidelineError, match="25 MB"):
        gl.add_bytes(project, "big.txt", b"a" * 101)
    big = project.root.parent / "big.txt"
    big.write_bytes(b"a" * 101)
    with pytest.raises(gl.GuidelineError, match="25 MB"):
        gl.add_file(project, big)
    assert not (project.root / "guidelines").exists() or gl.list_files(project) == []


def test_add_file_and_read_limit(project, tmp_path):
    src = tmp_path / "call.txt"
    src.write_text("x" * 500, encoding="utf-8")
    name = gl.add_file(project, src)
    out = gl.read_text(project, name, limit=100)
    assert out["truncated"] is True and len(out["text"]) == 100 and out["chars"] == 500
    with pytest.raises(FileNotFoundError):
        gl.add_file(project, tmp_path / "missing.txt")


def test_total_cap_flag(project, monkeypatch):
    monkeypatch.setattr(gl, "MAX_TOTAL_CHARS", 50)
    name = gl.add_bytes(project, "long.docx", make_docx(para("y" * 200)))
    out = gl.read_text(project, name, limit=1000)
    assert out["truncated"] is True and len(out["text"]) == 50


def test_remove_and_cache_rebuild(project):
    name = gl.add_bytes(project, "g.docx", make_docx(para("cached words")))
    gl.read_text(project, name)
    cache = list((project.root / ".chisel" / "guidelines").glob("*.json"))
    assert len(cache) == 1
    cache[0].unlink()                                   # a cache is rebuildable
    assert "cached words" in gl.read_text(project, name)["text"]
    assert len(list((project.root / ".chisel" / "guidelines").glob("*.json"))) == 1
    gl.remove(project, name)
    assert not (project.root / "guidelines" / name).exists()
    assert not list((project.root / ".chisel" / "guidelines").glob("*.json"))
    with pytest.raises(FileNotFoundError):
        gl.remove(project, name)


def test_pdf_text_and_scanned(project):
    pytest.importorskip("pypdf", reason="pypdf is an optional package")
    name = gl.add_bytes(project, "Call.pdf", make_pdf("Maximum length is ten pages"))
    assert name == "call.pdf"
    assert "Maximum length is ten pages" in gl.read_text(project, name)["text"]
    blank = gl.add_bytes(project, "scan.pdf", make_pdf(""))
    with pytest.raises(gl.GuidelineError, match="scanned"):
        gl.read_text(project, blank)
    rows = {r["name"]: r for r in gl.list_files(project)}
    assert rows["call.pdf"]["extracted"] is True and "scanned" in rows["scan.pdf"]["message"]


def test_pdf_without_pypdf(project, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "pypdf":
            raise ImportError("no pypdf")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    name = gl.add_bytes(project, "call.pdf", make_pdf("hello"))
    row = gl.list_files(project)[0]
    assert row["name"] == name and row["extracted"] is False and "pypdf" in row["message"]


# -- the bridge -------------------------------------------------------------------------------------------

def research_api(tmp_path):
    api = Api()
    api._load(Project.create(tmp_path / "paper", "Paper", "research"))
    return api


def test_bridge_roundtrip(tmp_path):
    api = research_api(tmp_path)
    assert api.guidelines_list() == {"ok": True, "files": []}
    assert api.guidelines_add() == {"ok": True, "added": [], "skipped": []}      # no window: nothing picked
    good = tmp_path / "rules.txt"
    good.write_text("be brief", encoding="utf-8")
    bad = tmp_path / "fake.pdf"
    bad.write_bytes(b"nope")
    res = api.guidelines_add([str(good), str(bad), str(tmp_path / "gone.txt")])
    assert res["added"] == ["rules.txt"]
    assert [s["name"] for s in res["skipped"]] == ["fake.pdf", "gone.txt"]
    assert all(s["reason"] for s in res["skipped"])
    assert api.guidelines_add_text("Notes", "text here") == {"ok": True, "name": "notes.md"}
    read = api.guidelines_read("rules.txt")
    assert read == {"ok": True, "name": "rules.txt", "text": "be brief", "truncated": False, "chars": 8,
                    "message": ""}
    assert api.guidelines_read("../project.toml")["ok"] is False
    assert api.guidelines_remove("rules.txt") == {"ok": True}
    assert [f["name"] for f in api.guidelines_list()["files"]] == ["notes.md"]


def test_bridge_research_only(tmp_path):
    api = Api()
    api._load(Project.create(tmp_path / "novel", "Novel"))
    for res in (api.guidelines_list(), api.guidelines_add_text("a", "b"), api.guidelines_read("a.md"),
                api.guidelines_remove("a.md"), api.guidelines_add([])):
        assert res["ok"] is False and "research" in res["error"].lower()


# -- privacy ----------------------------------------------------------------------------------------------

SECRET = "ZZ-GUIDELINE-SENTINEL-4471"


def test_guideline_text_never_in_ai_context(tmp_path):
    project = Project.create(tmp_path / "paper", "Paper", "research")
    gl.add_text(project, "Journal rules", f"{SECRET} keep it under ten pages; samples filtered")
    gl.add_bytes(project, "more.txt", f"{SECRET} samples filtered more".encode())
    research_notes.new_note(project, "Method note", "Samples were filtered.")
    mara, _ = project.create_entity("Mara Vale", "character")
    ent.add_alias(mara, "Mara")
    entities = project.load_entities()
    canon = {"Mara Vale": "Careful reader."}
    scene = "# Intro\n\nMara filtered the samples. Method matters.\n"

    texts = []
    sections = writing.build_context_sections(scene, 10, entities, canon, "Plain style.")
    texts.append(render(fit(sections, Budget.unbounded())[0]))
    sections = writing.build_project_context_sections(["Intro"], entities, canon, "Plain style.")
    texts.append(render(fit(sections, Budget.unbounded())[0]))
    sections, _hits = writing.research_sections(project, entities, canon, "samples filtered")
    texts.append(render(fit(sections, Budget.unbounded())[0]))
    texts.append(continuity.build_check_prompt(scene, canon))
    texts.append(links.build_prompt(scene, entities))
    _ents, planned_canon, report = continuity.plan_check(scene, entities, canon, Budget.unbounded())
    texts.append(repr(planned_canon) + repr(report.to_dict()))
    assert all(texts) and not any(SECRET in t for t in texts)


# -- review findings (C2) ----------------------------------------------------------------------------------

def test_bridge_refusals_have_no_class_prefix(tmp_path):
    from chisel.core.zotero.base import ZoteroError
    from chisel.gui._bridge import bridge

    api = research_api(tmp_path)
    for res in (api.guidelines_add_text("t", "   "), api.guidelines_read("nothing.pdf"),
                api.guidelines_read("../x.md")):
        assert res["ok"] is False and "Error:" not in res["error"], res

    class Fake:
        @bridge
        def zot(self):
            raise ZoteroError("Zotero is not running.")

    assert Fake().zot() == {"ok": False, "error": "Zotero is not running."}


def test_utf16_docx_with_entity_refused(project):
    xml = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ENTITY x "boom">]>'
           f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>')
    for raw in (xml.encode("utf-16"), xml.encode("utf-16-le")):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", raw)
        with pytest.raises(gl.GuidelineError):
            gl._docx_text(buf.getvalue())
    mixed = make_docx(para("x"), doctype="<!DocType d [<!EnTiTy x 'boom'>]>")
    with pytest.raises(gl.GuidelineError):
        gl._docx_text(mixed)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", f'<?xml version="1.0" encoding="ISO-8859-1"?><w:document xmlns:w="{W}"/>')
    with pytest.raises(gl.GuidelineError):
        gl._docx_text(buf.getvalue())


def test_extraction_outside_lock_and_failure_cached(tmp_path, monkeypatch):
    import threading

    api = research_api(tmp_path)
    api.guidelines_add_text("keep", "x")
    folder = api.project.root / "guidelines"
    (folder / "scan.pdf").write_bytes(make_pdf("Hello"))
    calls = []
    free = []

    def fake_pdf(data):
        calls.append(1)
        got = []

        def probe():
            got.append(api._lock.acquire(timeout=2))
            if got[0]:
                api._lock.release()

        t = threading.Thread(target=probe)
        t.start()
        t.join()
        free.append(bool(got and got[0]))
        raise gl.GuidelineError("This looks like a scanned document; paste its text instead.")

    monkeypatch.setattr(gl, "_pdf_text", fake_pdf)
    for _ in range(3):
        res = api.guidelines_list()
        assert res["ok"], res
        rows = {r["name"]: r for r in res["files"]}
        assert "scanned" in rows["scan.pdf"]["message"]
    assert api.guidelines_read("scan.pdf")["error"].startswith("This looks like a scanned")
    assert len(calls) == 1 and free == [True]


def test_pdf_page_cap_is_reported(project, monkeypatch):
    import pypdf

    class Page:
        def extract_text(self):
            return "word " * 5

    class Reader:
        is_encrypted = False
        pages = [Page() for _ in range(5)]

        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    monkeypatch.setattr(gl, "MAX_PDF_PAGES", 3)
    text, note = gl._pdf_text(b"%PDF-")
    assert note == "Only the first 3 pages were read." and text.count("word") == 15
    name = gl.add_bytes(project, "q.pdf", make_pdf("Hello"))
    row = [r for r in gl.list_files(project) if r["name"] == name][0]
    assert "first 3 pages" in row["message"]
    assert gl.read_text(project, name)["truncated"] is True
    monkeypatch.setattr(gl, "MAX_PAGE_CHARS", 4)
    assert "cut" in gl._pdf_text(b"%PDF-")[1]


def test_oversize_hand_placed_file_not_read(project, monkeypatch):
    monkeypatch.setattr(gl, "MAX_BYTES", 10)
    folder = project.root / "guidelines"
    folder.mkdir(exist_ok=True)
    (folder / "huge.txt").write_text("a" * 50, encoding="utf-8")
    row = gl.list_files(project)[0]
    assert row["extracted"] is False and "too large to read" in row["message"]
    with pytest.raises(gl.GuidelineError, match="too large to read"):
        gl.read_text(project, "huge.txt")


def test_cache_key_includes_extractor_version(project, monkeypatch):
    name = gl.add_bytes(project, "g.docx", make_docx(para("v words")))
    gl.read_text(project, name)
    monkeypatch.setattr(gl, "EXTRACTOR_VERSION", gl.EXTRACTOR_VERSION + 1)
    gl.read_text(project, name)
    assert len(list((project.root / ".chisel" / "guidelines").glob("*.json"))) == 2


def test_a_missing_pypdf_refusal_is_not_cached(tmp_path, monkeypatch):
    """Installing pypdf later must work without the file changing: the 'needs pypdf' refusal is never cached."""
    import sys
    from pathlib import Path

    from chisel.core.paper import guidelines
    from chisel.core.project import Project

    project = Project.create(tmp_path / "p", "P", "research")
    src = guidelines.Source(Path("x.pdf"), b"%PDF-1.4\n%fake\n")
    monkeypatch.setitem(sys.modules, "pypdf", None)          # "import pypdf" raises ImportError
    with pytest.raises(guidelines.GuidelineError, match="pypdf"):
        guidelines.extract(project, src)
    cache = project.root / ".chisel" / "guidelines"
    assert not cache.exists() or list(cache.glob("*.json")) == []


def test_image_errors_reach_the_author_without_a_class_prefix():
    from chisel.ai.images import ImageError
    from chisel.gui._bridge import USER_ERRORS

    assert ImageError in USER_ERRORS
