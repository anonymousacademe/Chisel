"""The tolerant quote rule (core.summaries.quote_check) and what verify reports about it.

Fixtures are real scenes and real model quotes from the diagnosis (tests/fixtures/quote_cases.json)."""
import json
from pathlib import Path

import pytest

from chisel.core import summaries as sm

CASES = json.loads((Path(__file__).parent / "fixtures" / "quote_cases.json").read_text(encoding="utf-8"))
ACCEPT = [c for c in CASES if c["cls"] in ("a_typography", "b_joined_with_ellipsis")]


@pytest.mark.parametrize("case", ACCEPT, ids=[f"{c['cls'][:1]}{c['id']}" for c in ACCEPT])
def test_diagnosed_quotes_are_accepted(case):
    assert sm.quote_found(case["scene"], case["quote"])


def test_the_paraphrase_is_rejected():
    case = next(c for c in CASES if c["cls"] == "c_paraphrase")
    assert not sm.quote_found(case["scene"], case["quote"])


def test_the_pronoun_swap_is_rejected():
    scene = ("Raskolnikov had time to put his hand into his pocket, to snatch up the coppers he had "
             "received in exchange for his rouble in the tavern and to lay them unnoticed on the window.")
    quote = "he had time to put his hand into his pocket, to snatch up the coppers ..."
    assert not sm.quote_found(scene, quote)
    # the same words with the name are fine
    assert sm.quote_found(scene, "Raskolnikov had time to put his hand into his pocket")


SCENE = ("The rain had not stopped for three days. Marmeladov—such is my name—paid thirty copecks.\n"
         "Elias drew a gun -- slowly -- and said nothing at all.")


def test_exact_and_whitespace_tests_are_unchanged():
    assert sm.quote_check(SCENE, "The rain had not stopped") == ("exact", "")
    assert sm.quote_check(SCENE, "paid thirty  copecks.\nElias") == ("exact", "")
    assert sm.quote_check(SCENE, "short") == ("", sm.NOT_IN_SCENE)


def test_typography_case_and_edge_punctuation_are_tolerated():
    assert sm.quote_check(SCENE, "marmeladov--such is my name--paid thirty copecks") == ("tolerant", "")
    assert sm.quote_check(SCENE, "Elias drew a gun — slowly — and said nothing") == ("tolerant", "")
    assert sm.quote_check(SCENE, '"The rain had not stopped for three days"!') == ("tolerant", "")
    assert sm.quote_check("It was Dounia’s own money, sadly.", "Dounia's own money.")[0] == "tolerant"


@pytest.mark.parametrize("bad", [
    "The rain had not stopped for four days",      # a number
    "Marmeladov paid thirty copecks",               # words missing in between
    "Elias drew a gun and said nothing at all",     # words missing in between
    "The rain had now stopped for three days",      # not -> now
    "Mara drew a gun slowly and said nothing",      # a name
])
def test_altered_quotes_are_rejected(bad):
    assert not sm.quote_found(SCENE, bad)


def test_ellipsis_pieces_must_be_in_order():
    ok = "The rain had not stopped ... Elias drew a gun"
    assert sm.quote_check(SCENE, ok)[0] == "tolerant"
    assert sm.quote_check(SCENE, "Elias drew a gun ... The rain had not stopped") == \
        ("", "the pieces of its quote are not in the scene in that order")
    assert sm.quote_found(SCENE, "The rain had not stopped … Elias drew a gun")
    assert sm.quote_found(SCENE, "The rain had not stopped [...] Elias drew a gun")


def test_pieces_do_not_overlap():
    assert not sm.quote_found("It was a long cold night.", "a long cold ... cold night")


def test_pieces_too_far_apart_are_rejected():
    far = "The rain had not stopped.\n" + "x " * 1100 + "\nElias drew a gun."
    assert "more than 2000 characters apart" in sm.quote_check(far, "The rain had not stopped ... Elias drew a gun")[1]
    near = "The rain had not stopped.\n" + "x " * 900 + "\nElias drew a gun."
    assert sm.quote_found(near, "The rain had not stopped ... Elias drew a gun")


def test_a_short_piece_is_rejected():
    assert sm.quote_check(SCENE, "The rain had not stopped ... Elias")[0] == ""
    assert "shorter than 8" in sm.quote_check(SCENE, "The rain had not stopped ... gun ... Elias drew a gun")[1]
    assert not sm.quote_found("Anna brought him some tea.", "Anna... brought him some tea")


def test_leading_and_trailing_ellipsis_only_trims_the_quote():
    assert sm.quote_check(SCENE, "...The rain had not stopped for three days...")[0] == "tolerant"
    assert sm.quote_check(SCENE, "...") == ("", sm.NOT_IN_SCENE)


def test_verify_says_which_rule_failed_and_counts_the_tolerant_facts():
    s = sm.Summary(summary="x", facts=(
        sm.Fact("Exact.", "The rain had not stopped for three days"),
        sm.Fact("Tolerant.", "The rain had not stopped ... Elias drew a gun"),
        sm.Fact("Order.", "Elias drew a gun ... The rain had not stopped"),
        sm.Fact("Invented.", "The sun shone on the whole town"),
    ))
    clean, dropped, tolerant = sm.verify_counted(s, SCENE)
    assert [f.text for f in clean.facts] == ["Exact.", "Tolerant."]
    assert tolerant == 1
    assert [(d.text, d.reason) for d in dropped] == [
        ("Order.", "the pieces of its quote are not in the scene in that order"),
        ("Invented.", "its quote is not in the scene")]
    assert sm.verify(s, SCENE)[1] == dropped
