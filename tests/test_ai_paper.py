"""Research-mode AI proposals: suggest_latex / suggest_plot_code (plan 7.3, 7.4).

No network: the client is a fake served by a booby-trapped make_client, and
the Budget is patched where a test needs a tiny window.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisel.ai import paper
from chisel.ai.budget import Budget, BudgetError
from chisel.ai.stream import CancelToken, Cancelled

MODEL = "vendor/model-x"


class FakeStream:
    def __init__(self, parts, on_next=None):
        self._parts = list(parts)
        self._on_next = on_next
        self.closed = False

    def __iter__(self):
        for text in self._parts:
            if self._on_next is not None:
                self._on_next()
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=text))], usage=None)

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, parts, on_next=None):
        self.calls = []
        self._parts = parts
        self._on_next = on_next
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self._parts, self._on_next)


def _sent_text(call) -> str:
    return "\n".join(m["content"] for m in call["messages"])


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient(["```latex\n", "E = mc^2", "\n```"])
    monkeypatch.setattr(paper, "make_client", lambda model=None: fake)
    return fake


def test_suggest_latex_returns_unfenced_proposal(client):
    out = paper.suggest_latex("Einstein's mass energy relation", model=MODEL, cancel=None)
    assert out == "E = mc^2"
    call = client.calls[0]
    assert "Einstein's mass energy relation" in _sent_text(call)
    # OpenRouter-only structured output is never sent for these proposals
    assert "response_format" not in call
    assert "require_parameters" not in str(call)


def test_suggest_plot_code_fence_is_removed(monkeypatch):
    fake = FakeClient(["```python\nprint('x')\n```"])
    monkeypatch.setattr(paper, "make_client", lambda model=None: fake)
    assert paper.suggest_plot_code("a line plot", None, model=MODEL, cancel=None) == "print('x')"


def test_columns_not_sent_when_not_ticked(client):
    paper.suggest_plot_code("flow against time", None, model=MODEL, cancel=None)
    sent = _sent_text(client.calls[0])
    assert "DATA COLUMNS" not in sent
    report = paper.plan_plot_code("flow against time", None, model=MODEL)
    assert "Data columns" not in [s.name for s in report.sections]


def test_columns_sent_and_reported_when_ticked(client):
    cols = ["time_h", "flow_m3s"]
    paper.suggest_plot_code("flow against time", cols, model=MODEL, cancel=None)
    assert "- flow_m3s" in _sent_text(client.calls[0])
    report = paper.plan_plot_code("flow against time", cols, model=MODEL)
    section = next(s for s in report.sections if s.name == "Data columns")
    assert section.items_total == 2 and section.items_sent == 2


def test_plan_sends_nothing(monkeypatch):
    def boom(model=None):
        raise AssertionError("no network call while planning")
    monkeypatch.setattr(paper, "make_client", boom)
    report = paper.plan_latex("a Gaussian", model=MODEL)
    assert report.est_tokens > 0
    assert paper.plan_plot_code("a plot", ["a"], model=MODEL).est_tokens > 0


def test_stopped_before_call_returns_nothing(monkeypatch):
    fake = FakeClient(["x"])
    monkeypatch.setattr(paper, "make_client", lambda model=None: fake)
    token = CancelToken()
    token.set()
    with pytest.raises(Cancelled):
        paper.suggest_latex("anything", model=MODEL, cancel=token)
    assert fake.calls == []


def test_stopped_mid_stream_returns_nothing(monkeypatch):
    token = CancelToken()
    fake = FakeClient(["a", "b", "c"], on_next=lambda: None)
    # cancel as soon as the first chunk is read
    fake._on_next = token.set
    monkeypatch.setattr(paper, "make_client", lambda model=None: fake)
    with pytest.raises(Cancelled):
        paper.suggest_plot_code("plot", None, model=MODEL, cancel=token)


def test_request_that_does_not_fit_raises_before_network(monkeypatch):
    def boom(model=None):
        raise AssertionError("no network call when the request does not fit")
    monkeypatch.setattr(paper, "make_client", boom)
    monkeypatch.setattr(paper.Budget, "for_model",
                        classmethod(lambda cls, model, *a, **k: Budget(60, 10)))
    with pytest.raises(BudgetError):
        paper.suggest_latex("word " * 2000, model=MODEL, cancel=None)


def test_mock_paper_functions_take_the_real_arguments(monkeypatch):
    import types

    from chisel.gui import mockai

    monkeypatch.setattr(mockai, "_pause", lambda seconds: None)
    mod = types.SimpleNamespace()
    mockai.install(mod)
    assert "E" in mod.suggest_latex("mass energy", model="m", cancel=None)
    assert "savefig" in mod.suggest_plot_code("a plot", ["t"], model="m", cancel=None)
