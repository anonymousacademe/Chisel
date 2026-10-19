"""ai/summaries: plan before the network, tolerant parse, verified proposals, streaming and Stop. Fakes only."""

import json
from types import SimpleNamespace

import pytest

from chisel.ai import client as ai_client
from chisel.ai import summaries as ais
from chisel.ai.budget import Budget, BudgetError
from chisel.ai.stream import Cancelled, CancelToken
from chisel.ai.usage import LEDGER
from chisel.core import scenemeta
from chisel.core import summaries as sm
from chisel.core.entities import Entity

SCENE = ("# Arrival\n\nMara stepped off the tram into Lower Meridian. The rain had not\n"
         "stopped for three days. Elias was waiting under the clock.\n")

GOOD = {"summary": "Mara arrived in Lower Meridian and met Elias.",
        "characters": [{"name": "Mara", "state": "at the tram stop"}, {"name": "Rook", "state": "unknown"}],
        "facts": [{"text": "It had rained for days.", "quote": "The rain had not stopped for three days"},
                  {"text": "Elias had a gun.", "quote": "Elias drew a gun"}],
        "threads": ["Why is Elias waiting?"]}


@pytest.fixture(autouse=True)
def clean_ledger():
    LEDGER.clear()
    yield
    LEDGER.clear()


class FakeStream:
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    def __iter__(self):
        return iter(self.chunks)

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, reply, cost=0.01):
        self.reply, self.cost, self.kwargs = reply, cost, None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.kwargs = kw
        usage = SimpleNamespace(cost=self.cost, prompt_tokens=1, completion_tokens=1)
        if kw.get("stream"):
            parts = [self.reply[i:i + 7] for i in range(0, len(self.reply), 7)]
            chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=p))], usage=None)
                      for p in parts]
            return FakeStream(chunks + [SimpleNamespace(choices=[], usage=usage)])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
                               usage=usage)


def entities():
    return [Entity(name="Mara Vale", aliases=["Mara"]), Entity(name="Elias Vale", aliases=["Elias"]),
            Entity(name="Unrelated Person")]


# -- plan ------------------------------------------------------------------------------


def test_plan_sends_only_the_names_the_scene_is_about():
    ents, report = ais.plan_summarize(SCENE, entities(), Budget(32_000))
    assert [e.name for e in ents] == ["Mara Vale", "Elias Vale"]
    assert [s.name for s in report.sections] == ["Instructions and question", "Known names", "Scene"]
    assert not report.dropped
    prompt = ais.build_prompt(SCENE, ents)
    assert prompt.startswith("KNOWN NAMES:\n- Mara Vale (character), also written: Mara") and "Unrelated" not in prompt
    assert prompt.endswith("SCENE:\n" + SCENE)


def test_plan_strips_details_and_refuses_before_any_call_when_the_scene_is_too_big():
    text = scenemeta.set_details(SCENE, status="draft", purpose="secret plan")
    assert "secret plan" not in ais.build_prompt(text, [])
    with pytest.raises(BudgetError):
        ais.plan_summarize(SCENE * 2_000, entities(), Budget(4_000, 1_000))


def test_plan_reports_names_dropped_for_room():
    many = [Entity(name=f"Person {i}", aliases=[]) for i in range(60)]
    text = SCENE + " ".join(f"Person {i}" for i in range(60))
    _, report = ais.plan_summarize(text, many, Budget(1_700, 1_000))
    known = next(s for s in report.sections if s.name == "Known names")
    assert known.items_dropped and set(known.items_dropped) <= {f"Person {i}" for i in range(60)}


# -- parsing ---------------------------------------------------------------------------


