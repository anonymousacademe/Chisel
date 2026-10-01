"""Page layouts for the PDF writer. A layout is a small module exposing
``LAYOUT`` (a ``Layout``): its name, description, which options it honours and
a ``render(book, options, path)`` function that writes the PDF and returns the
page count. To add one: write the module, import it in ``_REGISTRY`` below."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

from ..manuscript import Book, ExportOptions


@dataclass(frozen=True)
class Layout:
    name: str
    label: str
    description: str
    page_sizes: tuple[str, ...]            # ("letter",) = fixed
    fonts: tuple[str, ...]                 # font keys; the first is the default
    toc: bool = False                      # honours the table-of-contents option
    continuous: bool = True                # honours "scenes flow on"
    numbering: bool = True                 # honours chapter numbering words
    render: object = None                  # (Book, ExportOptions, Path) -> pages

    def resolve(self, options: ExportOptions) -> ExportOptions:
        """*options* with the page size and font forced into what this layout
        offers (the dialog keeps one set of options across layouts)."""
        from dataclasses import replace
        size = options.page_size if options.page_size in self.page_sizes else self.page_sizes[0]
        font = options.font if options.font in self.fonts else self.fonts[0]
        return replace(options, page_size=size, font=font)

    def describe(self) -> dict:
        from .. import pdfkit
        return {"name": self.name, "label": self.label, "description": self.description,
                "page_sizes": list(self.page_sizes),
                "fonts": [{"key": k, "label": pdfkit.font_label(k),
                           "available": k in pdfkit.fonts_present()} for k in self.fonts],
                "toc": self.toc, "continuous": self.continuous, "numbering": self.numbering}


_REGISTRY = ("book", "manuscript", "plain")


def reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return False
    return True


def all_layouts() -> list[Layout]:
    """Every layout, in menu order. Needs ReportLab (the ``export`` extra)."""
    return [importlib.import_module(f"{__name__}.{m}").LAYOUT for m in _REGISTRY]


def get(name: str) -> Layout:
    for layout in all_layouts():
        if layout.name == name:
            return layout
    raise ValueError(f"unknown layout: {name}")
