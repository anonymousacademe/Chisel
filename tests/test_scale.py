"""scale_hint: when to tell the author the project has outgrown the AI's view."""

from types import SimpleNamespace

from chisel.core import scale
from chisel.core import summaries as sm
from chisel.core.entities import Entity
from tests.gui_helpers import make_project

WINDOW = 100_000          # tokens: about 76,900 words


def project(entities=3, mode="story"):
    return SimpleNamespace(mode=mode, load_entities=lambda: [Entity(name=f"E{i}") for i in range(entities)],
                           counted_scenes=lambda: [])


def cov(total, summarised=0, stale=0):
    ids = {s: [] for s in sm.STATUSES}
    ids["fresh"] = [f"s{i}" for i in range(summarised - stale)]
    ids["stale"] = [f"t{i}" for i in range(stale)]
    ids["missing"] = [f"m{i}" for i in range(total - summarised)]
    return sm.Coverage(total, ids)


def hint(words, scenes, entities=3, summarised=0, window=WINDOW, **kw):
    return scale.scale_hint(project(entities), window, words=words, coverage=cov(scenes, summarised), **kw)


def test_short_project_is_left_alone():
    h = hint(20_000, 10)
    assert h["level"] == "none" and h["message"] == ""
    assert h["numbers"]["words"] == 20_000 and h["numbers"]["scenes"] == 10 and h["numbers"]["ratio"] == 0.3


def test_notice_triggers_each_on_its_own():
    # prose more than 1.5 windows (1.3 tokens a word)
    assert hint(115_000, 10)["level"] == "none"          # 149.5k tokens: just under 1.5 x 100k
    long = hint(116_000, 10)
    assert long["level"] == "notice" and "scene you are working on" in long["message"]
    assert hint(1000, 29)["level"] == "none" and hint(1000, 30)["level"] == "notice"
    assert hint(1000, 5, entities=39)["level"] == "none"
    many = hint(1000, 5, entities=40)
    assert many["level"] == "notice" and "None of your 5 scenes has a summary yet" in many["message"]


def test_strong_needs_four_windows_and_under_half_summarised():
    words = int(4 * WINDOW / scale.WORDS_TO_TOKENS) + 1000
    assert hint(words, 100, summarised=49)["level"] == "strong"
    assert hint(words, 100, summarised=50)["level"] == "notice"
    just_under = int(4 * WINDOW / scale.WORDS_TO_TOKENS) - 1000
    assert hint(just_under, 100, summarised=0)["level"] == "notice"


def test_well_summarised_book_is_not_nagged():
    assert hint(300_000, 120, summarised=108)["level"] == "none"         # 90 percent
    assert hint(300_000, 120, summarised=107)["level"] == "notice"


def test_message_is_plain_true_and_says_what_to_do():
    h = hint(400_000, 200, summarised=10)
    assert h["level"] == "strong"
    m = h["message"]
    assert "Chisel sends it only the scene you are working on and its characters’ notes" in m
    assert "10 of your 200 scenes have a summary" in m
    assert "you review each before it is kept" in m and "the cost is shown first" in m
    assert "helps with that" in m and "fixes" not in m and "fix that" not in m
    n = hint(120_000, 40, summarised=0)["message"]
    assert "not the rest of the book, so it cannot see earlier chapters" in n
    for text in (m, n):
        assert "token" not in text.lower() and "read at once" not in text and "window" not in text.lower()


