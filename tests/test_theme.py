"""Omarchy theme-following tests."""

from pathlib import Path

from lorewrite.tui.theme import (
    current_theme_slug,
    load_omarchy_colors,
    omarchy_textual_theme,
)

CATPPUCCIN = """\
mode = "dark"
accent = "#89b4fa"
background = "#1e1e2e"
lighter_background = "#313244"
dark_background = "#161622"
foreground = "#cdd6f4"
cyan = "#94e2d5"
orange = "#f6b6ab"
yellow = "#f9e2af"
red = "#f38ba8"
green = "#a6e3a1"
blue = "#89b4fa"
"""


def test_slug_from_state_file(tmp_path: Path):
    state = tmp_path / "theme.name"
    state.write_text("matte-black\n")
    assert current_theme_slug(state) == "matte-black"
    assert current_theme_slug(tmp_path / "missing") is None


def test_user_overlay_wins_over_stock(tmp_path: Path):
    user = tmp_path / "user"
    stock = tmp_path / "stock"
    (user / "catppuccin").mkdir(parents=True)
    (stock / "catppuccin").mkdir(parents=True)
    (user / "catppuccin" / "colors.toml").write_text('accent = "#ffffff"\n')
    (stock / "catppuccin" / "colors.toml").write_text(CATPPUCCIN)
    colors = load_omarchy_colors(
        "catppuccin", user_themes=user, stock_themes=stock
    )
    assert colors["accent"] == "#ffffff"
    # falls back to stock when no overlay
    colors = load_omarchy_colors(
        "catppuccin", user_themes=tmp_path / "nope", stock_themes=stock
    )
    assert colors["accent"] == "#89b4fa"


def test_theme_mapping():
    import tomllib

    theme = omarchy_textual_theme(tomllib.loads(CATPPUCCIN))
    assert theme is not None
    assert theme.dark is True
    assert theme.primary == "#89b4fa"
    assert theme.background == "#1e1e2e"
    assert theme.surface == "#313244"
    assert theme.error == "#f38ba8"


def test_theme_none_off_omarchy(tmp_path: Path):
    colors = load_omarchy_colors(
        None,
        state_file=tmp_path / "missing",
        user_themes=tmp_path / "a",
        stock_themes=tmp_path / "b",
    )
    assert colors is None
    assert omarchy_textual_theme({}) is None


def test_link_color_skips_hues_equal_to_foreground():
    from lorewrite.tui.theme import link_color

    assert link_color({"foreground": "#bebebe", "cyan": "#BEBEBE",
                       "blue": "#e68e0d", "orange": "#c63d3d"}) == "#e68e0d"
    assert link_color({"foreground": "#fff", "cyan": "#0ff"}) == "#0ff"
    assert link_color({"foreground": "#fff"}) is None


MATTE_BLACK = {
    "mode": "dark", "accent": "#e68e0d", "selection": "#2a2a2a",
    "background": "#121212", "lighter_background": "#1e1e1e",
    "foreground": "#bebebe", "red": "#D35F5F", "yellow": "#b91c1c",
    "orange": "#c63d3d", "green": "#FFC107", "cyan": "#bebebe",
    "blue": "#e68e0d", "magenta": "#D35F5F", "bright_red": "#B91C1C",
    "bright_yellow": "#b90a0a", "bright_green": "#FFC107",
    "bright_cyan": "#eaeaea", "bright_blue": "#f59e0b",
    "bright_magenta": "#B91C1C",
}


def test_distinct_color_on_matte_black_is_far_from_everything_it_could_blend_with():
    from lorewrite.tui.theme import distinct_color, link_color, rgb_distance

    link = link_color(MATTE_BLACK)
    avoid = [MATTE_BLACK["foreground"], link, MATTE_BLACK["orange"]]
    hue = distinct_color(MATTE_BLACK, avoid)
    for other in (*avoid, MATTE_BLACK["red"], MATTE_BLACK["magenta"],
                  MATTE_BLACK["accent"]):
        assert rgb_distance(hue, other) > 100, (hue, other)


def test_distinct_color_keeps_a_theme_hue_when_it_is_distinct():
    from lorewrite.tui.theme import distinct_color

    colors = {"foreground": "#ffffff", "orange": "#ff8800", "cyan": "#00ffff",
              "magenta": "#cc00cc", "green": "#00cc00"}
    avoid = ["#ffffff", "#00ffff", "#ff8800"]
    assert distinct_color(colors, avoid) in ("#cc00cc", "#00cc00")


def test_distinct_color_survives_empty_and_bad_palettes():
    from lorewrite.tui.theme import FALLBACK_HUES, distinct_color

    assert distinct_color({}, []) in FALLBACK_HUES
    assert distinct_color({"green": "not-a-color"}, [None, "zzz"]) in FALLBACK_HUES


def test_draft_tint_prefers_selection_then_lighter_background():
    from lorewrite.tui.theme import draft_tint

    assert draft_tint(MATTE_BLACK) == "#2a2a2a"
    assert draft_tint({"lighter_background": "#1e1e1e"}) == "#1e1e1e"
    assert draft_tint({}) is None


async def test_editor_draft_style_uses_distinct_hue_and_tint(tmp_path, monkeypatch):
    import lorewrite.tui.app as app_mod
    from lorewrite.core import drafts
    from lorewrite.core.project import Project
    from lorewrite.tui.app import LorewriteApp
    from lorewrite.tui.theme import link_color, rgb_distance

    monkeypatch.setattr(app_mod, "load_omarchy_colors", lambda: MATTE_BLACK)
    proj = Project.create(tmp_path / "n", title="T")
    scene = proj.manuscript_dir / "02-s.md"
    scene.write_text("# S\n\nStart " + drafts.wrap("ghost prose") + " end.\n")
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        st = app.editor.ai_style
        assert st.italic and st.bgcolor is not None
        assert st.bgcolor.get_truecolor().hex == "#2a2a2a"
        hue = st.color.get_truecolor().hex
        assert rgb_distance(hue, MATTE_BLACK["orange"]) > 100
        assert rgb_distance(hue, link_color(MATTE_BLACK)) > 100
        rendered = "".join(
            seg.text for seg in app.editor.render_line(2)
            if seg.style and seg.style.italic and seg.style.bgcolor)
        assert "ghost prose" in rendered
