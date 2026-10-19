"""Canon proposals with a quote per fact: schema, prompt, verification, and the newest-lines view of existing canon."""

import json
from unittest.mock import MagicMock

from chisel.ai import budget, continuity as cont
from chisel.ai.continuity import (
    ACCUMULATION_SCHEMA, ACCUMULATION_SYSTEM_PROMPT, CANON_CAP, CANON_KINDS, CanonProposal, CanonUpdate,
    left_out_sentence, parse_canon, parse_canon_updates, plan_canon, propose_canon, propose_canon_updates,
)
from chisel.core import entities as ent

SCENE = ("# Dinner\n\nLuzhin was forty-five and wore a copper cross on a cord. "
         "Dounia, who had black eyes, said nothing.\n\nThe lamp flickered; “It is late,” said Luzhin.\n")
LUZHIN = ent.Entity(name="Luzhin", type="character", aliases=["Pyotr"])
DOUNIA = ent.Entity(name="Dounia", type="character")
ENTS = [LUZHIN, DOUNIA]


def reply(*updates):
    return json.dumps({"updates": list(updates)})


def fact(text, quote, kind="other"):
    return {"fact": text, "quote": quote, "kind": kind}


def client_for(raw):
    msg = MagicMock()
    msg.content = raw
    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


# -- schema and prompt ------------------------------------------------------------------


def test_schema_asks_for_fact_quote_kind():
    item = ACCUMULATION_SCHEMA["properties"]["updates"]["items"]
    assert item["required"] == ["entity", "facts"]
    fact_schema = item["properties"]["facts"]["items"]
    assert fact_schema["required"] == ["fact", "quote", "kind"]
    assert fact_schema["additionalProperties"] is False
    assert fact_schema["properties"]["kind"]["enum"] == list(CANON_KINDS)
    assert CANON_KINDS == ("age", "appearance", "number", "duration", "possession", "place", "relationship",
                           "occupation", "habit", "other")


def test_prompt_is_short_and_has_the_key_phrases():
    assert len(ACCUMULATION_SYSTEM_PROMPT.split()) < 260
    p = ACCUMULATION_SYSTEM_PROMPT
    for phrase in ("stable details first", "ages", "appearance", "possessions", "habits", "ONE unbroken passage",
                   "exactly as written", "no ellipsis", "no pronoun in place of a name", "cannot quote",
                   "never restate", "only add", "ONE entity", "is forty-five", "omit that entity"):
        assert phrase.lower() in p.lower(), phrase
    assert "evidence" not in p and "paraphrase" not in p


# -- parsing and verification -----------------------------------------------------------


def test_new_shape_parses_with_quotes_and_kinds_in_order():
    raw = reply({"entity": "Luzhin", "facts": [
        fact("is forty-five", "Luzhin was forty-five", "age"),
        fact("wears a copper cross", "wore a copper cross on a cord", "possession")]})
    (u,) = parse_canon_updates(raw, ENTS, SCENE)
    assert u.entity == "Luzhin"
    assert u.new_facts == ("is forty-five", "wears a copper cross")
    assert u.quotes == ("Luzhin was forty-five", "wore a copper cross on a cord")
    assert u.kinds == ("age", "possession")
    assert u.evidence == "Luzhin was forty-five / wore a copper cross on a cord"


def test_exact_quote_is_kept_and_not_counted_tolerant():
    p = parse_canon(reply({"entity": "Dounia", "facts": [fact("has black eyes", "who had black eyes", "appearance")]}),
                    ENTS, SCENE)
    assert isinstance(p, CanonProposal)
    assert [u.new_facts for u in p.updates] == [("has black eyes",)]
    assert p.dropped == () and p.tolerant == 0 and p.left_out == ""


def test_tolerant_quote_is_kept_and_counted():
    q = '"it is late," said luzhin'          # straight quotes and case differ from the scene
    p = parse_canon(reply({"entity": "Luzhin", "facts": [fact("keeps late hours", q, "habit")]}), ENTS, SCENE)
    assert [u.new_facts for u in p.updates] == [("keeps late hours",)]
    assert p.tolerant == 1 and p.dropped == ()


