"""Speech engines for read aloud (docs/dev/plan-read-aloud.md): local voices downloaded from Hugging Face
(Kokoro), any OpenAI-compatible speech endpoint (a local speech server, or a cloud service the author chooses),
and a cache of rendered clips. Desktop only; nothing here runs unless the author asks for sound.

The browser's own voices need nothing from Python. Every other engine turns one piece of text into a WAV clip.
"""
