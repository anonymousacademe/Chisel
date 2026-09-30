"""core.spans: what an editor needs to decorate a text."""

from lorewrite.core import drafts
from lorewrite.core.entities import Entity
from lorewrite.core.spans import compute_spans, to_utf16

MARA = Entity(name="Mara Vale", type="character", aliases=["Mara"])
MERIDIAN = Entity(name="Lower Meridian", type="place")
ENTITIES = [MARA, MERIDIAN]


def kinds(spans):
    return [(s["kind"], s.get("target") or s.get("instruction") or s.get("id")) for s in spans]


def test_plain_mentions_and_explicit_links():
    text = "Mara walked to [[Lower Meridian|the district]] and [[Nowhere]] again."
    spans = compute_spans(text, ENTITIES)
    assert kinds(spans) == [("mention", "Mara"), ("link", "Lower Meridian"),
                            ("unresolved", "Nowhere")]
    link = spans[1]
    # the visible part is the display text; brackets and "Lower Meridian|" hide
    assert text[link["innerStart"]:link["innerEnd"]] == "the district"
    assert text[link["start"]:link["end"]] == "[[Lower Meridian|the district]]"
    assert link["entity"] == "Lower Meridian" and link["etype"] == "place"
    plain = compute_spans("see [[Mara]]", ENTITIES)[0]
    assert "see [[Mara]]"[plain["innerStart"]:plain["innerEnd"]] == "Mara"


def test_mentions_off_for_notes():
    spans = compute_spans("Mara and [[Mara]]", ENTITIES, mentions=False)
    assert kinds(spans) == [("link", "Mara")]


def test_pending_and_expand_spans_and_no_links_inside_drafts():
    text = ('Mara <!--ai-->Mara sighed.<!--/ai--> then '
            '<!--ai id="abc123"-->[[Lower Meridian]] rang<!--/ai--> '
            '{{expand: the rain}}')
    spans = compute_spans(text, ENTITIES)
    assert kinds(spans) == [("mention", "Mara"), ("pending", None),
                            ("pending", "abc123"), ("expand", "the rain")]
    first = spans[1]
    assert text[first["bodyStart"]:first["bodyEnd"]] == "Mara sighed."
    assert text[first["start"]:first["end"]].startswith("<!--ai-->")


def test_utf16_conversion_with_astral_characters():
    text = "\U0001F600 Mara is here"  # the emoji is 2 UTF-16 units
    spans = compute_spans(text, ENTITIES)
    assert spans[0]["start"] == 2  # code points
    converted = to_utf16(text, spans)
    assert converted[0]["start"] == 3 and converted[0]["end"] == 7
    assert spans[0]["start"] == 2  # input untouched
    plain = "no emoji Mara"
    assert to_utf16(plain, compute_spans(plain, ENTITIES)) == compute_spans(plain, ENTITIES)


def test_drafts_module_agrees_on_pending_offsets():
    text = "a<!--ai-->b<!--/ai-->c"
    span = [s for s in compute_spans(text, []) if s["kind"] == "pending"][0]
    assert span["start"] == drafts.find_pending(text)[0].start
