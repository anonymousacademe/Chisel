from lorewrite.core.links import (
    find_all_links,
    find_links,
    find_mentions,
    link_at,
    offset_to_rowcol,
    rowcol_to_offset,
)


def test_find_plain_link():
    links = find_links("Hello [[Elara Vance]], goodbye.")
    assert len(links) == 1
    assert links[0].target == "Elara Vance"
    assert links[0].display is None
    assert links[0].text == "Elara Vance"


def test_find_aliased_link():
    links = find_links("[[Elara Vance|the captain]] walked in")
    assert links[0].target == "Elara Vance"
    assert links[0].display == "the captain"
    assert links[0].text == "the captain"


def test_multiple_links_offsets():
    text = "[[A]] and [[B]]"
    links = find_links(text)
    assert [l.target for l in links] == ["A", "B"]
    assert text[links[0].start:links[0].end] == "[[A]]"
    assert text[links[1].start:links[1].end] == "[[B]]"


def test_unclosed_bracket_ignored():
    assert find_links("[[not a link") == []
    assert find_links("[[also not|") == []


def test_link_at():
    text = "see [[Borin]] here"
    link = link_at(text, 6)
    assert link is not None and link.target == "Borin"
    assert link_at(text, 3) is None
    # edge: offset at end boundary still counts as inside
    assert link_at(text, link.end) is not None


def test_rowcol_roundtrip():
    text = "line one\nline two\nline three"
    for offset in range(len(text) + 1):
        row, col = offset_to_rowcol(text, offset)
        assert rowcol_to_offset(text, row, col) == offset


# -- implicit mentions (no brackets needed) ---------------------------------------

NAMES = ["Elara Vance", "Elara", "the captain", "Borin", "Will", "X"]


def test_mentions_match_names_and_aliases_on_word_boundaries():
    text = "Elara Vance met Elara's crew. Elaras is not a name."
    got = [(m.target, m.start) for m in find_mentions(text, NAMES)]
    assert got == [("Elara Vance", 0), ("Elara", 16)]
    assert all(not m.explicit for m in find_mentions(text, NAMES))


def test_mentions_are_case_sensitive_but_allow_sentence_start():
    text = "The captain nodded; the captain left. Will will go. elara slept."
    got = [m.target for m in find_mentions(text, NAMES)]
    assert got == ["The captain", "the captain", "Will"]


def test_mentions_skip_explicit_links_and_one_letter_names():
    text = "[[Borin]] and Borin met X."
    links = find_all_links(text, NAMES)
    assert [(l.target, l.explicit) for l in links] == [
        ("Borin", True), ("Borin", False)]


def test_find_all_links_without_names_is_explicit_only():
    assert [l.target for l in find_all_links("Borin and [[Borin]]")] == ["Borin"]
