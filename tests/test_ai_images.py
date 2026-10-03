"""ai/images: generate() parsing with a fake client, cost, prompt hygiene; image-model catalog."""

import base64
from types import SimpleNamespace

import pytest

from chisel.ai import images
from chisel.ai.client import (DEFAULT_IMAGE_MODEL, MODEL_DEFAULTS, parse_models, resolve_model)
from chisel.ai.usage import LEDGER
from chisel.core import settings as user_settings

JPEG = b"\xff\xd8\xff\xe0" + b"j" * 30
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 30


def url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


class FakeMessage:
    def __init__(self, content="", imgs=None, refusal=None):
        self._d = {"role": "assistant", "content": content, "refusal": refusal,
                   "images": imgs}

    def model_dump(self):
        return dict(self._d)

    @property
    def content(self):
        return self._d["content"]


class FakeClient:
    def __init__(self, message, cost=0.0336, choices=True):
        self.calls = []
        usage = SimpleNamespace(cost=cost, prompt_tokens=10, completion_tokens=1120)
        resp = SimpleNamespace(choices=[SimpleNamespace(message=message)] if choices else [], usage=usage)
        outer = self

        class Completions:
            def create(self, **kw):
                outer.calls.append(kw)
                return resp

        self.chat = SimpleNamespace(completions=Completions())


def part(data, mime):
    return {"type": "image_url", "image_url": {"url": url(data, mime)}}


def test_generate_parses_a_jpeg_and_records_cost():
    client = FakeClient(FakeMessage("", [part(JPEG, "image/jpeg")]))
    out = images.generate("A dark subway platform", "g/img", client=client, style="no text")
    assert out == [(JPEG, "jpg")]
    call = client.calls[0]
    assert call["model"] == "g/img"
    assert call["messages"] == [{"role": "user", "content": "A dark subway platform. no text"}]
    assert call["extra_body"]["modalities"] == ["image", "text"]
    assert call["extra_body"]["usage"] == {"include": True}
    assert "provider" not in call["extra_body"] and "response_format" not in call
    last = LEDGER.last()
    assert (last.feature, last.model, last.cost) == ("image", "g/img", 0.0336)


def test_generate_keeps_several_images_png_and_jpeg():
    client = FakeClient(FakeMessage("here", [part(PNG, "image/png"), part(JPEG, "image/jpeg")]))
    assert images.generate("x", "m", client=client) == [(PNG, "png"), (JPEG, "jpg")]


def test_the_bytes_decide_the_type_not_the_mime():
    client = FakeClient(FakeMessage("", [part(PNG, "image/jpeg")]))
    assert images.generate("x", "m", client=client) == [(PNG, "png")]


def test_no_images_shows_what_the_model_said():
    client = FakeClient(FakeMessage("I can't draw that.", None))
    with pytest.raises(images.ImageError, match="I can't draw that"):
        images.generate("x", "m", client=client)
    assert LEDGER.count() == 1                       # the call was made, so it is on the ledger
    with pytest.raises(images.ImageError, match="did not return an image"):
        images.generate("x", "m", client=FakeClient(FakeMessage("", [])))
    with pytest.raises(images.ImageError, match="refus"):
        images.generate("x", "m", client=FakeClient(FakeMessage("", None, refusal="refused: policy")))
    with pytest.raises(images.ImageError):
        images.generate("x", "m", client=FakeClient(None, choices=False))


def test_junk_parts_are_skipped_not_fatal():
    bad = [{"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
           {"type": "image_url", "image_url": {"url": "data:image/png;base64,@@@@"}},
           {"type": "image_url", "image_url": {"url": url(b"GIF89a....", "image/gif")}},
           {"type": "image_url"}, "nonsense", part(JPEG, "image/jpeg")]
    assert images.extract_images({"images": bad}) == [(JPEG, "jpg")]


def test_an_empty_prompt_makes_no_call():
    client = FakeClient(FakeMessage("", [part(JPEG, "image/jpeg")]))
    with pytest.raises(images.ImageError):
        images.generate("   ", "m", client=client, style="")
    assert client.calls == []


def test_style_suffix_setting_and_default():
    assert images.style_suffix() == images.DEFAULT_STYLE
    assert images.full_prompt("A pier.") == "A pier. " + images.DEFAULT_STYLE
    user_settings.set("image_style", "oil painting")
    assert images.full_prompt("A pier") == "A pier. oil painting"
    user_settings.set("image_style", "")
    assert images.full_prompt("A pier") == "A pier"                   # turned off
    assert images.full_prompt("A pier, OIL PAINTING", "oil painting") == "A pier, OIL PAINTING"


def test_suggest_prompt_cleans_the_reply():
    client = FakeClient(FakeMessage('Prompt: "A rain-slick market under a rail spur,\nneon koi."'))
    out = images.suggest_prompt("ctx <<CURSOR>>", "fast/model", client=client)
    assert out == "A rain-slick market under a rail spur, neon koi."
    msgs = client.calls[0]["messages"]
    assert "no text" in msgs[0]["content"].casefold() and "ctx" in msgs[1]["content"]
    assert LEDGER.last().feature == "image-prompt"
    with pytest.raises(images.ImageError):
        images.suggest_prompt("c", "m", client=FakeClient(FakeMessage("  ")))


# -- model role and catalog -------------------------------------------------------


def test_image_is_the_fourth_model_role():
    assert MODEL_DEFAULTS["image"] == DEFAULT_IMAGE_MODEL == "google/gemini-3.1-flash-lite-image"
    assert resolve_model("image") == DEFAULT_IMAGE_MODEL
    user_settings.set("image_model", "x/img")
    assert resolve_model("image") == "x/img"
    assert resolve_model("image", {"ai": {"image_model": "proj/img"}}) == "proj/img"


PAYLOAD = {"data": [
    {"id": "a/text", "name": "Text", "architecture": {"output_modalities": ["text"]},
     "supported_parameters": ["structured_outputs"], "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
    {"id": "g/img", "name": "Img", "architecture": {"output_modalities": ["image", "text"]},
     "pricing": {"prompt": "0.0000001", "completion": "0.00003", "image": "0.03"}, "context_length": 32000},
    {"id": "no-arch", "name": "Bare"},
]}


def test_catalog_filters_image_output_models():
    got = parse_models(PAYLOAD, structured_only=False, output_modality="image")
    assert [m.id for m in got] == ["g/img"]
    assert got[0].output_modalities == ("image", "text") and got[0].image_price == 0.03
    assert got[0].completion_per_m == pytest.approx(30.0)
    assert [m.id for m in parse_models(PAYLOAD, structured_only=False)] == ["no-arch", "g/img", "a/text"]
    assert [m.id for m in parse_models(PAYLOAD)] == ["a/text"]       # the old default is unchanged