def test_every_message_is_short_and_never_says_only_zero():
    words = int(4 * WINDOW / scale.WORDS_TO_TOKENS) + 1000
    for level_words, scenes in ((120_000, 40), (words, 100), (1000, 30)):
        for summarised in (0, 1, 2, scenes // 3, scenes - 1):
            h = hint(level_words, scenes, summarised=summarised)
            m = h["message"]
            if not m:
                continue
            assert len(m.split()) <= 60, (len(m.split()), m)
            assert "only 0" not in m.lower() and "0 of" not in m.replace("10 of", "").replace("20 of", "")
            assert 2 <= m.count(". ") + 1 <= 3 and m.endswith(".")
    assert "None of your 100 scenes has a summary yet" in hint(words, 100, summarised=0)["message"]
    assert "1 of your 100 scenes has a summary" in hint(words, 100, summarised=1)["message"]
    assert scale.coverage_phrase({"summarised": 41, "scenes": 41}) == "All 41 of your scenes have a summary"
    assert scale.coverage_phrase({"summarised": 0, "scenes": 1}) == "Your scene has no summary yet"
    for level in ("notice", "strong"):      # the two wordings differ in emphasis only
        assert len(scale._message(level, {"summarised": 3, "scenes": 41}).split()) <= 60


def test_dismissed_hides_that_level_but_not_a_stronger_one():
    words = int(4 * WINDOW / scale.WORDS_TO_TOKENS) + 1000
    notice = hint(120_000, 40, dismissed="notice")
    assert notice["level"] == "none" and notice["dismissed"] is True and notice["message"] == ""
    assert hint(words, 100, dismissed="notice")["level"] == "strong"
    assert hint(words, 100, dismissed="strong")["level"] == "none"
    assert hint(1000, 5, dismissed="strong")["dismissed"] is False        # nothing to hide


def test_research_and_empty_projects_have_no_hint():
    r = scale.scale_hint(project(100, mode="research"), WINDOW, words=900_000, coverage=cov(300))
    assert r["level"] == "none"
    assert scale.scale_hint(project(), WINDOW, words=0, coverage=cov(0))["level"] == "none"


def test_a_smaller_window_triggers_sooner():
    assert hint(20_000, 10, window=6_000)["level"] == "strong"


def test_counts_words_and_coverage_from_a_real_project(tmp_path):
    p = make_project(tmp_path / "p")
    a, b = p.list_scenes()
    sm.save(p.root, a, sm.Summary(sm.current_hash(p, a), "Arrival."))
    h = scale.scale_hint(p, WINDOW)
    assert h["level"] == "none"
    assert h["numbers"]["scenes"] == 2 and h["numbers"]["summarised"] == 1 and h["numbers"]["missing"] == 1
    assert h["numbers"]["entities"] == 3
    raw = sum(len(x.read_text(encoding="utf-8").split()) for x in (a, b))
    assert h["numbers"]["words"] == scale.count_words(p) < raw          # the AI draft in scene 2 is not counted


# -- what the AI still does not see once summaries cover the book ------------------------------


def real_book(tmp_path, scenes=6, summarised=6, words=40):
    p = make_project(tmp_path / "p")
    for f in p.list_scenes():
        f.unlink()
    for n in range(1, scenes + 1):
        path = p.manuscript_dir / f"{n:02d}-s{n}.md"
        path.write_text(f"# Scene {n}\n\nMara met someone. Mark {n}.\n", encoding="utf-8")
        if n <= summarised:
            sm.save(p.root, path, sm.Summary(sm.current_hash(p, path), f"Event {n}. " + "filler " * words))
    return p


def test_the_continuity_reserve_mirrors_the_budget():
    from chisel.ai import budget

    assert scale.CONTINUITY_RESERVE == budget.DEFAULT_RESERVE


def test_after_is_none_without_summaries_or_with_low_coverage(tmp_path):
    none = real_book(tmp_path / "a", summarised=0)
    low = real_book(tmp_path / "b", scenes=10, summarised=5)
    for p in (none, low):
        assert scale.scale_hint(p, 32_000, words=1000, coverage=sm.coverage(p))["after"] is None
    research = scale.scale_hint(project(mode="research"), WINDOW, words=1, coverage=cov(5, 5))
    assert research["after"] is None and hint(10, 5)["after"] is None


def test_after_states_what_the_ai_still_does_not_see_with_a_real_number(tmp_path):
    p = real_book(tmp_path, scenes=6, summarised=6)
    out = scale.scale_hint(p, 32_000, words=1000, coverage=sm.coverage(p))
    assert out["level"] == "none" and out["message"] == ""
    text = out["after"]
    assert text.startswith("Summaries cover your whole book. When you check a scene, Chisel sends a short story so far (about ")
    assert text.endswith("for your last scene) and what is recorded about the characters in it, not the full text of earlier chapters.")
    story = sm.story_so_far(p, "manuscript/06-s6.md", cap_tokens=32_000 - scale.CONTINUITY_RESERVE)
    tokens = -(-len(story.text) // sm.CHARS_PER_TOKEN)
    assert f"about {scale._round(tokens):,} tokens, roughly {scale._round(int(tokens / scale.WORDS_TO_TOKENS)):,} words" in text
    assert "only 0" not in text and len(text.split()) < 60


def test_after_says_most_when_not_every_scene_has_a_summary_and_follows_the_cap(tmp_path):
    p = real_book(tmp_path, scenes=10, summarised=9)
    out = scale.scale_hint(p, 32_000, words=1000, coverage=sm.coverage(p))
    assert out["after"].startswith("Summaries cover most of your book.")
    big = real_book(tmp_path / "big", scenes=6, summarised=6, words=400)          # long summaries: the cap bites
    wide = scale.scale_hint(big, 32_000, words=1000, coverage=sm.coverage(big))["after"]
    narrow = scale.scale_hint(big, 6_000, words=1000, coverage=sm.coverage(big))["after"]
    cut = sm.story_so_far(big, "manuscript/06-s6.md", cap_tokens=2_000)
    assert cut.dropped and wide != narrow
    assert f"about {scale._round(-(-len(cut.text) // sm.CHARS_PER_TOKEN)):,} tokens" in narrow
    assert scale.scale_hint(big, 4_600, words=1000, coverage=sm.coverage(big))["after"] is None     # nothing fits: no story at all


def test_after_is_not_given_while_the_notice_speaks_or_is_dismissed(tmp_path):
    words = int(4 * WINDOW / scale.WORDS_TO_TOKENS) + 1000
    assert hint(words, 100, summarised=10)["after"] is None                            # the strong notice speaks
    assert hint(words, 100, summarised=10, dismissed="strong")["after"] is None        # closed, coverage low: still quiet
    assert scale._round(0) == 0 and scale._round(4) == 10 and scale._round(5040) == 5000 and scale._round(530) == 530
