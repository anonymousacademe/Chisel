"""What can be downloaded: the Kokoro model (Apache-2.0) and its voices, from Hugging Face.

One entry for now. Each new entry is checked against its model card before it is added (licences change)."""

from __future__ import annotations

HF_REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
HF_URL = f"https://huggingface.co/{HF_REPO}"
LICENCE = "Apache-2.0"

# variant -> (file in the repository, size in bytes, what to tell the author)
VARIANTS = {
    "standard": ("onnx/model_quantized.onnx", 92_361_116, "Natural voices, 92 MB (recommended)"),
    "high": ("onnx/model.onnx", 325_532_232, "Slightly richer sound, 326 MB"),
}
VOICE_BYTES = 522_240          # one voice style file (510 x 256 float32)

# voice id prefix: first letter the language (with its espeak code), second letter the gender
LANGUAGES = {
    "a": ("en-us", "English (US)"), "b": ("en-gb", "English (UK)"), "e": ("es", "Spanish"), "f": ("fr-fr", "French"),
    "h": ("hi", "Hindi"), "i": ("it", "Italian"), "p": ("pt-br", "Portuguese (Brazil)"), "j": ("ja", "Japanese"),
    "z": ("cmn", "Mandarin"),
}
GENDERS = {"f": "female", "m": "male"}

# Offered first: the voices most listeners find most natural (an editorial choice, not a measurement)
SUGGESTED = ("af_heart", "af_bella", "bf_emma", "am_michael", "am_fenrir", "bm_george", "af_nicole", "bm_fable",
             "am_puck", "bf_isabella", "af_sarah", "bm_lewis", "af_kore", "af_aoede", "am_echo", "bm_daniel")


def describe_voice(voice_id: str) -> dict:
    """{id, name, lang, language, gender, label, rank} for a Kokoro voice id such as ``af_heart``."""
    prefix, _, stem = voice_id.partition("_")
    lang, language = LANGUAGES.get(prefix[:1], ("en-us", "Unknown language"))
    gender = GENDERS.get(prefix[1:2], "")
    name = stem.replace("_", " ").title() or voice_id
    rank = SUGGESTED.index(voice_id) if voice_id in SUGGESTED else len(SUGGESTED) + (0 if prefix[:1] in "ab" else 100)
    detail = ", ".join(x for x in (language, gender) if x)
    return {"id": voice_id, "name": name, "lang": lang, "language": language, "gender": gender,
            "label": f"{name} ({detail})", "rank": rank}


def language_of(voice_id: str) -> str:
    """The espeak language code Kokoro needs for a voice."""
    return LANGUAGES.get(voice_id[:1], ("en-us", ""))[0]
