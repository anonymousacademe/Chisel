"""Atmosphere: typing sounds and ambience (user data dir + user settings, no project), and the native file dialog."""

from __future__ import annotations

from ..core import atmosphere, soundpacks
from ..core.desktop import open_path as desktop_open_path
from ._bridge import bridge


class AtmosphereMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    def _pick_file(self, save: bool, name: str = "", types: tuple[str, ...] = ()) -> str | None:
        """Native open/save dialog (only in the real window)."""
        if self._window is None:
            raise RuntimeError("This needs the desktop window")
        import webview

        kind = getattr(webview, "FileDialog", None)
        mode = (getattr(kind, "SAVE", None) if save else getattr(kind, "OPEN", None))
        if mode is None:
            mode = webview.SAVE_DIALOG if save else webview.OPEN_DIALOG
        picked = self._window.create_file_dialog(mode, save_filename=name, file_types=types)
        if not picked:
            return None
        return str(picked if isinstance(picked, str) else picked[0])

    @bridge
    def get_atmosphere(self) -> dict:
        """Saved sound preferences, the radio stations, and the custom packs and loops found."""
        return {"prefs": atmosphere.get_prefs(), "stations": atmosphere.get_stations(),
                "packs": soundpacks.list_packs(), "loops": soundpacks.list_loops(),
                "soundsDir": str(soundpacks.sounds_dir()), "ambienceDir": str(soundpacks.ambience_dir())}

    @bridge
    def set_atmosphere(self, prefs: dict) -> dict:
        return {"prefs": atmosphere.set_prefs(prefs)}

    @bridge
    def set_stations(self, stations: list | None) -> dict:
        """Save the station list (None = back to the defaults). http(s) addresses only."""
        return {"stations": atmosphere.set_stations(stations)}

    @bridge
    def sound_pack(self, pack: str) -> dict:
        """One custom pack's sounds as data URLs, by key class."""
        return soundpacks.read_pack(pack)

    @bridge
    def ambience_loop(self, name: str) -> dict:
        return {"dataUrl": soundpacks.read_loop(name)}

    @bridge
    def import_sound_pack(self, path: str | None = None) -> dict:
        """Add a pack from a .zip (picked in a dialog; ``path`` is for tests and the dev server).
        The zip is validated first; nothing is written if any check fails."""
        if path is None:
            path = self._pick_file(False, types=("Sound pack (*.zip)",))
            if path is None:
                return {"imported": None, "packs": soundpacks.list_packs()}
        return {"imported": soundpacks.import_pack(path), "packs": soundpacks.list_packs()}

    @bridge
    def export_sound_pack(self, pack: str, dest: str | None = None) -> dict:
        """Zip a pack to share it (save dialog; ``dest`` is for tests and the dev server)."""
        if dest is None:
            dest = self._pick_file(True, f"{soundpacks._plain(pack)}.zip", ("Sound pack (*.zip)",))
            if dest is None:
                return {"path": None}
        return {"path": str(soundpacks.export_pack(pack, dest))}

    @bridge
    def open_sounds_folder(self, which: str = "sounds") -> dict:
        """Open the sounds/ or ambience/ folder in the file manager (created if missing); only
        from a click in the real window."""
        folder = soundpacks.ambience_dir() if which == "ambience" else soundpacks.sounds_dir()
        folder.mkdir(parents=True, exist_ok=True)
        opened = self._window is not None and desktop_open_path(folder)
        return {"path": str(folder), "opened": bool(opened)}