def test_missing_quote_is_dropped_and_listed():
    p = parse_canon(reply({"entity": "Luzhin", "facts": [fact("is forty-five", "", "age")]}), ENTS, SCENE)
    assert p.updates == []
    assert [(d.entity, d.fact, d.reason) for d in p.dropped] == [("Luzhin", "is forty-five", "it has no quote")]


def test_quote_not_in_scene_is_dropped_and_listed():
    p = parse_canon(reply({"entity": "Luzhin", "facts": [fact("is forty-five", "he was forty-five years old", "age")]}),
                    ENTS, SCENE)
    assert p.updates == []
    assert [(d.entity, d.reason) for d in p.dropped] == [("Luzhin", "its quote is not in the scene")]


def test_two_facts_one_bad_quote_keeps_one_drops_one():
    raw = reply({"entity": "Luzhin", "facts": [
        fact("is forty-five", "Luzhin was forty-five", "age"),
        fact("owns a horse", "a grey horse stood outside", "possession")]})
    p = parse_canon(raw, ENTS, SCENE)
    (u,) = p.updates
    assert (u.new_facts, u.quotes) == (("is forty-five",), ("Luzhin was forty-five",))
    assert [d.fact for d in p.dropped] == ["owns a horse"]
    assert "1 proposed fact was left out" in p.left_out


def test_quotes_are_checked_against_prose_not_the_details_block():
    scene = "---\npov: Luzhin\nplace: the cellar\n---\n# T\n\nHe sat down.\n"
    raw = reply({"entity": "Luzhin", "facts": [
        fact("lives in the cellar", "place: the cellar", "place"),
        fact("sits down", "He sat down.", "habit")]})
    p = parse_canon(raw, ENTS, scene)
    assert [u.new_facts for u in p.updates] == [("sits down",)]
    assert [d.fact for d in p.dropped] == ["lives in the cellar"]


def test_old_shape_with_scene_text_is_all_dropped_for_having_no_quote():
    raw = json.dumps({"updates": [{"entity": "Luzhin", "new_facts": ["is forty-five", "wears a cross"],
                                   "evidence": "Luzhin was forty-five"}]})
    p = parse_canon(raw, ENTS, SCENE)
    assert p.updates == []
    assert [d.reason for d in p.dropped] == ["it has no quote", "it has no quote"]
    assert propose_canon(SCENE, ENTS, "m", client=client_for(raw)).updates == []


def test_old_shape_without_scene_text_is_parsed_only():
    raw = json.dumps({"updates": [{"entity": "Luzhin", "new_facts": ["is forty-five"], "evidence": "why"}]})
    (u,) = parse_canon_updates(raw, ENTS)
    assert (u.new_facts, u.evidence, u.quotes, u.kinds) == (("is forty-five",), "why", (), ())
    (u,) = parse_canon_updates(raw)
    assert u.new_facts == ("is forty-five",)


def test_new_shape_without_scene_text_is_not_verified():
    raw = reply({"entity": "Luzhin", "facts": [fact("owns a horse", "never in the scene", "possession")]})
    (u,) = parse_canon_updates(raw, ENTS)
    assert u.quotes == ("never in the scene",)


def test_kind_is_optional_and_unknown_becomes_other():
    raw = reply({"entity": "Luzhin", "facts": [
        {"fact": "is forty-five", "quote": "Luzhin was forty-five"},
        fact("wears a copper cross", "wore a copper cross on a cord", "jewellery")]})
    (u,) = parse_canon_updates(raw, ENTS, SCENE)
    assert u.kinds == ("other", "other")


def test_existing_canon_dedupe_still_applies_and_alias_is_canonical():
    luzhin = ent.Entity(name="Luzhin", aliases=["Pyotr"], body="## Canon (auto)\n\n- is forty-five\n")
    raw = reply({"entity": "pyotr", "facts": [
        fact("Is forty-five.", "Luzhin was forty-five", "age"),
        fact("wears a copper cross", "wore a copper cross on a cord", "possession")]})
    p = parse_canon(raw, [luzhin], SCENE)
    (u,) = p.updates
    assert u.entity == "Luzhin" and u.new_facts == ("wears a copper cross",)
    assert "is forty-five" in u.existing_canon
    assert p.dropped == ()                       # a duplicate is not a verification failure


