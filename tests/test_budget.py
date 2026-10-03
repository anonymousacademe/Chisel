"""ai/budget.py: token estimates, windows, fitting sections into a window, the sent report."""

import json

import pytest

from lorewrite.ai import budget as B
from lorewrite.ai.budget import (
    Budget, BudgetError, Item, Section, estimate_tokens, fit, fit_text, merge_attached, preflight, render, trim,
    validate_window, window_for,
)
from lorewrite.ai.client import ModelInfo, cached_context_length, remember_context_lengths


def budget_of(chars: int, reserve_chars: int = 0) -> Budget:
    """A budget whose request room is *chars* characters (4 chars per estimated token)."""
    return Budget(chars // 4 + reserve_chars // 4, reserve_chars // 4)


def by_name(report, name):
    return next(s for s in report.sections if s.name == name)


# -- estimate_tokens ----------------------------------------------------------------


def test_estimate_tokens_is_chars_over_four_rounded_up():
    assert estimate_tokens("") == 0 and estimate_tokens(None) == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("x" * 4000) == 1000


# -- windows ------------------------------------------------------------------------


def test_window_for_uses_the_catalogue_then_the_default():
    models = [ModelInfo("a/big", "Big", 1.0, 2.0, 200_000), ModelInfo("a/odd", "Odd", None, None, None)]
    assert window_for("a/big", models, {}) == 200_000
    assert window_for("a/big", {"a/big": 128_000}, {}) == 128_000          # a mapping works too
    assert window_for("a/odd", models, {}) == B.DEFAULT_WINDOW             # no context length known
    assert window_for("a/unknown", models, {}) == B.DEFAULT_WINDOW
    assert window_for("a/big", {"a/big": "garbage"}, {}) == B.DEFAULT_WINDOW
    assert window_for("a/big", {"a/big": 12}, {}) == B.DEFAULT_WINDOW      # absurdly small: not trusted


def test_window_for_without_a_catalogue_reads_the_remembered_lengths_never_the_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the budget must never fetch the catalogue")

    monkeypatch.setattr("lorewrite.ai.client.list_models", boom)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert cached_context_length("m/x") is None
    assert window_for("m/x", settings={}) == B.DEFAULT_WINDOW
    remember_context_lengths([ModelInfo("m/x", "X", None, None, 64_000), ModelInfo("m/y", "Y", None, None, None)])
    assert cached_context_length("m/x") == 64_000 and cached_context_length("m/y") is None
    assert window_for("m/x", settings={}) == 64_000
    remember_context_lengths([ModelInfo("m/z", "Z", None, None, 8_000)])      # earlier entries are kept
    assert cached_context_length("m/x") == 64_000 and cached_context_length("m/z") == 8_000


def test_window_setting_overrides_and_invalid_values_are_ignored():
    models = {"a/big": 200_000}
    assert window_for("a/big", models, {"context_window": 16_000}) == 16_000
    assert window_for("a/none", models, {"context_window": "48000"}) == 48_000
    for bad in (True, 12, -5, 10 ** 9, "lots", 3.5, [], {}):
        assert window_for("a/big", models, {"context_window": bad}) == 200_000
    assert window_for("a/big", models, {"context_window": ""}) == 200_000


def test_validate_window_rejects_what_is_not_a_sensible_size():
    assert validate_window(32_000) == 32_000 and validate_window("32,000") == 32_000
    for bad in (None, True, 0, 1999, 10_000_001, "abc", "", 2.5, [1]):
        with pytest.raises(ValueError):
            validate_window(bad)


def test_budget_available_is_window_minus_reserve():
    assert Budget(10_000, 4_000).available == 6_000
    assert Budget(1_000, 4_000).available == 0
    assert Budget.for_model("m/none", {}, {}).window_tokens == B.DEFAULT_WINDOW


# -- trim ---------------------------------------------------------------------------


def test_trim_cuts_at_a_sentence_then_a_word_never_inside_a_word():
    text = "The first sentence ends here. The second sentence runs on and on until it is far too long to keep."
    cut = trim(text, 60)
    assert cut == "The first sentence ends here.…" and len(cut) <= 60
    words = " ".join(f"word{i}" for i in range(200))
    cut = trim(words, 100)
    assert len(cut) <= 100 and cut.endswith("…")
    assert words[len(cut) - 1] == " "                      # the cut fell on a space
    assert cut[:-1].split(" ")[-1] in words.split(" ")     # the last word is whole
    lines = "\n".join(f"- fact number {i}" for i in range(100))
    cut = trim(lines, 120)
    assert cut.endswith("…") and "\n" in cut and not cut[:-1].endswith(" ")
    assert trim("short", 100) == "short" and trim("anything", 0) == ""


def test_trim_hard_cuts_only_one_unbroken_word():
    assert trim("x" * 500, 100) == "x" * 100


# -- fit: order, caps, reports ------------------------------------------------------


def test_fit_keeps_fixed_sections_then_droppable_ones_in_priority_order():
    fixed = Section("Scene", "S" * 100)
    low = Section("Low", "L" * 400, priority=2, droppable=True)
    high = Section("High", "H" * 400, priority=1, droppable=True)
    fitted, rep = fit([low, fixed, high], budget_of(520))           # fits Scene + one of the others
    assert [s.name for s in fitted] == ["Low", "Scene", "High"]      # input order is kept
    assert by_name(rep, "High").omitted is False and by_name(rep, "Low").omitted is True
    assert by_name(rep, "Low").items_dropped == ("Low",)
    assert "L" not in render(fitted) and "H" * 400 in render(fitted) and "S" * 100 in render(fitted)
    assert not rep.over_budget and rep.trimmed
    fitted, rep = fit([low, fixed, high], budget_of(2000))
    assert not rep.trimmed and render(fitted).count("L") == 400


def test_fit_fills_a_list_item_by_item_and_trims_one_item_last():
    sentences = " ".join(f"This is sentence number {i} of the note." for i in range(40))
    items = tuple(Item(f"E{i}", sentences if i == 2 else "short note " * 5, f"### E{i}", priority=i) for i in range(6))
    sec = Section("Notes", droppable=True, items=items, head="NOTES:\n")
    fixed = Section("Scene", "S" * 200)
    fitted, rep = fit([sec, fixed], budget_of(900))
    r = by_name(rep, "Notes")
    assert r.items_total == 6 and r.items_sent == 3                  # E0, E1 whole; E2 trimmed; the rest dropped
    assert r.truncated == ("E2",) and r.items_dropped == ("E3", "E4", "E5")
    text = render(fitted)
    assert "### E0" in text and "### E2" in text and "### E3" not in text
    e2 = text.split("### E2\n")[1].split("\n\n")[0]
    assert e2.endswith("…") and e2[:-1].endswith(".")               # at a sentence end, not mid-word
    assert estimate_tokens(text) <= 900 // 4


def test_fit_drops_an_item_rather_than_trim_it_to_a_stub():
    items = tuple(Item(f"E{i}", "word " * 100, f"### E{i}", priority=i) for i in range(3))
    sec = Section("Notes", droppable=True, items=items, head="N:\n")
    _, rep = fit([sec], budget_of(560))                              # room for one note + a sliver
    r = by_name(rep, "Notes")
    assert r.items_sent == 1 and r.truncated == () and r.items_dropped == ("E1", "E2")


def test_fit_applies_item_cap_group_cap_and_max_priority_and_reports_them():
    items = (Item("A", "a" * 50, priority=0, cap=20),
             Item("B", "b " * 40, priority=1),
             Item("C", "c" * 30, priority=2),
             Item("D", "d" * 10, priority=9))
    sec = Section("Notes", droppable=True, items=items, group_cap=60, max_priority=5)
    fitted, rep = fit([sec], Budget.unbounded())
    r = by_name(rep, "Notes")
    assert r.truncated == ("A",)                      # over its fixed cap
    assert r.items_dropped == ("B", "D")              # B: 20 + 79 > 60 (group cap); D: priority above the limit
    assert r.items_sent == 2                          # A (cut to its cap) and C still fit under the group cap
    assert "ddd" not in render(fitted) and "bb" not in render(fitted) and "c" * 30 in render(fitted)


def test_fit_group_cap_skips_what_does_not_fit_and_keeps_going_like_the_old_loop():
    items = tuple(Item(n, "x" * size, priority=i) for i, (n, size) in enumerate([("A", 40), ("B", 40), ("C", 10)]))
    _, rep = fit([Section("N", droppable=True, items=items, group_cap=55)], Budget.unbounded())
    r = by_name(rep, "N")
    assert r.items_dropped == ("B",) and r.items_sent == 2


def test_nothing_is_dropped_or_trimmed_without_being_named_in_the_report():
    items = tuple(Item(f"Name{i}", f"note {i} " * 60, f"### Name{i}", priority=(7 * i) % 13, cap=250) for i in range(30))
    fitted, rep = fit([Section("Notes", droppable=True, items=items, group_cap=5000, max_priority=11),
                       Section("Scene", "S" * 300)], budget_of(2400))
    kept = {it.name for s in fitted for it in (s.items or ())}
    r = by_name(rep, "Notes")
    assert kept | set(r.items_dropped) == {f"Name{i}" for i in range(30)}
    assert not kept & set(r.items_dropped)
    sent_text = render(fitted)
    for name in r.items_dropped:
        assert f"### {name}\n" not in sent_text
    for name in kept:
        assert f"### {name}\n" in sent_text
    assert set(r.truncated) <= kept


def test_fit_is_deterministic():
    def build():
        items = tuple(Item(f"E{i}", f"fact {i}. " * (10 + i), f"### E{i}", priority=(i * 5) % 7) for i in range(25))
        return [Section("Notes", droppable=True, items=items, head="N:\n"), Section("Scene", "S" * 500),
                Section("Style", "style " * 100, priority=1, droppable=True)]

    a_fit, a_rep = fit(build(), budget_of(1500))
    b_fit, b_rep = fit(build(), budget_of(1500))
    assert render(a_fit) == render(b_fit) and a_rep == b_rep


def test_fit_empty_and_empty_list_sections():
    fitted, rep = fit([], Budget(32_000))
    assert fitted == [] and rep.sections == () and rep.est_tokens == 0 and not rep.trimmed
    fitted, rep = fit([Section("Notes", droppable=True, items=(), head="N:\n"), Section("Gap", "")], Budget(32_000))
    assert render(fitted) == "" and rep.est_tokens == 0 and not rep.trimmed


def test_hidden_sections_count_toward_the_size_but_not_the_text():
    hidden = Section("Instructions and question", "I" * 400, visible=False)
    fitted, rep = fit([hidden, Section("Scene", "S" * 100)], Budget(32_000))
    assert render(fitted) == "S" * 100
    assert rep.est_tokens == estimate_tokens("I" * 400 + "S" * 100 + "xx")


# -- over the window ------------------------------------------------------------------


def test_fixed_sections_over_the_window_is_over_budget_and_preflight_raises_an_actionable_error():
    sections = [Section("Scene", "S" * 40_000), Section("Attachments", "A" * 20_000),
                Section("Notes", "N" * 400, droppable=True)]
    fitted, rep = fit(sections, Budget(8_000, 2_000))
    assert rep.over_budget and by_name(rep, "Notes").omitted
    with pytest.raises(BudgetError) as err:
        preflight(rep)
    msg = str(err.value)
    assert isinstance(err.value, ValueError)
    assert "context window" in msg and "15k" in msg and "8k" in msg      # how big vs the window
    assert "Scene" in msg and "Attachments" in msg                        # what is too big
    assert "bigger context window" in msg and "shorten the scene" in msg and "remove attachments" in msg
    with pytest.raises(BudgetError):
        fit_text(sections, Budget(8_000, 2_000), "ask")
    assert fit_text([Section("Scene", "S" * 100)], Budget(8_000, 2_000))[0] == "S" * 100


def test_the_error_says_when_the_window_is_only_a_default():
    rep = fit([Section("Scene", "S" * 200_000)], Budget(B.DEFAULT_WINDOW, 4000))[1]
    with pytest.raises(BudgetError, match="not known yet"):
        preflight(rep)


# -- the report ------------------------------------------------------------------------


def test_report_to_dict_is_plain_json_and_summarises():
    items = tuple(Item(f"E{i}", "note " * 80, f"### E{i}", priority=i) for i in range(5))
    _, rep = fit([Section("Notes", droppable=True, items=items), Section("Scene", "S" * 100)], budget_of(1100))
    d = rep.to_dict()
    json.dumps(d)
    assert set(d) == {"feature", "estTokens", "window", "reserve", "overBudget", "trimmed", "sections", "attached"}
    notes = next(s for s in d["sections"] if s["name"] == "Notes")
    assert set(notes) == {"name", "chars", "estTokens", "itemsTotal", "itemsSent", "itemsDropped", "truncated", "omitted"}
    assert d["trimmed"] is True and notes["itemsDropped"]
    assert "dropped" in rep.summary() and rep.summary().startswith("sent ~")
    assert B.fmt_tokens(3200) == "3.2k" and B.fmt_tokens(200_000) == "200k" and B.fmt_tokens(950) == "950"


def test_merge_attached_folds_the_attachment_report_in_without_duplicating_it():
    _, rep = fit([Section("Scene", "S" * 100), Section("Attachments", "A" * 80)], Budget(32_000))
    rows = [{"kind": "scene", "id": "a.md", "title": "A", "chars": 80, "truncated": True, "skipped": False},
            {"kind": "note", "id": "b.md", "title": "B", "chars": 0, "truncated": False, "skipped": True, "reason": "empty"}]
    merged = merge_attached(rep, rows)
    att = by_name(merged, "Attachments")
    assert att.items_total == 2 and att.items_sent == 1 and att.items_dropped == ("B",) and att.truncated == ("A",)
    assert [s.name for s in merged.sections].count("Attachments") == 1
    assert merged.attached[0]["id"] == "a.md" and merged.to_dict()["attached"][1]["reason"] == "empty"
    assert merge_attached(rep, []) is rep
    only_skipped = merge_attached(fit([Section("Scene", "S")], Budget(32_000))[1], rows[1:])
    assert by_name(only_skipped, "Attachments").items_dropped == ("B",)
