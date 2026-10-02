#!/usr/bin/env python3
"""Build the installable LoreWriter apps. One entry point for CI and for local use.

    python packaging/build.py bundle     # PyInstaller onedir -> dist/LoreWriter[.app]
    python packaging/build.py selftest   # run --self-test on the built bundle
    python packaging/build.py package    # installer / DMG / AppImage / zip -> dist/release/
    python packaging/build.py all        # the three above

Needs the web UI built first (``npm run build`` in gui/ writes src/lorewrite/gui/web/)
and the build dependencies (packaging/requirements-build.txt). Nothing here signs
or uploads anything. See docs/dev/packaging.md.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pyinstaller"
RELEASE = DIST / "release"
BUNDLE = DIST / "LoreWriter"
ICON_PNG = ROOT / "gui" / "src-tauri" / "icons" / "icon.png"
APPIMAGETOOL_URL = ("https://github.com/AppImage/appimagetool/releases/download/continuous/"
                    "appimagetool-x86_64.AppImage")


def version() -> str:
    ns: dict = {}
    exec((ROOT / "src" / "lorewrite" / "__init__.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def say(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def run(cmd: list[str | Path], **kw) -> None:
    say(" ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def mac_arch() -> str:
    return os.environ.get("LOREWRITE_TARGET_ARCH") or platform.machine().replace("aarch64", "arm64")


# -- bundle ------------------------------------------------------------------------


def bundle() -> None:
    if not (ROOT / "src" / "lorewrite" / "gui" / "web" / "index.html").is_file():
        sys.exit("the web UI is not built: run `npm ci && npm run build` in gui/ first")
    for folder in (DIST / "LoreWriter", DIST / "LoreWriter.app", WORK):
        if folder.exists():
            shutil.rmtree(folder)
    run([sys.executable, "-m", "PyInstaller", PKG / "lorewriter.spec", "--noconfirm", "--clean",
         "--distpath", DIST, "--workpath", WORK])


def bundle_exes() -> tuple[Path, Path]:
    """(desktop executable, terminal executable) inside the built bundle."""
    exe = ".exe" if sys.platform == "win32" else ""
    if sys.platform == "darwin":
        macos = DIST / "LoreWriter.app" / "Contents" / "MacOS"
        return macos / "LoreWriter", macos / "lorewrite"
    return BUNDLE / f"LoreWriter{exe}", BUNDLE / f"lorewrite{exe}"


# -- self test ---------------------------------------------------------------------


def selftest(gui: Path | None = None, tui: Path | None = None, extra: list[str] | None = None) -> None:
    """--self-test of both executables; the windowed one writes a report file
    (a Windows GUI exe has no stdout)."""
    gui, tui = (gui, tui) if gui and tui else bundle_exes()
    for exe in (tui, gui):
        report = ROOT / "build" / f"selftest-{exe.stem}.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.unlink(missing_ok=True)
        say(f"self-test: {exe}")
        proc = subprocess.run([str(exe), *(extra or []), "--self-test", "--report", str(report)],
                              capture_output=True, text=True, timeout=600)
        sys.stdout.write(proc.stdout[-4000:] if proc.stdout else "")
        sys.stderr.write(proc.stderr[-2000:] if proc.stderr else "")
        if not report.is_file():
            sys.exit(f"{exe} wrote no self-test report (exit {proc.returncode})")
        data = json.loads(report.read_text(encoding="utf-8"))
        for check in data["checks"]:
            print(f"   {'ok  ' if check['ok'] else 'FAIL'} {check['name']}: {check['detail']}")
        if proc.returncode != 0 or not data["ok"]:
            sys.exit(f"self-test failed for {exe}")
        if not data["frozen"]:
            sys.exit(f"{exe} did not run as a frozen app")


# -- packaging ---------------------------------------------------------------------


def package() -> None:
    RELEASE.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        package_windows()
    elif sys.platform == "darwin":
        package_macos()
    else:
        package_linux()


def zip_dir(src: Path, out: Path, top: str) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(src.rglob("*")):
            z.write(path, Path(top) / path.relative_to(src))


def package_windows() -> None:
    ver = version()
    zip_dir(BUNDLE, RELEASE / f"LoreWriter-{ver}-windows-portable.zip", "LoreWriter")
    iscc = shutil.which("iscc") or next(
        (p for p in (r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                     r"C:\Program Files\Inno Setup 6\ISCC.exe") if Path(p).is_file()), None)
    if iscc is None:
        sys.exit("Inno Setup (ISCC.exe) not found: choco install innosetup")
    run([iscc, f"/DAppVersion={ver}", f"/DSourceDir={BUNDLE}", f"/DOutputDir={RELEASE}",
         f"/DIconFile={ROOT / 'gui' / 'src-tauri' / 'icons' / 'icon.ico'}",
         f"/DLicenseFile={ROOT / 'LICENSE'}", PKG / "lorewriter.iss"])


def package_macos() -> None:
    ver, arch = version(), mac_arch()
    stage = ROOT / "build" / "dmg"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    run(["ditto", DIST / "LoreWriter.app", stage / "LoreWriter.app"])
    (stage / "Applications").symlink_to("/Applications")
    (stage / "READ ME FIRST.txt").write_text(
        "LoreWriter is not signed yet.\n\nDrag LoreWriter.app to Applications. The first time, "
        "right-click (or control-click) it and choose Open, then Open again.\nIf macOS still "
        "refuses: xattr -dr com.apple.quarantine /Applications/LoreWriter.app\n",
        encoding="utf-8")
    out = RELEASE / f"LoreWriter-{ver}-macos-{arch}.dmg"
    out.unlink(missing_ok=True)
    run(["hdiutil", "create", "-volname", "LoreWriter", "-srcfolder", stage, "-ov",
         "-format", "UDZO", out])


def appimagetool() -> Path:
    tool = ROOT / "build" / "appimagetool-x86_64.AppImage"
    if not tool.is_file():
        say(f"downloading appimagetool: {APPIMAGETOOL_URL}")
        tool.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(APPIMAGETOOL_URL, tool)
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return tool


APPRUN = """#!/bin/sh
# LoreWriter AppImage launcher: the desktop app by default; the terminal app when run
# through a link named "lorewrite" or as `LoreWriter.AppImage --terminal [options]`.
HERE="$(dirname "$(readlink -f "$0")")"
APP="$HERE/usr/lib/LoreWriter"
case "$(basename "${ARGV0:-}")" in
  lorewrite) exec "$APP/lorewrite" "$@" ;;
