"""Research wave C1: journal profiles, kind/journal settings, starter outline, requirements, citation style."""

import json
import tomllib
from pathlib import Path

import pytest

from chisel.core import entities as ent
from chisel.core import scenemeta
from chisel.core.paper import citefmt, journals, requirements
from chisel.core.paper.types import Citation, CiteRef
from chisel.core.project import Project
from chisel.core.spans import compute_spans
from chisel.gui.api import Api
from chisel.gui.research_project_api import ResearchProjectMixin


class RApi(ResearchProjectMixin, Api):
    pass


def make(tmp_path, journal="ems", kind="manuscript"):
    return Project.create(tmp_path / "paper", "Paper", "research", kind, journal)


def scene_for(project, title):
    for p in project.list_scenes():
        if p.read_text(encoding="utf-8").lstrip("-").find(f"# {title}\n") >= 0:
            return p
    raise AssertionError(title)


def put(project, title, body):
    p = scene_for(project, title)
    text = p.read_text(encoding="utf-8")
    p.write_text(text.rstrip("\n") + "\n\n" + body + "\n", encoding="utf-8", newline="\n")


def by_id(rows):
    return {r["id"]: r for r in rows}


# -- profiles -------------------------------------------------------------------------------------


def test_every_shipped_profile_parses_and_its_checks_are_implemented():
    profiles = journals.list_profiles()
    assert [p.id for p in profiles][:3] == ["ems", "manuscript", "proposal"]
    on_disk = sorted(p.stem for p in journals.journals_dir().glob("*.toml"))
    assert sorted(p.id for p in profiles) == on_disk
    for p in profiles:
        assert p.kind in journals.KINDS and p.citation_style in journals.CITATION_STYLES and p.outline
        for r in p.requirements:
            if r.kind == "check":
                assert r.check in journals.CHECK_KINDS
                # and the engine has a branch for it: evaluating never reports an unknown check
                assert r.check in requirements.IMPLEMENTED
    assert journals.load_profile("ems").citation_style == "harvard"


@pytest.mark.parametrize("bad", ["", "../ems", "ems/x", "EMS", "a.b", "..", "x" * 80])
def test_profile_ids_are_plain_names(bad):
    with pytest.raises(ValueError):
        journals.load_profile(bad)


def test_missing_and_malformed_profiles_are_clean_errors(tmp_path, monkeypatch):
    (tmp_path / "broken.toml").write_text("id = [", encoding="utf-8")
    (tmp_path / "wrongid.toml").write_text('id = "other"\nkind = "manuscript"\n', encoding="utf-8")
    (tmp_path / "badcheck.toml").write_text(
        'id = "badcheck"\nkind = "manuscript"\n[[requirement]]\nid = "x"\ntitle = "t"\nkind = "check"\n'
        'check = "nope"\n', encoding="utf-8")
    monkeypatch.setattr(journals, "journals_dir", lambda: tmp_path)
    for name in ("broken", "wrongid", "badcheck", "absent"):
        with pytest.raises(ValueError):
            journals.load_profile(name)
    assert journals.list_profiles() == []


# -- settings ---------------------------------------------------------------------------------------


def test_defaults_and_unknown_values_read_as_default(tmp_path):
    p = Project.create(tmp_path / "s", "S", "research")
    assert (p.research_kind, p.journal) == ("manuscript", "")
    p.update_research_settings(kind="proposal", journal="nonexistent")
    assert p.research_kind == "proposal" and p.journal == ""      # unknown profile reads as none
    (p.root / "project.toml").write_text('title = "x"\n[research]\nkind = "pamphlet"\njournal = 3\n',
                                         encoding="utf-8")
    q = Project.open(p.root)
    assert (q.research_kind, q.journal) == ("manuscript", "")
    story = Project.create(tmp_path / "t", "T")
    assert story.citation_style == "apa" and "research" not in story.meta


def test_update_research_settings_edits_only_named_lines(tmp_path):
    p = make(tmp_path, "")
    path = p.root / "project.toml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("[research]\n", "[research]\n# keep me\nnumbering = 'plain'   # and me\n")
    text += '\n[export]\nformat = "pdf"\n'
    path.write_text(text, encoding="utf-8", newline="\n")
    p = Project.open(p.root)
    p.update_research_settings(journal="ems")
    new = path.read_text(encoding="utf-8")
    assert new == text.replace('journal = ""', 'journal = "ems"')
    p.update_research_settings(zotero_collections=["A", "B"])
    after = path.read_text(encoding="utf-8")
    assert 'zotero_collections = ["A", "B"]' in after and "# keep me" in after and "# and me" in after
    assert tomllib.loads(after)["research"]["journal"] == "ems"


