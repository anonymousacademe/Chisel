"""Follow the Omarchy system theme.

Reads the current theme slug from ~/.local/state/omarchy/current/theme.name,
then its colors.toml — the user overlay in ~/.config/omarchy/themes/<slug>/
wins over the stock theme in /usr/share/omarchy/themes/<slug>/ (the same
precedence Omarchy itself uses). Returns None off-Omarchy so callers fall
back to Textual's built-in themes.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from textual.theme import Theme

STATE_FILE = Path.home() / ".local/state/omarchy/current/theme.name"
USER_THEMES = Path.home() / ".config/omarchy/themes"
STOCK_THEMES = Path("/usr/share/omarchy/themes")

THEME_NAME = "omarchy"


def current_theme_slug(state_file: Path = STATE_FILE) -> str | None:
    try:
        slug = state_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return slug or None


def load_omarchy_colors(
    slug: str | None = None,
    *,
    state_file: Path = STATE_FILE,
    user_themes: Path = USER_THEMES,
    stock_themes: Path = STOCK_THEMES,
) -> dict | None:
    """Colors for the current Omarchy theme, or None if unavailable."""
    slug = slug if slug is not None else current_theme_slug(state_file)
    if not slug:
        return None
    for base in (user_themes, stock_themes):
        colors_path = base / slug / "colors.toml"
        if colors_path.is_file():
            try:
                with colors_path.open("rb") as f:
                    return tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                return None
    return None


def omarchy_textual_theme(colors: dict | None = None) -> Theme | None:
    """Build a Textual theme from Omarchy colors. None if not on Omarchy."""
    if colors is None:
        colors = load_omarchy_colors()
    if not colors:
        return None
    return Theme(
        name=THEME_NAME,
        dark=colors.get("mode", "dark") == "dark",
        primary=colors.get("accent") or colors.get("blue"),
        secondary=colors.get("blue"),
        accent=colors.get("cyan") or colors.get("magenta"),
        warning=colors.get("yellow"),
        error=colors.get("red"),
        success=colors.get("green"),
        foreground=colors.get("foreground"),
        background=colors.get("background"),
        surface=colors.get("lighter_background") or colors.get("dark_background"),
        panel=colors.get("dark_background"),
        boost=colors.get("lighter_background"),
    )


def link_color(colors: dict) -> str | None:
    """Color for resolved links/mentions that actually stands out from prose.

    Some themes (e.g. matte-black) set cyan equal to the foreground, which
    would make plain-name mentions invisible; fall back through other hues,
    skipping the unresolved-link (orange) color.
    """
    taken = {(colors.get(k) or "").lower() for k in ("foreground", "orange")}
    for key in ("cyan", "blue", "accent", "green", "magenta"):
        value = colors.get(key)
        if value and value.lower() not in taken:
            return value
    return None


DRAFT_CANDIDATES = ("green", "yellow", "magenta", "bright_cyan", "blue", "cyan",
                    "bright_green", "bright_magenta", "bright_blue", "bright_yellow")
# last-resort hues for palettes with nothing distinct (e.g. matte-black is
# only reds, ambers and grays)
FALLBACK_HUES = ("#3fb8af", "#a78bfa", "#6fcf97", "#5ac8fa")
GOOD_DISTANCE = 110  # RGB distance at which a theme hue counts as distinct


def _rgb(color: str) -> tuple[int, int, int] | None:
    c = (color or "").strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return None
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return None


def rgb_distance(a: str, b: str) -> float:
    """Euclidean RGB distance between two hex colors (inf if unparsable)."""
    ra, rb = _rgb(a), _rgb(b)
    if ra is None or rb is None:
        return float("inf")
    return sum((x - y) ** 2 for x, y in zip(ra, rb)) ** 0.5


def distinct_color(colors: dict, avoid: list[str | None]) -> str:
    """The hue for pending AI drafts: among the theme's candidate hues the one
    farthest (in RGB) from every color in *avoid* (foreground, link color,
    unresolved color, ...). If no theme hue is clearly distinct, built-in
    fallback hues join the pool, so drafts never blend into links or prose."""
    avoid_rgb = [a for a in avoid if a and _rgb(a)]

    def score(color: str) -> float:
        return min((rgb_distance(color, a) for a in avoid_rgb),
                   default=float("inf"))

    theme = [colors[k] for k in DRAFT_CANDIDATES if _rgb(colors.get(k) or "")]
    best = max(theme, key=score, default=None)
    if best is not None and score(best) >= GOOD_DISTANCE:
        return best
    return max([*theme, *FALLBACK_HUES], key=score)


def draft_tint(colors: dict) -> str | None:
    """Subtle background tint for draft text: the theme's selection color,
    else its lighter background."""
    for key in ("selection", "lighter_background"):
        if _rgb(colors.get(key) or ""):
            return colors[key]
    return None
