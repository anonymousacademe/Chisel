"""Streaming AI calls (plan 1.5): deltas, usage from the last chunk, cancel closes
the stream and raises Cancelled. Fake streams only; nothing reaches the network."""

import threading
from types import SimpleNamespace

import pytest

from chisel.ai import writing
from chisel.ai.stream import Cancelled, CancelToken, call_ai, stream_text
from chisel.ai.usage import LEDGER


def chunk(text=None, usage=None):
    choices = [SimpleNamespace(delta=SimpleNamespace(content=text))] if text is not None else []
    return SimpleNamespace(choices=choices, usage=usage)


class FakeStream:
    def __init__(self, chunks, on_chunk=None, block=None):
        self.chunks, self.on_chunk, self.block = chunks, on_chunk, block
        self.closed = False
        self.read = 0

    def __iter__(self):
        for i, c in enumerate(self.chunks):
            if self.block is not None and i == 1:
                self.block.wait(5)           # a stalled stream, until closed
                if self.closed:
                    raise ConnectionError("stream closed")
            if self.on_chunk:
                self.on_chunk(i)
            self.read += 1
            yield c

    def close(self):
        self.closed = True
        if self.block is not None:
            self.block.set()


class FakeClient:
    def __init__(self, stream):
        self.stream = stream
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return self.stream


USAGE = SimpleNamespace(cost=0.0042, prompt_tokens=10, completion_tokens=5)


@pytest.fixture(autouse=True)
def clean_ledger():
    LEDGER.clear()
    yield
    LEDGER.clear()


def test_stream_yields_deltas_and_records_cost_from_the_last_chunk():
    stream = FakeStream([chunk("Hel"), chunk("lo "), chunk("there"), chunk(None, USAGE)])
    client = FakeClient(stream)
    got = []
    text = stream_text(client, "m/x", [{"role": "user", "content": "hi"}], "ask", got.append)
    assert text == "Hello there" and got == ["Hel", "lo ", "there"]
    assert client.kwargs["stream"] is True and client.kwargs["extra_body"]["usage"]["include"] is True
    assert stream.closed
    assert LEDGER.count() == 1 and LEDGER.last().cost == pytest.approx(0.0042)


def test_cancel_between_chunks_closes_the_stream_and_raises():
    token = CancelToken()
    stream = FakeStream([chunk("a"), chunk("b"), chunk("c"), chunk(None, USAGE)],
                        on_chunk=lambda i: token.set() if i == 1 else None)
    got = []
    with pytest.raises(Cancelled):
        stream_text(FakeClient(stream), "m", [], "ask", got.append, token)
    assert stream.closed and "".join(got) == "a" and stream.read < 4
    assert LEDGER.count() == 0           # no usage was reported: nothing to record


def test_cancel_closes_a_stalled_stream_from_another_thread():
    token = CancelToken()
    block = threading.Event()
    stream = FakeStream([chunk("a"), chunk("b")], block=block)
    threading.Timer(0.1, token.set).start()
    with pytest.raises(Cancelled):
        stream_text(FakeClient(stream), "m", [], "ask", None, token)
    assert stream.closed


def test_cancelled_before_start_makes_no_request():
    token = CancelToken()
    token.set()
    client = FakeClient(FakeStream([]))
    with pytest.raises(Cancelled):
        stream_text(client, "m", [], "ask", None, token)
    assert client.kwargs is None


def test_cost_reported_before_the_stop_is_recorded():
    token = CancelToken()
    stream = FakeStream([chunk("a", USAGE), chunk("b")],
                        on_chunk=lambda i: token.set() if i == 1 else None)
    with pytest.raises(Cancelled):
        stream_text(FakeClient(stream), "m", [], "ask", None, token)
    assert LEDGER.count() == 1 and LEDGER.last().cost == pytest.approx(0.0042)


def test_a_real_error_still_propagates():
    def boom(i):
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError, match="provider down"):
        stream_text(FakeClient(FakeStream([chunk("a")], on_chunk=boom)), "m", [], "ask")


def streamed(text="One. Two."):
    lines = text.split("\n")
    pieces = [line + ("\n" if i < len(lines) - 1 else "") for i, line in enumerate(lines)]
    return FakeClient(FakeStream([chunk(p) for p in pieces] + [chunk(None, USAGE)]))


def test_writing_calls_stream_when_asked_and_clean_the_result():
    got = []
    out = writing.generate("draft", "go", "ctx", "m", client=streamed("Here is prose."),
                           on_delta=got.append)
    assert out == "Here is prose." and "".join(got).strip() == "Here is prose."
    assert writing.ask("q?", "ctx", "m", client=streamed("Answer <!-- x"), on_delta=got.append) \
        == "Answer <!- x"
    assert writing.research_answer("q?", "ctx", "m", client=streamed("Per [1]."), cancel=CancelToken()) \
        == "Per [1]."
    ideas = writing.brainstorm("ctx", "m", client=streamed("1. A thing.\n2. Another."),
                               on_delta=got.append)
    assert ideas == ["A thing.", "Another."]


def test_a_stopped_draft_returns_nothing():
    token = CancelToken()
    stream = FakeStream([chunk("x "), chunk("y ")], on_chunk=lambda i: token.set())
    with pytest.raises(Cancelled):
        writing.generate("draft", "go", "ctx", "m", client=FakeClient(stream), cancel=token)


def test_call_ai_passes_streaming_arguments_only_to_functions_that_take_them():
    seen = {}

    def old(a):
        return a

    def new(a, on_delta=None, cancel=None):
        seen.update(on_delta=on_delta, cancel=cancel)
        return a

    token = CancelToken()
    assert call_ai(old, 1, on_delta=print, cancel=token) == 1
    assert call_ai(new, 2, on_delta=print, cancel=token) == 2
    assert seen == {"on_delta": print, "cancel": token}
