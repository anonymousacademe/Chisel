"""Shared ReportLab helpers for the PDF layouts: fonts (embedded TTFs), page
sizes, inline markup, a few typographic niceties. Imports ReportLab, so import
this module only through ``layouts`` (which checks that it is installed)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4, A5, LETTER
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .manuscript import Run

PAGE_SIZES = {
    "trade": (6 * inch, 9 * inch),
    "a5": A5,
    "letter": LETTER,
    "a4": A4,
}

# key -> (label, family name used in the PDF, directory names to search,
#         file stems for regular / bold / italic / bold-italic)
FONTS = {
    "noto-serif": ("Noto Serif", "NotoSerif",
                   ("noto",), ("NotoSerif-Regular", "NotoSerif-Bold",
                               "NotoSerif-Italic", "NotoSerif-BoldItalic")),
    "liberation-serif": ("Liberation Serif", "LiberationSerif",
                         ("liberation", "liberation-fonts", "truetype/liberation"),
                         ("LiberationSerif-Regular", "LiberationSerif-Bold",
                          "LiberationSerif-Italic", "LiberationSerif-BoldItalic")),
    "liberation-sans": ("Liberation Sans", "LiberationSans",
                        ("liberation", "liberation-fonts", "truetype/liberation"),
                        ("LiberationSans-Regular", "LiberationSans-Bold",
                         "LiberationSans-Italic", "LiberationSans-BoldItalic")),
    "liberation-mono": ("Liberation Mono", "LiberationMono",
                        ("liberation", "liberation-fonts", "truetype/liberation"),
                        ("LiberationMono-Regular", "LiberationMono-Bold",
                         "LiberationMono-Italic", "LiberationMono-BoldItalic")),
}
# Noto Serif and Liberation Mono ship inside the package (SIL OFL, licences beside
# the files), so a PDF export works on any machine; everything else, and these
# too when the files are somehow missing, is looked up in the system's fonts.
BUNDLED = Path(__file__).resolve().parent / "fonts"
_FONT_ROOTS = (Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
               Path.home() / ".local/share/fonts", Path.home() / ".fonts",
               Path.home() / "Library/Fonts", Path("/Library/Fonts"),
               Path("/System/Library/Fonts"), Path("C:/Windows/Fonts"))


def font_label(key: str) -> str:
    return FONTS[key][0]


def _find(stem: str) -> Path | None:
    bundled = BUNDLED / f"{stem}.ttf"
    if bundled.is_file():
        return bundled
    for root in _FONT_ROOTS:
        if root.is_dir():
            for hit in root.rglob(f"{stem}.ttf"):
                return hit
    return None


@lru_cache(maxsize=None)
def fonts_present() -> frozenset[str]:
    """Font keys whose four faces (regular, bold, italic, bold italic) all exist."""
    return frozenset(k for k, (_l, _f, _d, stems) in FONTS.items()
                     if all(_find(s) for s in stems))


@dataclass(frozen=True)
class Face:
    family: str
    regular: str
    bold: str
    italic: str
    bold_italic: str


def register_font(key: str) -> Face:
    """Register the four faces of font *key* (once) and return their names. A
    missing font raises FileNotFoundError naming it."""
    if key not in FONTS:
        raise ValueError(f"unknown font: {key}")
    label, family, _dirs, stems = FONTS[key]
    names = [f"{family}-{suffix}" for suffix in ("R", "B", "I", "BI")]
    if names[0] not in pdfmetrics.getRegisteredFontNames():
        paths = [_find(s) for s in stems]
        if not all(paths):
            raise FileNotFoundError(f"the font {label} is not installed")
        for name, path in zip(names, paths):
            pdfmetrics.registerFont(TTFont(name, str(path)))
        pdfmetrics.registerFontFamily(names[0], normal=names[0], bold=names[1],
                                      italic=names[2], boldItalic=names[3])
    return Face(family, *names)


def hyphenation_lang() -> str | None:
    """'en_US' when pyphen is installed (ReportLab hyphenates with it), else None."""
    try:
        import pyphen  # noqa: F401
    except ImportError:
        return None
    return "en_US"


def markup(runs: tuple[Run, ...], smart: bool = False) -> str:
    """Runs -> ReportLab paragraph markup (escaped, with <i>/<b>)."""
    out = []
    for r in runs:
        text = smarten(r.text) if smart else r.text
        text = escape(text)
        if r.bold:
            text = f"<b>{text}</b>"
        if r.italic:
            text = f"<i>{text}</i>"
        out.append(text)
    return "".join(out)


def smarten(text: str) -> str:
    """Curly quotes and dashes from straight ones: "..." -> “...”, ' -> ’,
    -- -> —, ... -> …  (a quote opens after whitespace, an opening bracket or
    a dash, else it closes)."""
    text = text.replace("---", "\u2014").replace("--", "\u2014").replace("...", "\u2026")
    text = re.sub(r'(^|[\s(\[{\u2014\u2013])"', "\\1\u201c", text)
    text = text.replace('"', "\u201d")
    text = re.sub(r"(^|[\s(\[{\u2014\u2013\u201c])'", "\\1\u2018", text)
    return text.replace("'", "\u2019")


def spaced(text: str) -> str:
    """Word spaces in small caps style labels are widened by hand: ReportLab
    has no letter-spacing, so labels use thin spaces between letters."""
    return "\u200a".join(text)
