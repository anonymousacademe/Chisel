"""The `reasoning` setting for utility AI calls (default | low | off). Fakes only, no network."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from chisel.ai import client as ai_client
from chisel.ai import continuity, links, relationships, style
from chisel.ai import summaries as ais
from chisel.ai.budget import Budget, Section, fit
from chisel.ai.stream import CancelToken
from chisel.core import settings as user_settings
from chisel.core.entities import Entity

USAGE = {"usage": {"include": True}}
STRICT = {"provider": {"require_parameters": True}}
OFF = {"reasoning": {"enabled": False}}
LOW = {"reasoning": {"effort": "low"}}


@pytest.fixture(autouse=True)
def fresh():
    ai_client.set_meta_source(None)
    yield
    ai_client.set_meta_source(None)


def use(value):
    user_settings.set("reasoning", value)


class Capture:
    """Records every extra_body; answers with an empty JSON object."""
    def __init__(self):
        self.bodies = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.bodies.append(kw.get("extra_body"))
        usage = SimpleNamespace(cost=0.0, prompt_tokens=1, completion_tokens=1)
        if kw.get("stream"):
            chunk = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="{}"))], usage=None)
            return iter([chunk, SimpleNamespace(choices=[], usage=usage)])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))], usage=usage)


def run(fn):
    c = Capture()
    try:
        fn(c)
    except Exception:
        pass            # an empty reply is an error for most of them; only the request matters here
    assert c.bodies, "the call never reached the client"
    return c.bodies[-1]


MARA = Entity(name="Mara", type="character")
SCENE = "# T\n\nMara walked home in the rain. It had not stopped for three days.\n"
SITES = {
    "aliases": (lambda c, m: links.suggest_links(SCENE, [MARA], m, client=c), STRICT),
    "continuity": (lambda c, m: continuity.check_scene(SCENE, [MARA], {"Mara": "Mara is tall."}, m, client=c), STRICT),
    "canon": (lambda c, m: continuity.propose_canon_updates(SCENE, [MARA], m, client=c), STRICT),
    "relationships": (lambda c, m: relationships.suggest_relationships(MARA, [MARA, Entity("Elias", "character")],
                                                                       m, client=c), STRICT),
    "style": (lambda c, m: style.learn_style([("a", SCENE)], m, client=c), {}),
    "summary": (lambda c, m: ais.summarize_scene(SCENE, [], m, client=c), {}),
    "summary (streamed)": (lambda c, m: ais.summarize_scene(SCENE, [], m, client=c, cancel=CancelToken()), {}),
}


@pytest.mark.parametrize("site", SITES)
def test_default_sends_exactly_what_it_always_did(site):
    fn, extra = SITES[site]
    assert run(lambda c: fn(c, "x/model")) == {**extra, **USAGE}


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("value, field", [("off", OFF), ("low", LOW)])
def test_off_and_low_put_the_exact_field_in_the_body(site, value, field):
    use(value)
    fn, _ = SITES[site]
    body = run(lambda c: fn(c, "x/model"))
    assert body == {**USAGE, **field}          # and never provider.require_parameters beside it


@pytest.mark.parametrize("site", SITES)
def test_a_local_model_never_gets_it(site):
    use("off")
    fn, _ = SITES[site]
    assert run(lambda c: fn(c, "local:llama3")) == {}


def test_voice_uses_the_utility_body():
    src = (Path(__file__).parent.parent / "src" / "chisel" / "ai" / "voice.py").read_text(encoding="utf-8")
    assert "utility_extra_body(" in src and "openrouter_extra_body(" not in src


def test_drafting_and_chat_streams_never_get_it():
    use("off")
    from chisel.ai.stream import stream_text
    c = Capture()
    stream_text(c, "x/model", [{"role": "user", "content": "hi"}], "draft")
    assert c.bodies == [USAGE]


def test_unknown_values_fall_back_to_default():
    for bad in ("max", "", None, 3, "OFF!", ["off"]):
        use(bad)
        assert ai_client.resolve_reasoning() == "default"
        assert ai_client.reasoning_extra_body(bad) == {}
    assert ai_client.reasoning_extra_body("default") == {}
    assert ai_client.resolve_reasoning({"ai": {"reasoning": "bogus"}}) == "default"
    use("off")                       # a bad project value falls through to the user's setting
    assert ai_client.resolve_reasoning({"ai": {"reasoning": "bogus"}}) == "off"
    use(" Low ")
    assert ai_client.resolve_reasoning() == "low"


def test_reasoning_extra_body_values():
    assert ai_client.reasoning_extra_body("low") == LOW
    assert ai_client.reasoning_extra_body("off") == OFF
    body = ai_client.reasoning_extra_body("off")
    body["reasoning"]["enabled"] = True            # a copy: the table is not changed
    assert ai_client.reasoning_extra_body("off") == OFF


def test_project_toml_overrides_the_user_setting():
    use("off")
    meta = {"ai": {"reasoning": "low"}}
    assert ai_client.resolve_reasoning(meta) == "low"
    assert ai_client.resolve_reasoning({"ai": {"reasoning": "default"}}) == "default"
    assert ai_client.resolve_reasoning({}) == "off"
    ai_client.set_meta_source(lambda: meta)
    fn, _ = SITES["summary"]
    assert run(lambda c: fn(c, "x/model")) == {**USAGE, **LOW}
    ai_client.set_meta_source(lambda: {"ai": {"reasoning": "default"}})
    assert run(lambda c: fn(c, "x/model")) == USAGE


def test_a_broken_meta_source_means_user_setting():
    use("low")
    ai_client.set_meta_source(lambda: 1 / 0)
    assert ai_client.active_reasoning("x/y") == "low"


def test_extra_options_of_other_providers_keep_their_other_keys():
    body = ai_client.openrouter_extra_body({"provider": {"require_parameters": True, "order": ["a"]}},
                                           model="x/y", reasoning="off")
    assert body == {"usage": {"include": True}, "provider": {"order": ["a"]}, **OFF}


def test_the_report_says_when_reasoning_ran_off_or_low():
    sections = [Section("Scene", "SCENE:\nx")]
    use("default")
    _, rep = fit(sections, Budget.for_model("x/model"), "summary")
    assert rep.reasoning == "" and "reasoning" not in rep.summary()
    use("off")
    _, rep = fit(sections, Budget.for_model("x/model"), "summary")
    assert rep.reasoning == "reasoning off" and rep.summary().endswith("; reasoning off")
    assert rep.to_dict()["reasoning"] == "reasoning off"
    assert "reasoning" not in fit(sections, Budget.for_model("local:m"), "summary")[1].to_dict()
    use("low")
    assert fit(sections, Budget.for_model("x/model"), "continuity")[1].reasoning == "reasoning low"
    # drafting and chat are not utility calls: nothing said
    assert fit(sections, Budget.for_model("x/model"), "draft")[1].reasoning == ""
    # a local model never ran with it
    assert fit(sections, Budget.for_model("local:m"), "summary")[1].reasoning == ""


def test_the_plan_reports_carry_it():
    use("off")
    _, sent = ais.plan_summarize(SCENE, [MARA], Budget.for_model("x/model"))
    assert sent.reasoning == "reasoning off"
    _, sent = links.plan_aliases(SCENE, [MARA], Budget.for_model("x/model"))
    assert sent.reasoning == "reasoning off"
