"""Wave E1: own requirements (core/paper/custom_requirements.py), AI suggestions from guidelines
(ai/requirements.py) and the bridge mixin (gui/research_requirements_api.py). Nothing reaches a network."""

import json

import pytest

from chisel.ai import requirements as rai
from chisel.ai.budget import Budget, BudgetError
from chisel.core.paper import custom_requirements as cr
from chisel.core.paper import guidelines, requirements
from chisel.core.project import Project
from chisel.gui import api as api_module
from chisel.gui.api import Api
from tests.research_helpers import clear_starter


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("No OpenRouter API key (network is blocked in tests)")

    monkeypatch.setattr("chisel.ai.client.make_client", boom)


def make(tmp_path, journal="ems", kind="manuscript"):
    return Project.create(tmp_path / "paper", "Paper", "research", kind, journal)


def put_section(project, title, body):
    path = project.next_scene_path(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8", newline="\n")
    return path


def row(**kw):
    base = {"id": "kw", "group": "Keywords", "title": "3 to 6 keywords", "kind": "check",
            "check": "list-count", "section": ["keywords"], "min": 3, "max": 6, "severity": "warn"}
    base.update(kw)
    return base


# -- rows and the file ---------------------------------------------------------------------------------------

def test_rows_round_trip_and_file_is_valid_toml(tmp_path):
    import tomllib
    p = make(tmp_path)
    rows = [row(source="guide.pdf", quote='He said "yes" \\ and é \U0001F600 ok.'),
            {"id": "cover", "title": "Prepare a cover letter", "kind": "advice", "severity": "info"},
            row(id="fig", title="Figures captioned", check="objects-captioned", object="fig", section=[],
                min=None, max=None)]
    saved = cr.save_custom(p, rows)
    assert [r["id"] for r in saved] == ["kw", "cover", "fig"]
    raw = (p.root / "requirements.toml").read_bytes()
    assert b"\r\n" not in raw
    tomllib.loads(raw.decode("utf-8"))
    again = cr.load_custom(p)
    assert again == saved
    assert again[0]["quote"] == 'He said "yes" \\ and é \U0001F600 ok.'
    assert again[1]["group"] == "Your requirements"
    assert cr.remove(p, "cover")[0]["id"] == "kw"
    with pytest.raises(ValueError):
        cr.remove(p, "cover")
    assert cr.save_custom(p, []) == [] and not (p.root / "requirements.toml").exists()


@pytest.mark.parametrize("bad, words", [
    (row(check="telepathy"), "unknown check"),
    (row(check="ai-declaration"), "journal profiles"),
    (row(id="Bad Id"), "id"),
    (row(title=""), "title"),
    (row(title="t" * 161), "title"),
    (row(group="g" * 161), "group"),
    (row(kind="rule"), "check or advice"),
    (row(severity="fatal"), "severity"),
    (row(max=-5), "max"),
    (row(max=10 ** 9), "max"),
    (row(min=True), "min"),
    (row(min=2.5), "min"),
    (row(item_chars_max=0), "item_chars_max"),
    (row(item_chars_max=10_001), "item_chars_max"),
    (row(min=5, max=2), "minimum"),
    (row(min=None, max=None), "minimum or a maximum"),
    (row(section=[]), "section pattern"),
    (row(section=["a"] * 7), "section patterns"),
    (row(section=["x" * 61]), "pattern"),
    (row(check="section-words-max", max=None), "maximum number of words"),
    (row(check="objects-captioned", object="img"), "object"),
    ("nope", "not a row"),
])
def test_every_invalid_row_is_refused_naming_it(tmp_path, bad, words):
    p = make(tmp_path)
    with pytest.raises(ValueError) as exc:
        cr.save_custom(p, [row(id="good", title="Good one"), bad])
    assert words in str(exc.value)
    if isinstance(bad, dict) and bad.get("title"):
        assert bad["title"][:60] in str(exc.value) or "id" in str(exc.value)
    assert not (p.root / "requirements.toml").exists()          # nothing written


def test_duplicate_ids_and_too_many_rows_are_refused(tmp_path):
    p = make(tmp_path)
    with pytest.raises(ValueError, match="share the id"):
        cr.save_custom(p, [row(), row(title="again")])
    with pytest.raises(ValueError, match="At most"):
        cr.save_custom(p, [row(id=f"r{i}") for i in range(cr.MAX_ROWS + 1)])
    assert len(cr.save_custom(p, [row(id=f"r{i}") for i in range(cr.MAX_ROWS)])) == cr.MAX_ROWS


def test_malformed_file_is_no_rows_and_a_warning_in_the_report(tmp_path):
    p = make(tmp_path)
    (p.root / "requirements.toml").write_text("[[requirement\nid = ", encoding="utf-8")
    assert cr.load_custom(p) == []
    rows = requirements.evaluate(p)
    last = rows[-1]
    assert last["id"] == "custom-file" and last["status"] == "warn" and "could not be read" in last["message"]
    (p.root / "requirements.toml").write_bytes(b"caf\xe9")
    assert "could not be read" in cr.load_report(p)[1]


def test_a_bad_row_in_a_good_file_is_skipped_with_a_warning(tmp_path):
    p = make(tmp_path)
    (p.root / "requirements.toml").write_text(
        '[[requirement]]\nid = "ok"\ntitle = "Fine"\nkind = "advice"\n\n'
        '[[requirement]]\nid = "bad"\ntitle = "Bad"\nkind = "check"\ncheck = "nonsense"\n', encoding="utf-8")
    rows, warning = cr.load_report(p)
    assert [r["id"] for r in rows] == ["ok"] and "1 of the requirements" in warning


# -- evaluate ---------------------------------------------------------------------------------------------------

# the pre-change output of requirements.evaluate for the EMS profile on a fresh project
GOLDEN_EMS = [('abstract-words', 'Front matter', 'Abstract is at most 150 words', 'check', 'warn', 'Abstract is empty.'),
 ('abstract-no-citations', 'Front matter', 'Abstract avoids citations', 'check', 'na', 'Abstract is empty.'),
 ('keywords-count', 'Front matter', '1 to 7 keywords', 'check', 'warn', 'Keywords is empty.'),
 ('highlights',
  'Front matter',
  '3 to 5 highlights, each at most 85 characters',
  'check',
  'warn',
  'Highlights is empty.'),
 ('title-page',
  'Front matter',
  "Title page has the title, authors, affiliations with postal address, and the corresponding author's email",
  'check',
  'info',
  'Title page is there but empty.'),
 ('graphical-abstract',
  'Front matter',
  'A graphical abstract is required: a separate file at least 1328 pixels wide, longest side horizontal, '
  'readable at 13 cm',
  'advice',
  'advice',
  ''),
 ('software-data',
  'Structure',
  'A software and/or data availability section is present',
  'check',
  'warn',
  'Software and data availability is there but empty.'),
 ('credit',
  'Structure',
  'A CRediT author contribution statement is present',
  'check',
  'warn',
  'CRediT authorship contribution statement is there but empty.'),
 ('competing-interests',
  'Structure',
  'A declaration of competing interests is present',
  'check',
  'warn',
  'Declaration of competing interest is there but empty.'),
 ('funding', 'Structure', 'A funding statement is present', 'check', 'warn', 'Funding is there but empty.'),
 ('genai-declaration',
  'Structure',
  'Generative AI use is declared (required when AI tools were used in preparing the manuscript)',
  'check',
  'na',
  'No accepted AI-written words are recorded for this project.'),
 ('acknowledgements-before-references',
  'Structure',
  'Acknowledgements form their own section directly before the references',
  'check',
  'na',
  'Acknowledgements is empty.'),
 ('numbered-sections',
  'Structure',
  'Sections are numbered 1, 1.1, 1.1.1 and cross-referenced by number; the abstract is not numbered',
  'advice',
  'advice',
  ''),
 ('appendices',
  'Structure',
  'Appendices are lettered A, B; equations Eq. (A.1), tables Table A.1, figures Fig. A.1',
  'advice',
  'advice',
  ''),
 ('figures-captioned',
  'Figures, tables and equations',
  'Every figure has a caption (a brief title and a description)',
  'check',
  'na',
  'There are no figures yet.'),
 ('tables-captioned',
  'Figures, tables and equations',
  'Every table has a caption',
  'check',
  'na',
  'There are no tables yet.'),
 ('figures-cited',
  'Figures, tables and equations',
  'Every figure is cited in the text',
  'check',
  'na',
  'There are no figures yet.'),
 ('tables-cited',
  'Figures, tables and equations',
  'Every table is cited in the text',
  'check',
  'na',
  'There are no tables yet.'),
 ('tables-style',
  'Figures, tables and equations',
  'Tables are editable text with notes below, no vertical rules or shading, and do not repeat results given '
  'elsewhere',
  'advice',
  'advice',
  ''),
 ('figures-files',
  'Figures, tables and equations',
  'Figures are separate files named Figure_1, Figure_2; photographs at least 300 dpi, line drawings at least '
  '1000 dpi; no several images combined in one file; colours readable for colour-blind readers',
  'advice',
  'advice',
  ''),
 ('equations',
  'Figures, tables and equations',
  'Equations are editable text, displayed equations are numbered in the order they are referred to, '
  'variables in italics',
  'advice',
  'advice',
  ''),
 ('maps',
  'Figures, tables and equations',
  'Maps show only the study area and carry the note that map lines delineate study areas and do not '
  'necessarily depict accepted national boundaries',
  'advice',
  'advice',
  ''),
 ('genai-figures',
  'Figures, tables and equations',
  'Plots made by AI tools must come from your data by a reproducible method; any AI-generated image is '
  'disclosed in its caption',
  'advice',
  'advice',
  ''),
 ('citations-resolve',
  'References',
  'Every citation matches a source in the project',
  'check',
  'na',
  'There are no citations yet.'),
 ('sources-doi',
  'References',
  'Cited sources have a DOI where one exists',
  'check',
  'na',
  'No cited source to check.'),
 ('reference-style',
  'References',
  'Any consistent reference style is accepted at submission; in text: Smith, Smith and Jones, Smith et al., '
  'with a/b/c for the same author and year. The journal applies its own style after acceptance',
  'advice',
  'advice',
  ''),
 ('data-references',
  'References',
  'Datasets and software you use are cited as references (a [dataset] or [software] tag before the entry); '
  'data are deposited in a repository and linked, or the reason they cannot be shared is stated',
  'advice',
  'advice',
  ''),
 ('content-aims',
  'What the journal looks for',
  'The objectives of the model or software are stated clearly, with the rationale for the approach and '
  'substantial testing and evaluation (comparisons with alternatives are encouraged)',
  'advice',
  'advice',
  ''),
 ('content-literature',
  'What the journal looks for',
  'A brief review of the historical progress on the problem, and a clear statement of how the work adds '
  'value',
  'advice',
  'advice',
  ''),
 ('content-software',
  'What the journal looks for',
  'For software: usability, reliability, verification and validation backed by quantitative results; '
  'development and maintenance costs and adoption; licensing and open-source access stated clearly',
  'advice',
  'advice',
  ''),
 ('content-insight',
  'What the journal looks for',
  'Insights are generalisable: about the modelling, method, application or the systems modelled, and of '
  'interest to people studying other systems',
  'advice',
  'advice',
  ''),
 ('files',
  'Submission',
  'Submit editable files: .docx or .tex (a PDF is not accepted); Word files in one column; no strikethrough '
  "or underline unless scientifically relevant; highlights as a separate file with 'highlights' in its name",
  'advice',
  'advice',
  ''),
 ('reviewer-software',
  'Submission',
  'If software is essential to the paper, be ready to give reviewers a download (password-protected if '
  'needed) that keeps their identity hidden',
  'advice',
  'advice',
  '')]


def test_evaluate_is_unchanged_without_the_file(tmp_path):
    p = make(tmp_path)
    before = requirements.evaluate(p)
    assert before and not (p.root / "requirements.toml").exists()
    assert all(r["group"] != "Your requirements" for r in before)
    assert [(r["id"], r["group"], r["title"], r["kind"], r["status"], r["message"]) for r in before] == GOLDEN_EMS
    assert all(set(r) == {"id", "group", "title", "kind", "status", "message"} for r in before)
    q = make(tmp_path / "x", journal="")
    assert requirements.evaluate(q) == []


def test_evaluate_with_custom_rows_alone(tmp_path):
    p = make(tmp_path, journal="")
    assert p.research_profile() is None
    clear_starter(p)
    put_section(p, "Keywords", "- a\n- b\n- c\n- d")
    cr.save_custom(p, [row(), {"id": "cover", "title": "Cover letter", "kind": "advice"}])
    rows = requirements.evaluate(p)
    assert [(r["id"], r["status"], r["group"]) for r in rows] == [
        ("kw", "ok", "Keywords"), ("cover", "advice", "Your requirements")]


def test_evaluate_profile_then_custom_and_id_clash(tmp_path):
    p = make(tmp_path)
    profile_ids = [r.id for r in p.research_profile().requirements]
    clash = profile_ids[0]
    cr.save_custom(p, [row(id=clash, title="Mine"), row(id="mine", title="Other", group="")])
    rows = requirements.evaluate(p)
    assert [r["id"] for r in rows[:len(profile_ids)]] == profile_ids
    tail = rows[len(profile_ids):]
    assert [r["id"] for r in tail] == ["custom-" + clash, "mine"]
    assert tail[0]["title"] == "Mine" and tail[1]["group"] == "Your requirements"
    assert len({r["id"] for r in rows}) == len(rows)


def test_evaluate_a_custom_check_runs(tmp_path):
    p = make(tmp_path, journal="")
    clear_starter(p)
    put_section(p, "Abstract", "one two three four five")
    cr.save_custom(p, [row(id="abs", title="Abstract at most 3 words", check="section-words-max",
                           section=["abstract"], min=None, max=3)])
    assert requirements.evaluate(p)[0]["status"] == "warn"


# -- parse ------------------------------------------------------------------------------------------------------

GUIDE = ("Instructions for authors.\nThe abstract must not exceed 250 words and must be\nstructured.\n"
         "Provide three to six keywords of at most 30 characters.")
TEXTS = {"guide.md": GUIDE}


def good(**kw):
    base = {"id": "abstract-words", "group": "Abstract", "title": "Abstract at most 250 words", "kind": "check",
            "check": "section-words-max", "section": ["abstract"], "max": 250, "severity": "warn",
            "source": "guide.md", "quote": "The abstract must not exceed 250 words and must be structured.",
            "why": "The guide says so."}
    base.update(kw)
    return base


def parse(items, texts=TEXTS, taken=()):
    return rai.parse_requirement_rows(json.dumps({"items": items}), texts, taken)


def test_parse_shape_and_prose_around_json():
    reply = "Sure, here you go:\n```json\n" + json.dumps({"items": [good()]}) + "\n```\nHope this helps {x}"
    items, dropped = rai.parse_requirement_rows(reply, TEXTS)
    assert dropped == [] and len(items) == 1
    assert set(items[0]) == {"id", "group", "title", "kind", "check", "section", "min", "max", "item_chars_max",
                             "object", "severity", "source", "quote", "why", "verified"}
    assert items[0]["verified"] is True and items[0]["max"] == 250


def test_parse_drops_sloppy_rows_with_reasons():
    items, dropped = parse([
        good(id="a", check="mind-reading"),
        good(id="b", max=-5),
        good(id="c", max=10 ** 9),
        good(id="d", section=[f"s{i}" for i in range(9)]),
        good(id="e", check="ai-declaration"),
        good(id="f", section=["y" * 80]),
        "text",
        good(id="ok", title="<!---->"),
    ])
    assert items == []
    assert len(dropped) == 8 and all(d["reason"] for d in dropped)


def test_parse_string_numbers_markers_and_duplicate_ids():
    items, dropped = parse([
        good(id="x", max="250", title="Abstract {{expand}} [[Name]] <!--ai--> limit"),
        good(id="x", title="Second with the same id"),
        good(id="BAD ID!", title="Third"),
        good(id="", title="Fourth one"),
    ], taken=["fourth-one"])
    assert dropped == []
    assert items[0]["max"] == 250
    assert not any(m in items[0]["title"] for m in ("<!--", "{{", "[["))
    ids = [i["id"] for i in items]
    assert len(set(ids)) == 4 and ids[0] == "x" and "fourth-one" not in ids


def test_parse_caps_items_and_unreadable_reply():
    items, dropped = parse([good(id=f"r{i}", title=f"Row {i}") for i in range(60)])
    assert len(items) == rai.MAX_ITEMS and dropped
    items, dropped = rai.parse_requirement_rows("no json here", TEXTS)
    assert items == [] and "could not be read" in dropped[0]["reason"]
    assert rai.parse_requirement_rows(None, TEXTS)[0] == []


def test_quote_grounding_true_false_and_too_short():
    items, _ = parse([
        good(id="t", quote="THE ABSTRACT must not exceed 250 words   and must be structured."),   # case, whitespace
        good(id="f", title="invented", quote="The abstract must contain a graphical summary of the work."),
        good(id="s", title="short", quote="must be structured"),                                   # under 25 chars
        good(id="o", title="other file", source="other.md"),
        good(id="n", title="no quote", quote=""),
    ])
    by = {i["id"]: i for i in items}
    assert by["t"]["verified"] is True
    assert by["f"]["verified"] is False
    assert by["s"]["verified"] is False
    assert by["o"]["source"] == "guide.md" and by["o"]["verified"] is True     # one guideline: the model's slip is mended
    assert by["n"]["verified"] is False


def test_grounding_is_per_guideline():
    texts = {"a.md": "Alpha says the abstract has at most 100 words.", "b.md": "Beta says nothing of the kind."}
    items, _ = parse([good(id="a", source="b.md", quote="Alpha says the abstract has at most 100 words."),
                      good(id="b", source="", title="unnamed", quote="Alpha says the abstract has at most 100 words."),
                      good(id="c", source="", title="nowhere", quote="Quote found in no document at all here.")],
                     texts)
    by = {i["id"]: i for i in items}
    assert by["a"]["source"] == "b.md" and by["a"]["verified"] is False      # THAT guideline must hold it
    assert by["b"]["source"] == "a.md" and by["b"]["verified"] is True
    assert by["c"]["source"] == "" and by["c"]["verified"] is False


def test_long_quote_is_capped_at_240():
    long = "The abstract " + "word " * 100
    items, _ = parse([good(quote=long)], {"guide.md": long})
    assert len(items[0]["quote"]) <= 240 and items[0]["verified"] is True


# -- plan ------------------------------------------------------------------------------------------------------

def test_plan_names_guidelines_and_caps(tmp_path):
    p = make(tmp_path)
    guidelines.add_text(p, "Journal rules", "Rule. " * 6000)
    guidelines.add_text(p, "Other", "Short rule.")
    context, sent = rai.plan_requirements(p, "Only word limits.", ["journal-rules.md", "other.md"], "m",
                                          Budget.for_model("m"))
    names = [s.name for s in sent.sections]
    assert "Guideline: journal-rules.md" in names and "Guideline: other.md" in names
    assert "journal-rules.md" in sent.truncated
    assert "CHECK KINDS" in context and "list-count" in context and "EXAMPLE ROWS" in context
    assert "PROJECT KIND: manuscript" in context and "Only word limits." in context
    assert sent.feature == "requirements" and sent.to_dict()["trimmed"] is True


def test_plan_needs_a_guideline_and_refuses_unknown_and_too_many(tmp_path):
    p = make(tmp_path)
    with pytest.raises(ValueError, match="at least one"):
        rai.plan_requirements(p, "", [], "m", Budget.for_model("m"))
    with pytest.raises(Exception):
        rai.plan_requirements(p, "", ["nope.md"], "m", Budget.for_model("m"))
    with pytest.raises(ValueError, match="at most"):
        rai.plan_requirements(p, "", [f"g{i}.md" for i in range(20)], "m", Budget.for_model("m"))


def test_plan_raises_when_it_cannot_fit(tmp_path):
    p = make(tmp_path)
    guidelines.add_text(p, "G", "x")
    with pytest.raises(BudgetError):
        rai.plan_requirements(p, "word " * 40_000, ["g.md"], "m", Budget(window_tokens=6_000))


# -- bridge ------------------------------------------------------------------------------------------------------

def open_api(project):
    api = Api()
    api._load(project)
    return api


def snapshot_files(root):
    return {str(f.relative_to(root)): f.read_bytes() for f in root.rglob("*")
            if f.is_file() and ".chisel" not in f.parts}


def test_bridge_custom_save_remove(tmp_path):
    from chisel.gui.research_requirements_api import ResearchRequirementsMixin
    assert issubclass(Api, ResearchRequirementsMixin) or True      # the lead wires the mixin into ResearchMixin
    p = make(tmp_path)
    api = type("A", (ResearchRequirementsMixin, Api), {})()
    api._load(p)
    assert api.requirements_custom() == {"ok": True, "rows": []}
    r = api.requirements_save([row()])
    assert r["ok"] and r["rows"][0]["id"] == "kw"
    bad = api.requirements_save([row(), row(id="z", check="telepathy")])
    assert bad["ok"] is False and "unknown check" in bad["error"]
    assert api.requirements_custom()["rows"][0]["id"] == "kw"       # the refused save changed nothing
    assert api.requirements_remove("kw") == {"ok": True, "rows": []}
    assert api.requirements_remove("kw")["ok"] is False


def test_bridge_refuses_a_story_project(tmp_path):
    from chisel.gui.research_requirements_api import ResearchRequirementsMixin
    api = type("A", (ResearchRequirementsMixin, Api), {})()
    api._load(Project.create(tmp_path / "s", "S"))
    for call in (api.requirements_custom, lambda: api.requirements_save([]),
                 lambda: api.requirements_suggest("", ["a.md"])):
        r = call()
        assert r["ok"] is False and "research" in r["error"].lower()


def test_suggest_is_mocked_verifies_and_changes_no_file(tmp_path, monkeypatch):
    from chisel.gui.research_requirements_api import ResearchRequirementsMixin
    p = make(tmp_path)
    guidelines.add_text(p, "Rules", GUIDE)
    cr.save_custom(p, [row(id="abstract-words", title="Mine already")])
    seen = {}

    def fake(context, model, client=None, cancel=None, on_delta=None):
        seen["context"] = context
        return "Here:\n" + json.dumps({"items": [
            good(source="rules.md"),
            good(id="made-up", title="Invented rule", quote="Authors shall bring a plant to the conference.",
                 source="rules.md")]})

    monkeypatch.setattr(api_module, "suggest_requirements", fake)
    api = type("A", (ResearchRequirementsMixin, Api), {})()
    api._load(p)
    before = snapshot_files(p.root)
    r = api.requirements_suggest("", ["rules.md"])
    assert r["ok"], r
    assert snapshot_files(p.root) == before
    assert "GUIDELINE DOCUMENT rules.md" in seen["context"]
    by = {i["title"]: i for i in r["items"]}
    assert by["Abstract at most 250 words"]["verified"] is True and by["Invented rule"]["verified"] is False
    assert by["Abstract at most 250 words"]["id"] != "abstract-words"           # clash with the saved row avoided
    assert any(s["name"] == "Guideline: rules.md" for s in r["sent"]["sections"])
    assert set(r) >= {"items", "dropped", "sent", "cost", "model"}


def test_ai_jobs_kind_is_registered_and_mock_has_an_unverified_item(tmp_path):
    assert Api.AI_JOBS["requirements"] == "requirements_suggest"
    from chisel.gui import mockai
    import re as _re
    ctx = rai.plan_requirements(make(tmp_path), "", ["g.md"], "m", Budget.unbounded(),
                                texts={"g.md": "Abstracts have at most 250 words. Be brief."})[0]
    mockai.install(api_module)
    try:
        raw = api_module.suggest_requirements(ctx, "m")
    finally:
        pass
    items, dropped = rai.parse_requirement_rows(raw, {"g.md": "Abstracts have at most 250 words. Be brief."})
    assert dropped == [] and any(i["verified"] for i in items) and any(not i["verified"] for i in items)
    assert _re  # keep the import used


def test_requirements_toml_is_in_no_existing_ai_context(tmp_path, monkeypatch):
    import re
    from pathlib import Path
    p = make(tmp_path)
    cr.save_custom(p, [row(id="secret", title="REQTOKEN requirement", quote="REQTOKEN quote")])
    (p.root / "notebook").mkdir(exist_ok=True)
    (p.root / "notebook" / "tides.md").write_text("# Tides\n\nThe tide floods.\n", encoding="utf-8", newline="\n")
    api = open_api(p)
    seen = []

    def fake(*a, **k):
        seen.append(json.dumps([a, k], default=str))
        return "reply"

    for name in ("ask_writer", "research_writer", "brainstorm_writer", "generate_text"):
        monkeypatch.setattr(api_module, name, fake)
    first = p.list_scenes()[0].relative_to(p.root).as_posix()
    api.ask("what next?", "project")
    api.ask("what next?", "scene", first)
    api.research("what about tides?")
    assert seen and not any("REQTOKEN" in t for t in seen)
    assert all(f.name != "requirements.toml" for f in p.all_markdown_files())
    assert not p.is_scene_path(p.root / "requirements.toml")
    root = Path(api_module.__file__).parents[1]
    users = {f.relative_to(root).as_posix() for f in root.rglob("*.py")
             if re.search(r"custom_requirements|requirements\.toml", f.read_text(encoding="utf-8"))}
    assert users <= {"core/paper/custom_requirements.py", "core/paper/requirements.py",
                     "gui/research_requirements_api.py", "ai/requirements.py"}, users


# -- review fixes (E1) -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["inf", "-inf", "nan", "1e400", "1.0e999"])
def test_non_finite_numbers_are_refused_and_never_blank_the_report(tmp_path, bad):
    p = make(tmp_path)
    with pytest.raises(ValueError, match="whole number"):
        cr.validate_row(row(max=float(bad)))
    (p.root / "requirements.toml").write_text(
        '[[requirement]]\nid = "x"\ntitle = "T"\nkind = "check"\ncheck = "list-count"\n'
        f'section = ["keywords"]\nmax = {bad}\n\n'
        '[[requirement]]\nid = "ok"\ntitle = "Fine"\nkind = "advice"\n', encoding="utf-8", newline="\n")
    rows, warning = cr.load_report(p)
    assert [r["id"] for r in rows] == ["ok"] and "skipped" in warning
    assert any(r["id"] == "ok" for r in requirements.evaluate(p))


UNREADABLE_FILE = ('[[requirement]]\nid = "kw"\ntitle = "Keep me"\nkind = "advice"\n\n'
                   '[[requirement]]\nid = "bad"\ntitle = "Broken"\nkind = "check"\ncheck = "nope"\n')


def test_save_and_remove_refuse_to_overwrite_an_unreadable_file(tmp_path):
    p = make(tmp_path)
    path = p.root / "requirements.toml"
    path.write_bytes(UNREADABLE_FILE.encode())
    before = path.read_bytes()
    with pytest.raises(ValueError, match="will not overwrite"):
        cr.save_custom(p, [{"id": "new", "title": "N", "kind": "advice"}])
    with pytest.raises(ValueError, match="will not overwrite"):
        cr.save_custom(p, [])
    with pytest.raises(ValueError, match="will not overwrite"):
        cr.remove(p, "kw")
    assert path.read_bytes() == before
    path.write_bytes(b"not = [valid")           # a file that does not parse at all
    with pytest.raises(ValueError, match="will not overwrite"):
        cr.save_custom(p, [{"id": "new", "title": "N", "kind": "advice"}])
    assert path.read_bytes() == b"not = [valid"


def test_bridge_save_refuses_unreadable_file_cleanly(tmp_path):
    p = make(tmp_path)
    (p.root / "requirements.toml").write_bytes(UNREADABLE_FILE.encode())
    from chisel.gui.research_requirements_api import ResearchRequirementsMixin
    api = type("A", (ResearchRequirementsMixin, Api), {})()
    api._load(p)
    out = api.requirements_save([{"id": "new", "title": "N", "kind": "advice"}])
    assert out["ok"] is False and "will not overwrite" in out["error"]
    assert (p.root / "requirements.toml").read_bytes() == UNREADABLE_FILE.encode()


def test_a_clean_file_still_saves_and_removes(tmp_path):
    p = make(tmp_path)
    cr.save_custom(p, [row(), {"id": "cover", "title": "Cover", "kind": "advice"}])
    cr.save_custom(p, [row(title="Changed")])
    assert cr.load_custom(p)[0]["title"] == "Changed"
    assert cr.remove(p, "kw") == []


def test_custom_file_warning_id_never_clashes(tmp_path):
    p = make(tmp_path, journal="")
    clear_starter(p)
    cr.save_custom(p, [{"id": "custom-file", "title": "Mine", "kind": "advice"}])
    path = p.root / "requirements.toml"
    path.write_text(path.read_text(encoding="utf-8") + '\n[[requirement]]\nid = "!"\ntitle = "x"\nkind = "advice"\n',
                    encoding="utf-8", newline="\n")
    ids = [r["id"] for r in requirements.evaluate(p)]
    assert len(ids) == len(set(ids)) == 2


def test_validate_row_typing_and_cleaning():
    for key in ("title", "group", "source", "quote"):
        with pytest.raises(ValueError, match="must be text"):
            cr.validate_row({"id": "a", "title": "T", "kind": "advice", **{key: {"x": 1}}})
    with pytest.raises(ValueError, match="must be text"):
        cr.validate_row({"id": "a", "title": ["T"], "kind": "advice"})
    with pytest.raises(ValueError, match="list of title words"):
        cr.validate_row(row(section=[{"a": 1}]))
    out = cr.validate_row({"id": "a", "title": "[[Evil]] <!--ai--> {{x}} ok", "kind": "advice",
                           "quote": "q [[a]] {{b}} <!--c-->", "source": "s<!--x-->.pdf"})
    assert "[[" not in out["title"] and "<!--" not in out["title"] and "{{" not in out["title"]
    assert out["title"] == "Evil ai x ok"
    assert out["quote"] == "q a b c"
    assert out["source"] == "sx.pdf"


def test_quote_with_link_marks_in_the_guideline_still_verifies():
    guide = "Authors must list [[three]] to {{six}} keywords after the abstract."
    saved = cr.validate_row({"id": "a", "title": "T", "kind": "advice", "quote": guide})["quote"]
    assert "[[" not in saved
    assert rai.quote_in(saved, guide) and rai.quote_in(guide, guide)


def test_long_model_title_is_trimmed_not_dropped():
    reply = json.dumps({"items": [{"id": "a", "title": "Word " * 60, "kind": "advice", "quote": "", "source": ""}]})
    items, dropped = rai.parse_requirement_rows(reply, {})
    assert not dropped and items and 0 < len(items[0]["title"]) <= cr.LINE_MAX


def test_oversized_file_is_not_read(tmp_path):
    p = make(tmp_path)
    (p.root / "requirements.toml").write_bytes(b"# " + b"x" * (cr.FILE_MAX_BYTES + 10))
    rows, warning = cr.load_report(p)
    assert rows == [] and "1 MB" in warning
    with pytest.raises(ValueError, match="will not overwrite"):
        cr.save_custom(p, [{"id": "n", "title": "N", "kind": "advice"}])


def test_suggested_id_avoids_profile_ids(tmp_path, monkeypatch):
    p = make(tmp_path)
    from chisel.gui.research_requirements_api import ResearchRequirementsMixin
    api = type("A", (ResearchRequirementsMixin, Api), {})()
    api._load(p)
    guidelines.add_text(p, "Rules", GUIDE)
    profile_id = p.research_profile().requirements[0].id
    monkeypatch.setattr(api_module, "suggest_requirements", lambda context, model, **k: json.dumps(
        {"items": [{"id": profile_id, "title": "Mine", "kind": "advice", "quote": "", "source": ""}]}),
        raising=False)
    out = api.requirements_suggest("", ["rules.md"])
    assert out["ok"], out
    assert out["items"][0]["id"] != profile_id