def test_select_keeps_quotes_and_kinds_in_step():
    u = CanonUpdate("L", ("a", "b", "c"), "qa / qb / qc", "", ("qa", "qb", "qc"), ("age", "place", "other"))
    s = u.select([0, 2])
    assert (s.new_facts, s.quotes, s.kinds, s.evidence) == (("a", "c"), ("qa", "qc"), ("age", "other"), "qa / qc")
    old = CanonUpdate("L", ("a", "b"), "why")
    assert old.select([1]).new_facts == ("b",) and old.select([1]).evidence == "why"


def test_left_out_sentence_names_count_and_top_reason():
    assert left_out_sentence(()) == ""
    d = [cont.CanonDropped("L", f"f{i}", "its quote is not in the scene") for i in range(3)]
    assert left_out_sentence(d) == "3 proposed facts were left out because the passage it quoted is not in the scene."
    d.append(cont.CanonDropped("L", "g", "it has no quote"))
    assert left_out_sentence(d).endswith("scene; the others for other reasons.")


def test_propose_canon_sends_the_new_schema_and_returns_a_proposal():
    raw = reply({"entity": "Luzhin", "facts": [fact("is forty-five", "Luzhin was forty-five", "age")]})
    client = client_for(raw)
    result = propose_canon(SCENE, ENTS, "m/x", client=client)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"]["json_schema"]["schema"] is ACCUMULATION_SCHEMA
    assert kwargs["messages"][0]["content"] == ACCUMULATION_SYSTEM_PROMPT
    assert result.updates[0].quotes == ("Luzhin was forty-five",)
    assert propose_canon_updates(SCENE, ENTS, "m/x", client=client_for(raw)) == result.updates


# -- the proposer's view of existing canon: newest lines ----------------------------------


def _long(n=120):
    lines = [f"- line {i:03d} " + "y" * 25 for i in range(n)]
    return ent.Entity(name="Luzhin", type="character", body="## Canon (auto)\n\n" + "\n".join(lines) + "\n")


def test_trim_tail_keeps_the_newest_whole_lines():
    text = "\n".join(f"line {i:02d}" for i in range(30))
    out = budget.trim_tail(text, 60)
    assert len(out) <= 60 and out.startswith("…\n") and out.endswith("line 29")
    assert all(ln.startswith("line ") for ln in out.splitlines()[1:])
    assert budget.trim_tail(text, 10 ** 6) == text and budget.trim_tail(text, 0) == ""
    assert budget.trim_tail("x" * 100, 20) == "…\n" + "x" * 18


def test_proposer_sees_newest_canon_lines_and_the_report_names_the_cut():
    e = _long()
    assert len(cont.get_canon(e.body)) > CANON_CAP
    ents, report = plan_canon(SCENE, [e], budget.Budget(32_000))
    row = next(r for r in report.sections if r.name == "Entity notes")
    assert row.truncated == ("Luzhin",)           # named, not silent
    client = client_for('{"updates": []}')
    propose_canon_updates(SCENE, ents, "m", client=client)
    user = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "line 119" in user and "line 000" not in user
    assert len(user.split("existing canon:\n")[1].split("\n\nSCENE")[0]) <= CANON_CAP


def test_short_canon_is_sent_unchanged():
    e = ent.Entity(name="Luzhin", type="character", body="## Canon (auto)\n\n- a\n- b\n")
    ents, report = plan_canon(SCENE, [e], budget.Budget(32_000))
    assert ents[0] is e
    assert not next(r for r in report.sections if r.name == "Entity notes").truncated


def test_dedupe_uses_the_full_canon_even_when_the_view_is_cut():
    e = _long()
    raw = reply({"entity": "Luzhin", "facts": [fact("line 000 yyyyyyyyyyyyyyyyyyyyyyyyy", "Luzhin was forty-five")]})
    assert parse_canon(raw, [e], SCENE).updates == []