def test_parse_is_tolerant():
    raw = json.dumps(GOOD)
    assert ais.parse_summary(raw).summary.startswith("Mara arrived")
    assert ais.parse_summary("```json\n" + raw + "\n```").facts[0].quote.startswith("The rain")
    assert ais.parse_summary("Here you go: " + raw + " Hope it helps!").threads == ("Why is Elias waiting?",)
    only = ais.parse_summary('{"summary": "Short."}')
    assert only.summary == "Short." and only.facts == () and only.characters == ()
    messy = ais.parse_summary(json.dumps({"summary": "S.", "characters": ["x", {"name": ""}, {"name": "A"}],
                                          "facts": [{"text": "t"}, 3], "threads": [1, " a "]}))
    assert [c.name for c in messy.characters] == ["A"] and [f.text for f in messy.facts] == ["t"]
    assert messy.threads == ("a",)
    for bad in ("", "no json here", "[1, 2]", '{"summary": ""}', '{"summary": 5', None):
        assert ais.parse_summary(bad) is None


def test_overlong_summary_is_cut_at_a_sentence_end_never_in_the_middle():
    sentences = [f"Sentence number {i} says something plain." for i in range(30)]       # 6 words each
    s, trimmed = ais.parse_summary_flagged(json.dumps({"summary": " ".join(sentences)}))
    assert trimmed is True and s.summary.endswith("plain.") and "…" not in s.summary
    assert len(s.summary.split()) <= sm.SUMMARY_WORDS and len(s.summary.split()) % 6 == 0
    assert s.summary == " ".join(sentences[:len(s.summary.split()) // 6])


def test_overlong_text_without_a_sentence_end_is_cut_at_a_word_and_flagged():
    s, trimmed = ais.parse_summary_flagged(json.dumps({"summary": "word " * 200}))
    assert trimmed is True and len(s.summary.split()) == sm.SUMMARY_WORDS and "…" not in s.summary
    text, cut = ais._clip("A long one, with a comma, " * 40)
    assert cut and not text.endswith(",") and len(text.split()) <= sm.SUMMARY_WORDS


def test_a_summary_within_the_cap_is_untouched_and_not_flagged():
    s, trimmed = ais.parse_summary_flagged(json.dumps({"summary": "Mara left. Elias stayed."}))
    assert s.summary == "Mara left. Elias stayed." and trimmed is False
    assert ais._clip("  " + "w " * sm.SUMMARY_WORDS) == (("w " * sm.SUMMARY_WORDS).strip(), False)
    assert ais.parse_summary_flagged("nothing") == (None, False)


def test_the_prompt_asks_for_fewer_words_than_the_cap():
    assert f"at most {ais.ASK_WORDS} words" in ais.SYSTEM_PROMPT and ais.ASK_WORDS < sm.SUMMARY_WORDS
    assert f"at most {sm.SUMMARY_WORDS} words" not in ais.SYSTEM_PROMPT


def test_a_proposal_carries_the_trimmed_flag():
    long = dict(GOOD, summary=" ".join(f"Sentence {i} is here and plain enough." for i in range(40)))
    out = ais.summarize_scene(SCENE, entities(), "m/x", client=FakeClient(json.dumps(long)))
    assert out.trimmed is True and out.summary.summary.endswith("enough.")
    assert ais.summarize_scene(SCENE, entities(), "m/x", client=FakeClient(json.dumps(GOOD))).trimmed is False


def test_a_part_summary_is_capped_at_150_words_by_sentence_and_says_when():
    part = json.dumps({"summary": " ".join(f"Part sentence {i} goes on." for i in range(60)),
                       "characters": [], "threads": []})
    out = ais.summarize_part("Part", scene_summaries(2), "m/x", client=FakeClient(part))
    assert out.trimmed is True and out.summary.endswith("on.") and 90 < len(out.summary.split()) <= sm.PART_SUMMARY_WORDS
    assert "trimmed" not in out.as_dict()
    short = json.dumps({"summary": "Short part.", "characters": [], "threads": []})
    assert ais.summarize_part("Part", scene_summaries(2), "m/x", client=FakeClient(short)).trimmed is False


# -- summarize_scene --------------------------------------------------------------------


def test_summarize_scene_returns_a_verified_proposal():
    client = FakeClient(json.dumps(GOOD), cost=0.0123)
    out = ais.summarize_scene(SCENE, entities(), "m/writer", client=client)
    s = out.summary
    assert [f.text for f in s.facts] == ["It had rained for days."]
    assert [c.name for c in s.characters] == ["Mara"]
    assert [(d.kind, d.text) for d in out.dropped] == [("fact", "Elias had a gun."), ("character", "Rook")]
    assert s.source_hash == sm.hash_of(SCENE) and s.model == "m/writer" and s.cost == pytest.approx(0.0123)
    assert not s.author_edited and not s.locked and s.created
    # plain request: no structured-output demands, no provider.require_parameters
    kw = client.kwargs
    assert "response_format" not in kw and "require_parameters" not in json.dumps(kw["extra_body"])
    assert kw["messages"][0]["content"] == ais.SYSTEM_PROMPT
    assert "SCENE:\n" + SCENE.strip() in kw["messages"][1]["content"]
    assert LEDGER.count() == 1


def test_pending_ai_text_and_details_are_not_sent_and_not_hashed():
    text = scenemeta.set_details(SCENE, pov="Mara") + "<!--ai-->Mara shot Elias.<!--/ai-->\n"
    client = FakeClient(json.dumps(GOOD))
    out = ais.summarize_scene(text, entities(), "m/x", client=client)
    assert "shot Elias" not in client.kwargs["messages"][1]["content"]
    assert "pov: Mara" not in client.kwargs["messages"][1]["content"]
    assert out.summary.source_hash == sm.hash_of(SCENE)


def test_unusable_reply_is_a_clear_error_and_nothing_is_returned():
    with pytest.raises(ValueError, match="did not contain a summary"):
        ais.summarize_scene(SCENE, [], "m/x", client=FakeClient("sorry, no"))


def test_streaming_passes_deltas_and_reads_the_cost():
    seen = []
    client = FakeClient(json.dumps(GOOD), cost=0.05)
    out = ais.summarize_scene(SCENE, [], "m/x", client=client, on_delta=seen.append)
    assert "".join(seen) == json.dumps(GOOD) and client.kwargs["stream"] is True
    assert out.summary.cost == pytest.approx(0.05)


def test_stop_before_the_call_raises_and_returns_nothing():
    token = CancelToken()
    token.set()
    client = FakeClient(json.dumps(GOOD))
    with pytest.raises(Cancelled):
        ais.summarize_scene(SCENE, [], "m/x", client=client, cancel=token)
    assert client.kwargs is None


def test_stop_during_the_stream_raises():
    token = CancelToken()
    client = FakeClient(json.dumps(GOOD))
    with pytest.raises(Cancelled):
        ais.summarize_scene(SCENE, [], "m/x", client=client, on_delta=lambda d: token.set(), cancel=token)


class SequenceClient(FakeClient):
    """Answers with each reply in turn (the last one repeats)."""
    def __init__(self, *replies, cost=0.01):
        super().__init__("", cost)
        self.replies, self.calls = list(replies), 0

    def _create(self, **kw):
        self.reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        out = super()._create(**kw)
        if not kw.get("stream"):
            out.choices[0].finish_reason = "length"
        return out


def test_prompt_asks_for_one_unbroken_passage():
    assert "ONE unbroken passage copied exactly as written" in ais.SYSTEM_PROMPT
    assert 'Never join two passages with "..."' in ais.SYSTEM_PROMPT


def test_proposal_counts_facts_that_needed_the_tolerant_rule():
    reply = dict(GOOD, facts=[{"text": "a", "quote": "The rain had not stopped for three days"},
                              {"text": "b", "quote": "Mara stepped off the tram ... Elias was waiting"}])
    out = ais.summarize_scene(SCENE, [], "m/x", client=FakeClient(json.dumps(reply)))
    assert len(out.summary.facts) == 2 and out.tolerant == 1
    assert "tolerant" not in out.summary.as_dict()


def test_an_empty_reply_is_asked_for_once_more_and_both_costs_count(monkeypatch):
    logged = []
    monkeypatch.setattr(ais.applog, "log_exc", lambda ctx, exc=None, **kw: logged.append(ctx))
    client = SequenceClient("", json.dumps(GOOD), cost=0.02)
    out = ais.summarize_scene(SCENE, [], "m/x", client=client)
    assert client.calls == 2 and out.summary.summary.startswith("Mara arrived")
    assert out.summary.cost == pytest.approx(0.04) and LEDGER.count() == 2
    assert len(logged) == 1
    assert "step=empty reply" in logged[0] and "finish_reason=length" in logged[0]
    assert "completion_tokens=1" in logged[0] and "reply_chars=0" in logged[0]


def test_two_bad_replies_raise_the_same_error_and_log_each(monkeypatch):
    logged = []
    monkeypatch.setattr(ais.applog, "log_exc", lambda ctx, exc=None, **kw: logged.append(ctx))
    client = SequenceClient("sorry, no", '{"summary": ""}')
    with pytest.raises(ValueError, match="did not contain a summary"):
        ais.summarize_scene(SCENE, [], "m/x", client=client)
    assert client.calls == 2
    assert "step=no JSON object" in logged[0] and "step=no usable summary" in logged[1]
    assert not any("sorry" in line for line in logged)


def test_a_good_first_reply_is_not_retried():
    client = SequenceClient(json.dumps(GOOD))
    ais.summarize_scene(SCENE, [], "m/x", client=client)
    assert client.calls == 1


def test_stop_is_never_retried():
    token = CancelToken()
    token.set()
    client = SequenceClient("", json.dumps(GOOD))
    with pytest.raises(Cancelled):
        ais.summarize_scene(SCENE, [], "m/x", client=client, cancel=token)
    assert client.calls == 0
    token2 = CancelToken()
    client = SequenceClient("not json at all", json.dumps(GOOD))
    with pytest.raises(Cancelled):
        ais.summarize_scene(SCENE, [], "m/x", client=client, on_delta=lambda d: token2.set(), cancel=token2)
    assert client.calls == 1


# -- parts ------------------------------------------------------------------------------


def scene_summaries(n, words=5):
    return [(f"Scene {i}", sm.Summary("h", f"Event {i}. " + "w " * words,
                                      (sm.Character("Mara", f"state {i}"),), threads=("open",)))
            for i in range(n)]


def test_part_plan_drops_the_latest_scenes_by_name():
    scenes = scene_summaries(10, words=150)
    kept, report = ais.plan_summarize_part("The Recall", scenes, Budget(1_900, 1_000))
    assert kept == [f"Scene {i}" for i in range(len(kept))] and 0 < len(kept) < 10
    row = next(s for s in report.sections if s.name == "Scene summaries")
    assert row.items_dropped == tuple(f"Scene {i}" for i in range(len(kept), 10))
    with pytest.raises(BudgetError):
        ais.plan_summarize_part("x", scenes, Budget(400, 300))


def test_summarize_part_builds_a_part_summary_with_inputs():
    reply = json.dumps({"summary": "The recall began.", "characters": [{"name": "Mara", "state": "home"}],
                        "threads": ["the signal"]})
    client = FakeClient(reply, cost=0.02)
    inputs = (("01-rain.md", "abc"),)
    part = ais.summarize_part("The Recall", scene_summaries(2), "m/x", inputs, client=client)
    assert part.summary == "The recall began." and part.inputs == inputs and part.cost == pytest.approx(0.02)
    assert part.characters == (sm.Character("Mara", "home"),) and part.threads == ("the signal",)
    user = client.kwargs["messages"][1]["content"]
    assert user.startswith("PART: The Recall") and "### Scene 1\nEvent 1." in user
    with pytest.raises(ValueError):
        ais.summarize_part("x", scene_summaries(1), "m/x", client=FakeClient("nope"))


# -- model role -------------------------------------------------------------------------


def test_summary_role_falls_back_to_the_writing_model(monkeypatch):
    from chisel.core import settings as user_settings
    monkeypatch.setattr(user_settings, "get", lambda key, default=None: {}.get(key))
    assert ai_client.resolve_model("summary") == ai_client.resolve_model("writing")
    assert ai_client.resolve_model("summary", {"ai": {"writing_model": "w/1"}}) == "w/1"
    assert ai_client.resolve_model("summary", {"ai": {"writing_model": "w/1", "summary_model": "s/2"}}) == "s/2"
    monkeypatch.setattr(user_settings, "get", lambda key, default=None: {"summary_model": "s/3"}.get(key))
    assert ai_client.resolve_model("summary") == "s/3"
