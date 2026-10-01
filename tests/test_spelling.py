import time

import pytest

from lorewrite.core import spelling as sp
from lorewrite.core.project import Project
from tests.gui_helpers import make_project


def bad(text, accepted=None):
    return [m.word for m in sp.check(text, accepted)]


# -- tokenizer ----------------------------------------------------------------

def test_flags_misspelling_with_offsets():
    text = "She would recieve it."
    [m] = sp.check(text)
    assert (m.word, text[m.start:m.end]) == ("recieve", "recieve")


def test_possessives_straight_and_curly():
    assert bad("Rook's nest and Rook’s nest, the dogs' bowl") == []
    [m] = sp.check("Zorble's hat")
    assert m.word == "Zorble"  # the 's is not part of the span


def test_possessive_strip_does_not_eat_letters():
    # str.strip("'s") would turn "glass" into "gla"
    assert bad("the glass and the moss") == []
    assert bad("hiss's") == [] or bad("hiss's") == ["hiss"]


def test_contractions():
    assert bad("don't wasn't she'd I'll they've") == []
    assert bad("dont") == ["dont"]


def test_hyphenated_words():
    assert bad("a noodle-stall and a well-known man") == []
    [m] = sp.check("a noodle-stal here")
    assert m.word == "stal"
    text = "a noodle-stal here"
    assert text[m.start:m.end] == "stal"


def test_skips():
    text = "\n".join([
        "---", "name: Qzx", "aliases: [Blorfle]", "---", "",
        "# Heading words", "",
        "inline `codez` and https://exampl.zzz/qwe and me@exmple.zzz",
        "```", "fenced bloop", "```",
        "<!--ai id=\"abc123\"-->", "{{expand: blorb the thing}}",
        "NYPD K-V a 3rd x2 snake_case",
    ])
    assert bad(text) == []


def test_heading_words_are_checked():
    assert bad("# The recieving dock") == ["recieving"]


def test_wikilinks():
    assert bad("[[Quuxor]]") == []  # names an entity, not prose
    assert bad("[[Quuxor|the shownn word]]") == ["shownn"]


def test_pending_draft_bodies_are_checked_markers_skipped():
    text = 'ok <!--ai id="abc123-->x<!--/ai--> <!--ai id="abc123"-->mispelled<!--/ai-->'
    assert "mispelled" in bad(text)
    assert "abc123" not in bad(text)


def test_non_latin_and_accents():
    assert bad("café naïve 你好") == []


def test_offsets_with_astral_characters_are_code_points():
    text = "\U0001F600 recieve"
    [m] = sp.check(text)
    assert text[m.start:m.end] == "recieve"


# -- accepted terms -------------------------------------------------------------

def test_case_rules():
    acc = sp.AcceptedTerms.from_terms(["Kessler", "maglev"])
    assert bad("Kessler maglev Maglev MAGLEV", acc) == []
    assert bad("kessler", acc) == ["kessler"]


def test_phrase_acceptance():
    acc = sp.AcceptedTerms.from_terms(["maglev spur"])
    assert bad("the maglev spur ran", acc) == []
    assert bad("the Maglev   Spur ran", acc) == []  # case + whitespace
    assert bad("a maglev alone", acc) == ["maglev"]


def test_entity_names_and_aliases_accepted(tmp_path):
    project = make_project(tmp_path / "p")
    (project.root / "entities" / "characters" / "zed.md").write_text(
        "---\nname: Zedquik Vorn\ntype: character\naliases: [Zeddo]\n---\n\n")
    acc = sp.accepted_terms(project)
    assert bad("Zedquik Vorn met Zeddo and Vorn and Zedquik", acc) == []
    assert bad("zeddo", acc) == ["zeddo"]


def test_session_ignores_and_dictionaries(tmp_path):
    project = make_project(tmp_path / "p")
    sp.add_to_dictionary(sp.project_dictionary_path(project), "Blorfle")
    sp.add_to_dictionary(sp.personal_dictionary_path(), "snarfblat")
    acc = sp.accepted_terms(project, ignored=["wibble"])
    assert bad("Blorfle snarfblat wibble", acc) == []


def test_personal_dictionary_honours_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOREWRITE_STATE_DIR", str(tmp_path / "elsewhere"))
    assert sp.personal_dictionary_path() == tmp_path / "elsewhere" / "dictionary.txt"


def test_dictionary_file_is_not_a_scene_or_entity(tmp_path):
    project = make_project(tmp_path / "p")
    sp.add_to_dictionary(sp.project_dictionary_path(project), "Blorfle")
    assert all(p.name != "dictionary.txt" for p in project.all_markdown_files())
    assert all(p.name != "dictionary.txt" for p in project.list_scenes())
    assert Project.open(project.root).load_entities()  # still loads fine


# -- dictionary files -------------------------------------------------------------

def test_dictionary_add_remove_dedupe_comments(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_text("# my words\n\nalpha")  # no trailing newline
    assert sp.add_to_dictionary(path, "beta  gamma")
    assert not sp.add_to_dictionary(path, "alpha")
    assert not sp.add_to_dictionary(path, "  ")
    assert sp.load_dictionary(path) == ["alpha", "beta gamma"]
    assert path.read_text().startswith("# my words\n\nalpha\nbeta gamma\n")
    assert sp.remove_from_dictionary(path, "alpha")
    assert not sp.remove_from_dictionary(path, "alpha")
    assert sp.load_dictionary(path) == ["beta gamma"]
    assert path.read_text().startswith("# my words\n")


def test_dictionary_writes_are_atomic(tmp_path):
    path = tmp_path / "dictionary.txt"
    sp.add_to_dictionary(path, "alpha")
    assert not list(tmp_path.glob("*.tmp"))


def test_ensure_dictionary_creates_header_once(tmp_path):
    path = tmp_path / "dictionary.txt"
    sp.ensure_dictionary(path)
    assert path.read_text().startswith("#")
    path.write_text("mine\n")
    sp.ensure_dictionary(path)
    assert path.read_text() == "mine\n"
    assert sp.load_dictionary(sp.ensure_dictionary(tmp_path / "x" / "d.txt")) == []


# -- suggestions ------------------------------------------------------------------

def test_suggestions_keep_capitalisation():
    assert sp.suggestions("recieve")[0] == "receive"
    assert sp.suggestions("Recieve")[0] == "Receive"
    assert sp.suggestions("RECIEVE")[0] == "RECEIVE"
    assert len(sp.suggestions("recieve", n=1)) == 1
    assert sp.suggestions("") == []


# -- performance --------------------------------------------------------------------

def test_check_50k_words_is_fast():
    para = ("The quick brown fox jumped over the lazy dog while Kessler watched "
            "the noodle-stall and Rook's recieve of it. ")
    text = para * 2500  # ~55k words
    sp.check("warm")
    t0 = time.perf_counter()
    found = sp.check(text)
    elapsed = time.perf_counter() - t0
    assert found
    assert elapsed < 0.3, elapsed
