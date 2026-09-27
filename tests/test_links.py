from lorewrite.core.links import find_links, link_at, offset_to_rowcol, rowcol_to_offset


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
