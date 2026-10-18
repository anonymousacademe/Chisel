"""Script export helpers (script mode): the Fountain file and the text the screenplay layout pages.

``manuscript.assemble`` produces the book for a script project too (each scene is one ``ScriptText`` block
holding its Fountain text); this module turns that book into Fountain, or into the one text the PDF layout
paginates. Pure Python; no ReportLab."""

from __future__ import annotations

from .. import fountain
from .manuscript import Book, ScriptText


def scene_texts(book: Book) -> list[str]:
    """The Fountain text of every scene, in reading order (empty scenes left out)."""
    out = []
    for chapter in book.chapters():
        text = "\n\n".join(b.text for b in chapter.blocks if isinstance(b, ScriptText)).strip("\n")
        if text.strip():
            out.append(text)
    return out


def script_text(book: Book) -> str:
    """The whole script as one text for the PDF layout to paginate: notes are back in the ``<!-- -->`` form
    Chisel's parser knows, so they are recognised as notes and never printed."""
    return fountain.notes_from_fountain("\n\n".join(scene_texts(book))) + "\n"


def to_fountain(book: Book) -> str:
    """The book as a ``.fountain`` file: a title page, parts as ``# sections``, scenes as written (with a
    ``= synopsis`` of the scene's title when it says more than its heading)."""
    parts = []
    for part in book.parts:
        scenes = [(c.title, "\n\n".join(b.text for b in c.blocks if isinstance(b, ScriptText)))
                  for c in part.chapters]
        parts.append((part.title, scenes))
    page = fountain.title_page_text(book.title, book.author, book.contact, book.copyright, book.subtitle)
    return fountain.export_text(page, parts)