def test_update_creates_table_and_refuses_bad_values(tmp_path):
    p = Project.create(tmp_path / "s", "S")          # a story project has no [research]
    p.update_research_settings(kind="proposal", journal="")
    assert tomllib.loads((p.root / "project.toml").read_text(encoding="utf-8"))["research"] == {
        "kind": "proposal", "journal": ""}
    for kwargs in ({"kind": "thesis"}, {"journal": "../x"}):
        with pytest.raises(ValueError):
            p.update_research_settings(**kwargs)
    path = p.root / "project.toml"
    path.write_text('[research]\nzotero_collections = [\n  "a",\n]\n', encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        Project.open(p.root).update_research_settings(zotero_collections=["z"])
    assert path.read_bytes() == before


# -- creation ---------------------------------------------------------------------------------------


def test_ems_starter_outline(tmp_path):
    p = make(tmp_path)
    assert p.research_kind == "manuscript" and p.journal == "ems" and p.citation_style == "harvard"
    parts = p.list_parts()
    assert [p.part_title(x) for x in parts] == ["Front matter", "Article", "Declarations and availability"]
    assert p.part_is_front_matter(parts[0])
    details = [scenemeta.details(x.read_text(encoding="utf-8")) for x in p.list_scenes()]
    assert details[2]["purpose"].startswith("At most 150 words")
    assert len(p.list_scenes()) == 4 + 5 + 6
    assert [x.name for x in p.list_unplaced()] == ["01-opening.md"]
    assert p.counted_scenes() and all(not p.is_front_matter(x) for x in p.counted_scenes())
    assert (p.root / "manuscript" / "_unplaced" / "01-opening.md").is_file()
    assert not (p.root / "manuscript" / "01-opening.md").exists()


def test_generic_and_proposal_outlines_and_mismatch(tmp_path):
    g = make(tmp_path, "")
    assert [g.part_title(x) for x in g.list_parts()] == ["Front matter", "Article", "Back matter"]
    pr = Project.create(tmp_path / "pr", "Pr", "research", "proposal", "")
    assert pr.research_kind == "proposal"
    assert "Objectives" in [x.read_text(encoding="utf-8") .split("\n# ")[1].splitlines()[0]
                            for x in pr.list_scenes()]
    with pytest.raises(ValueError):
        Project.create(tmp_path / "bad", "Bad", "research", "proposal", "ems")
    assert not (tmp_path / "bad").exists()
    with pytest.raises(ValueError):
        Project.create(tmp_path / "bad2", "Bad", "research", "manuscript", "nope")


def test_story_and_script_creation_unchanged(tmp_path):
    s = Project.create(tmp_path / "s", "S", "story", "proposal", "ems")     # kind and journal ignored
    files = sorted(p.relative_to(s.root).as_posix() for p in s.root.rglob("*") if p.is_file())
    assert files == [".gitignore", "manuscript/01-opening.md", "project.toml"]
    assert "[research]" not in (s.root / "project.toml").read_text(encoding="utf-8")
    sc = Project.create(tmp_path / "sc", "Sc", "script", "proposal", "ems")
    assert "[research]" not in (sc.root / "project.toml").read_text(encoding="utf-8")
    assert (sc.root / "manuscript" / "01-opening.md").is_file()


# -- requirements -----------------------------------------------------------------------------------


def test_requirements_empty_without_profile(tmp_path):
    assert requirements.evaluate(make(tmp_path, "")) == []
    assert requirements.evaluate(Project.create(tmp_path / "s", "S")) == []


def test_ems_checks_on_a_fresh_project(tmp_path):
    rows = by_id(requirements.evaluate(make(tmp_path)))
    assert rows["abstract-words"]["status"] == "ok"
    assert rows["keywords-count"]["status"] == "warn"
    assert rows["title-page"]["status"] == "ok"
    assert rows["graphical-abstract"]["status"] == "advice"
    assert rows["figures-captioned"]["status"] == "na"
    assert rows["citations-resolve"]["status"] == "na"
    assert rows["genai-declaration"]["status"] == "na"
    assert rows["acknowledgements-before-references"]["status"] == "ok"      # Acknowledgements is last
    assert set(r["status"] for r in rows.values()) <= {"ok", "warn", "info", "na", "advice"}


def test_abstract_words_highlights_and_keywords(tmp_path):
    p = make(tmp_path)
    put(p, "Abstract", " ".join(["word"] * 183) + " <!--ai-->" + " ".join(["draft"] * 50) + "<!--/ai-->")
    put(p, "Highlights", "- Short one\n- " + "x" * 90 + "\n- Another short\n")
    put(p, "Keywords", "water; models, software\nmore, extra, a, b, c")
    rows = by_id(requirements.evaluate(p))
    assert rows["abstract-words"]["status"] == "warn"
    assert rows["abstract-words"]["message"] == "Abstract is 183 words; the limit is 150."
    assert rows["highlights"]["status"] == "warn"
    assert rows["highlights"]["message"].startswith("1 of the 3 highlights are longer than 85 characters:")
    assert rows["keywords-count"]["status"] == "warn"       # 8 keywords
    assert "expected 1 to 7" in rows["keywords-count"]["message"]
    put(p, "Keywords", "")
    p2 = make(tmp_path / "again")
    put(p2, "Keywords", "water, models")
    put(p2, "Highlights", "1. A\n2. B\n3. C")
    put(p2, "Abstract", "A short abstract citing [[@x]].")
    rows = by_id(requirements.evaluate(p2))
    assert rows["keywords-count"]["status"] == "ok" and rows["highlights"]["status"] == "ok"
    assert rows["abstract-no-citations"]["status"] == "info"


def test_section_presence_and_last_section(tmp_path):
    p = make(tmp_path)
    scene_for(p, "Funding").unlink()
    ack = scene_for(p, "Acknowledgements")
    p.unplace_scene(ack)           # park it: no longer in the book
    rows = by_id(requirements.evaluate(p))
    assert rows["funding"]["status"] == "warn" and '"funding"' in rows["funding"]["message"]
    assert rows["acknowledgements-before-references"]["status"] == "na"
    p.next_scene_path("Appendix", p.list_parts()[-1]).write_text("# Appendix\n", encoding="utf-8")
    p.next_scene_path("Acknowledgements", p.list_parts()[1]).write_text("# Acknowledgements\n", encoding="utf-8")
    rows = by_id(requirements.evaluate(p))
    assert rows["acknowledgements-before-references"]["status"] == "info"
    assert "followed by" in rows["acknowledgements-before-references"]["message"]


def test_objects_and_citations(tmp_path):
    p = make(tmp_path)
    (p.root / "figures").mkdir()
    (p.root / "figures" / "fig-a.md").write_text("---\ncaption: A flow\n---\n", encoding="utf-8")
    (p.root / "figures" / "fig-b.md").write_text("---\ncaption: ''\n---\n", encoding="utf-8")
    (p.root / "tables").mkdir()
    (p.root / "tables" / "tbl-t.md").write_text("---\ncaption: T\n---\n| a |\n|---|\n| 1 |\n", encoding="utf-8")
    put(p, "Results", "See [[fig:a]] and [[tbl:t]].\n\n![[fig:a]]")
    n1 = ent.Entity(name="lee2020", type="source", aliases=["Lee 2020"],
                    extra={"key": "lee2020", "csl": {"issued": {"date-parts": [[2020]]}}})
    n2 = ent.Entity(name="kay2021", type="source", extra={"key": "kay2021", "csl": {"DOI": "10.1/x"}})
    for n in (n1, n2):
        ent.save_entity(n, p.root / "entities" / "sources" / f"{n.name}.md")
    put(p, "Introduction", "As shown [[@lee2020]] and [[@kay2021]] and [[@ghost]].")
    rows = by_id(requirements.evaluate(p))
    assert rows["figures-captioned"]["status"] == "warn"
    assert "b" in rows["figures-captioned"]["message"]
    assert rows["tables-captioned"]["status"] == "ok"
    assert rows["figures-cited"]["status"] == "warn" and "b" in rows["figures-cited"]["message"]
    assert rows["tables-cited"]["status"] == "ok"
    assert rows["citations-resolve"]["status"] == "warn" and "ghost" in rows["citations-resolve"]["message"]
    assert rows["sources-doi"]["status"] == "info" and "lee2020" in rows["sources-doi"]["message"]
    assert "kay2021" not in rows["sources-doi"]["message"]


def test_ai_declaration_uses_accepted_words(tmp_path, monkeypatch):
    p = make(tmp_path)
    monkeypatch.setattr(requirements, "_accepted_ai_words", lambda project: 120)
    row = by_id(requirements.evaluate(p))["genai-declaration"]
    assert row["status"] == "warn" and "120 words" in row["message"]
    put(p, "Declaration of generative AI use", "Used a model for wording.")
    assert by_id(requirements.evaluate(p))["genai-declaration"]["status"] == "ok"


def test_accepted_ai_words_read_from_the_tracker(tmp_path):
    from chisel.core.stats import Tracker
    p = make(tmp_path)
    assert requirements._accepted_ai_words(p) == 0
    t = Tracker(p.root)
    t.seen("k", 10)
    t.accepted("k", 40)
    t.flush()
    assert requirements._accepted_ai_words(p) == 40


# -- citation style ---------------------------------------------------------------------------------


def test_citation_styles():
    src = {"a": citefmt.CiteSource(["Smith", "Jones"], "2020", "T"),
           "b": citefmt.CiteSource(["Smith", "Jones", "Lee"], "2021", "U")}
    one = Citation([CiteRef("a")], 0, 0, "", "bracketed")
    two = Citation([CiteRef("a"), CiteRef("b")], 0, 0, "", "bracketed")
    nar = Citation([CiteRef("a")], 0, 0, "", "narrative")
    assert citefmt.format_citation(one, src) == "(Smith & Jones, 2020)"
    assert citefmt.format_citation(one, src, style="apa") == "(Smith & Jones, 2020)"
    assert citefmt.format_citation(one, src, style="harvard") == "(Smith and Jones, 2020)"
    assert citefmt.format_citation(two, src, style="harvard") == "(Smith and Jones, 2020; Smith et al., 2021)"
    assert citefmt.format_citation(nar, src, style="harvard") == "Smith and Jones (2020)"
    assert citefmt.format_citation(nar, src) == "Smith and Jones (2020)"


def test_spans_use_the_project_style(tmp_path):
    p = make(tmp_path)
    ent.save_entity(ent.Entity(name="sj", type="source", extra={
        "key": "sj", "csl": {"author": [{"family": "Smith"}, {"family": "Jones"}],
                             "issued": {"date-parts": [[2020]]}}}),
                    p.root / "entities" / "sources" / "sj.md")
    entities = p.load_entities()
    text = "x [[@sj]] y"
    apa = [s for s in compute_spans(text, entities, mentions=False, citations=True) if s["kind"] == "citation"]
    har = [s for s in compute_spans(text, entities, mentions=False, citations=True, citation_style=p.citation_style)
           if s["kind"] == "citation"]
    assert apa[0]["display"] == "(Smith & Jones, 2020)" and har[0]["display"] == "(Smith and Jones, 2020)"
    api = RApi()
    api._load(p)
    got = api.link_spans("manuscript/02-article/01-introduction.md", text)
    assert [s["display"] for s in got["spans"] if s["kind"] == "citation"] == ["(Smith and Jones, 2020)"]


# -- bridge -----------------------------------------------------------------------------------------


def test_bridge_profiles_settings_requirements(tmp_path):
    api = RApi()
    assert api.new_project("Paper", str(tmp_path / "paper"), "research", "manuscript", "ems")["ok"] is True
    r = api.research_profiles()
    assert r["ok"] and [x["id"] for x in r["profiles"]][:3] == ["ems", "manuscript", "proposal"]
    assert set(r["profiles"][0]) == {"id", "name", "publisher", "kind", "source", "readOn"}
    s = api.research_get_settings()
    assert s["kind"] == "manuscript" and s["journal"] == "ems" and s["citationStyle"] == "harvard"
    assert s["journalName"] == "Environmental Modelling & Software" and s["readOn"] == "2026-10-19"
    q = api.research_requirements()
    assert q["ok"] and q["journal"] == "ems" and q["groups"][0]["title"] == "Front matter"
    assert set(q["summary"]) == {"ok", "warn", "info", "advice"} and q["summary"]["advice"] > 0
    item = q["groups"][0]["items"][0]
    assert set(item) == {"id", "title", "status", "message"}
    # settings: refuse unknown and mismatched, never touch other files
    root = Path(tmp_path / "paper")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != "project.toml"}
    assert api.research_set_settings("manuscript", "nope")["ok"] is False
    assert api.research_set_settings("proposal", "ems")["ok"] is False
    assert api.research_set_settings("manuscript", "../ems")["ok"] is False
    ok = api.research_set_settings("manuscript", "manuscript")
    assert ok["ok"] and ok["journal"] == "manuscript" and ok["citationStyle"] == "apa"
    none = api.research_set_settings("proposal", "")
    assert none["ok"] and none["journal"] == "" and none["kind"] == "proposal"
    assert api.research_requirements()["groups"] == []
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != "project.toml"}
    assert json.dumps(tomllib.loads((root / "project.toml").read_text(encoding="utf-8"))["research"])


def test_bridge_refuses_story_projects_and_bad_new_project(tmp_path):
    api = RApi()
    assert api.new_project("Tale", str(tmp_path / "tale"))["ok"] is True
    for call in (api.research_profiles, api.research_get_settings, api.research_requirements,
                 lambda: api.research_set_settings("manuscript", "")):
        r = call()
        assert r["ok"] is False and "not a research project" in r["error"]
    for kind, journal in (("thesis", ""), ("manuscript", "nope"), ("proposal", "ems")):
        r = api.new_project("P", str(tmp_path / f"p-{kind}-{journal}"), "research", kind, journal)
        assert r["ok"] is False
        assert not (tmp_path / f"p-{kind}-{journal}").exists()
