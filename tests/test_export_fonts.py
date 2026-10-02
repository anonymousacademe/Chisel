"""Export fonts are vendored: PDF export must not depend on the system's fonts."""

import pytest

from lorewrite.core.export import layouts

pytestmark = pytest.mark.skipif(not layouts.reportlab_available(), reason="ReportLab missing")


def test_bundled_fonts_work_with_no_system_fonts(monkeypatch):
    from lorewrite.core.export import pdfkit

    monkeypatch.setattr(pdfkit, "_FONT_ROOTS", ())
    pdfkit.fonts_present.cache_clear()
    try:
        assert {"noto-serif", "liberation-mono"} <= pdfkit.fonts_present()
        assert pdfkit.register_font("noto-serif").regular == "NotoSerif-R"
    finally:
        pdfkit.fonts_present.cache_clear()


def test_every_layout_has_a_bundled_font():
    from lorewrite.core.export import pdfkit

    for name in ("book", "manuscript", "plain"):
        assert {"noto-serif", "liberation-mono"} & set(layouts.get(name).fonts), name
    assert all((pdfkit.BUNDLED / f"{stem}.ttf").is_file()
               for key in ("noto-serif", "liberation-mono") for stem in pdfkit.FONTS[key][3])


def test_font_licences_ship_with_the_fonts():
    from lorewrite.core.export import pdfkit

    assert (pdfkit.BUNDLED / "OFL-NotoSerif.txt").is_file()
    assert (pdfkit.BUNDLED / "LICENSE-Liberation.txt").is_file()
