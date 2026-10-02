"""Atmosphere preferences (typing sounds, ambience mix) and the editable radio-station list.

Both live in user settings (<state dir>/settings.json), never in a project. Nothing here
plays anything: the GUI starts audio only on the author's own click or keystroke, and a
station is only ever contacted after the author picks it.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from . import settings as user_settings

STATIONS_KEY = "radio_stations"
PREFS_KEY = "atmosphere"
MAX_STATIONS = 30
MAX_PRESETS = 20
SOMAFM_SUPPORT = "https://somafm.com/support/"

# Free, listener-supported SomaFM channels. Nothing plays until one is picked.
DEFAULT_STATIONS = [
    {"name": "Groove Salad (SomaFM)", "url": "https://ice1.somafm.com/groovesalad-128-mp3"},
    {"name": "Drone Zone (SomaFM)", "url": "https://ice1.somafm.com/dronezone-128-mp3"},
    {"name": "Deep Space One (SomaFM)", "url": "https://ice1.somafm.com/deepspaceone-128-mp3"},
    {"name": "Fluid (SomaFM): lo-fi, instrumental hip-hop", "url": "https://ice1.somafm.com/fluid-128-mp3"},
]

LAYERS = ("rain", "ocean", "wind", "forest", "fire", "cafe", "brown", "pink", "white", "drone")
TYPING_PACKS = ("typewriter", "clicky", "thocky")  # built-in synthesised packs (ids)


def valid_url(url: object) -> str:
    url = str(url or "").strip()
    if not url or len(url) > 300 or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("not a valid stream address")
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc or not parts.hostname:
        raise ValueError("A station address must start with http:// or https://")
    return url


def attribution(url: str) -> dict | None:
    host = (urlsplit(url).hostname or "").lower()
    if host == "somafm.com" or host.endswith(".somafm.com"):
        return {"via": "SomaFM", "text": "via SomaFM - listener-supported, consider supporting them",
                "link": SOMAFM_SUPPORT}
    return None


def clean_stations(rows: object) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError("stations must be a list")
    if len(rows) > MAX_STATIONS:
        raise ValueError(f"at most {MAX_STATIONS} stations")
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each station needs a name and an address")
        name = " ".join(str(row.get("name") or "").split())[:60]
        if not name:
            raise ValueError("each station needs a name")
        url = valid_url(row.get("url"))
        if url in seen:
            continue
        seen.add(url)
        out.append({"name": name, "url": url})
    return out


def get_stations() -> list[dict]:
    stored = user_settings.get(STATIONS_KEY)
    try:
        rows = clean_stations(stored) if stored is not None else [dict(s) for s in DEFAULT_STATIONS]
    except ValueError:
        rows = [dict(s) for s in DEFAULT_STATIONS]  # a hand-edited bad file never blocks the panel
    return [{**r, "attribution": attribution(r["url"])} for r in rows]


def set_stations(rows: object) -> list[dict]:
    """Save the list (None resets to the defaults)."""
    if rows is None:
        user_settings.set(STATIONS_KEY, None)
    else:
        user_settings.set(STATIONS_KEY, clean_stations(rows))
    return get_stations()


def _num(value: object, default: float, low: float = 0.0, high: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return round(max(low, min(high, float(value))), 3)


def _mix(value: object) -> dict:
    layers = value if isinstance(value, dict) else {}
    return {k: _num(layers[k], 0.0) for k in LAYERS if k in layers and _num(layers[k], 0.0) > 0}


def clean_prefs(raw: object) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    typing = raw.get("typing") if isinstance(raw.get("typing"), dict) else {}
    amb = raw.get("ambience") if isinstance(raw.get("ambience"), dict) else {}
    pack = str(typing.get("pack") or "typewriter")[:80]
    presets = {}
    if isinstance(amb.get("presets"), dict):
        for name, mix in list(amb["presets"].items())[:MAX_PRESETS]:
            name = " ".join(str(name).split())[:40]
            if name:
                presets[name] = _mix(mix)
    station = amb.get("station")
    try:
        station = valid_url(station) if station else None
    except ValueError:
        station = None
    return {
        "typing": {"on": bool(typing.get("on", False)), "pack": pack, "volume": _num(typing.get("volume"), 0.5)},
        "ambience": {"volume": _num(amb.get("volume"), 0.6), "layers": _mix(amb.get("layers")),
                     "loops": {str(k)[:80]: _num(v, 0.0) for k, v in list((amb.get("loops") or {}).items())[:20]
                               if isinstance(amb.get("loops"), dict) and _num(v, 0.0) > 0},
                     "station": station, "stationVolume": _num(amb.get("stationVolume"), 0.6),
                     "presets": presets},
    }


def get_prefs() -> dict:
    return clean_prefs(user_settings.get(PREFS_KEY))


def set_prefs(raw: object) -> dict:
    prefs = clean_prefs(raw)
    user_settings.set(PREFS_KEY, prefs)
    return prefs
