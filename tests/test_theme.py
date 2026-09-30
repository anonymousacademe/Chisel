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