esac
if [ "$1" = "--terminal" ]; then shift; exec "$APP/lorewrite" "$@"; fi
exec "$APP/LoreWriter" "$@"
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=LoreWriter
GenericName=Fiction writing
Comment=Write fiction in plain Markdown, with linked characters and places
Exec=LoreWriter %F
Icon=lorewriter
Terminal=false
Categories=Office;TextEditor;
Keywords=fiction;novel;writing;markdown;
X-AppImage-Version={version}
"""


def package_linux() -> None:
    ver = version()
    appdir = ROOT / "build" / "LoreWriter.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "lib").mkdir(parents=True)
    shutil.copytree(BUNDLE, appdir / "usr" / "lib" / "LoreWriter", symlinks=True)
    apprun = appdir / "AppRun"
    apprun.write_text(APPRUN, encoding="utf-8", newline="\n")
    apprun.chmod(0o755)
    (appdir / "LoreWriter.desktop").write_text(DESKTOP.format(version=ver), encoding="utf-8",
                                               newline="\n")
    shutil.copy(ICON_PNG, appdir / "lorewriter.png")
    (appdir / ".DirIcon").symlink_to("lorewriter.png")
    share = appdir / "usr" / "share"
    (share / "applications").mkdir(parents=True)
    shutil.copy(appdir / "LoreWriter.desktop", share / "applications" / "LoreWriter.desktop")
    icons = share / "icons" / "hicolor" / "512x512" / "apps"
    icons.mkdir(parents=True)
    shutil.copy(ICON_PNG, icons / "lorewriter.png")
    out = RELEASE / f"LoreWriter-{ver}-x86_64.AppImage"
    out.unlink(missing_ok=True)
    env = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    run([appimagetool(), "--appimage-extract-and-run", appdir, out], env=env)
    out.chmod(0o755)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("stage", choices=["bundle", "selftest", "package", "all"])
    parser.add_argument("--gui", type=Path, help="selftest: the desktop executable to test "
                        "(default: the one in dist/; e.g. an installed copy)")
    parser.add_argument("--tui", type=Path, help="selftest: the terminal executable to test")
    args = parser.parse_args()
    if args.stage in ("bundle", "all"):
        bundle()
    if args.stage in ("selftest", "all"):
        selftest(args.gui, args.tui)
    if args.stage in ("package", "all"):
        package()


if __name__ == "__main__":
    main()
