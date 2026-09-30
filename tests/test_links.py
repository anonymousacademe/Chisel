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


def test_overlapping_mentions_prefer_the_longest():
    names = ["Hollow Market", "the Hollow", "the Meridian", "Meridian"]
    text = "Rain in the Hollow Market. Back at the Hollow, the Meridian slept."
    got = [m.target for m in find_mentions(text, names)]
    assert got == ["Hollow Market", "the Hollow", "the Meridian"]


def _bruteforce_mentions(text, names):
    """The original O(n^2) resolution, kept as the reference."""
    from lorewrite.core.links import _mention_re, find_links

    pattern = _mention_re(tuple(sorted(set(names))))
    taken = [(l.start, l.end) for l in find_links(text)]
    candidates = sorted(((m.start(1), m.end(1)) for m in pattern.finditer(text)),
                        key=lambda span: (span[0] - span[1], span[0]))
    chosen = []
    for start, end in candidates:
        if any(s < end and start < e for s, e in taken):
            continue
        taken.append((start, end))
        chosen.append((start, end))
    return sorted(chosen)


def test_find_mentions_matches_bruteforce_reference():
    import random

    from lorewrite.core.links import find_mentions

    rng = random.Random(7)
    words = ["the", "Hollow", "Market", "Hollow Market", "the Hollow", "Rook", "Rook Tanaka",
             "[[Rook|the man]]", "said", "rain", "Wren", "[[Hollow Market]]", "\n", "\n\n"]
    names = ["the Hollow", "Hollow Market", "Rook", "Rook Tanaka", "Wren", "Market"]
    for _ in range(200):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(1, 60)))
        got = [(m.start, m.end) for m in find_mentions(text, names)]
        assert got == _bruteforce_mentions(text, names), text


def test_find_mentions_scales_to_a_huge_dense_scene():
    import time

    from lorewrite.core.links import find_mentions

    text = " ".join(["Rook said Wren spoke in the Hollow Market"] * 6000)  # ~250 KB, ~18k mentions
    t = time.time()
    found = find_mentions(text, ["Rook", "Wren", "Hollow Market"])
    assert len(found) == 18000
    assert time.time() - t < 3.0  # was tens of seconds when quadratic
