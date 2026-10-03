# PyInstaller spec for Chisel (one spec, OS branches). Run it through
# packaging/build.py. Output: dist/Chisel/ (onedir) holding two executables,
# Chisel (desktop, no console window) and lorewrite (terminal), and on macOS
# dist/Chisel.app.
import os
import pkgutil
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
WORK = Path(workpath)
sys.path.insert(0, str(SRC))
from lorewrite import __version__  # noqa: E402

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")
ICONS = ROOT / "gui" / "src-tauri" / "icons"
BUNDLE_ID = "io.github.mishkin.lorewriter"

datas = [
    (str(SRC / "lorewrite" / "gui" / "web"), "lorewrite/gui/web"),
    (str(SRC / "lorewrite" / "core" / "export" / "fonts"), "lorewrite/core/export/fonts"),
]
binaries = []
hiddenimports = collect_submodules("lorewrite")  # layouts and export writers load by name


def everything(package):
    """Data files, binaries and every submodule of *package* (lazy imports)."""
    d, b, h = collect_all(package)
    datas.extend(d)
    binaries.extend(b)
    hiddenimports.extend(h)


for package in ("textual", "rich", "spellchecker", "pyphen", "reportlab", "certifi",
                "openai", "webview"):
    everything(package)
# textual[syntax]: the tree-sitter grammars are separate packages
for mod in pkgutil.iter_modules():
    if mod.name.startswith("tree_sitter"):
        everything(mod.name)
hiddenimports += collect_submodules("keyring")
for dist in ("textual", "keyring", "platformdirs", "pywebview"):
    datas += copy_metadata(dist)

if WINDOWS:
    hiddenimports += ["keyring.backends.Windows", "win32ctypes.core", "webview.platforms.edgechromium",
                      "clr", "clr_loader"]
    everything("clr_loader")
    everything("pythonnet")
elif MACOS:
    hiddenimports += ["keyring.backends.macOS", "webview.platforms.cocoa", "objc", "Foundation",
                      "AppKit", "WebKit", "Quartz", "Security", "UniformTypeIdentifiers",
                      "PyObjCTools"]
else:
    hiddenimports += ["keyring.backends.SecretService", "keyring.backends.libsecret",
                      "keyring.backends.kwallet", "secretstorage", "jeepney",
                      "webview.platforms.qt", "qtpy", "qtpy.QtCore", "qtpy.QtGui",
                      "qtpy.QtWidgets", "qtpy.QtWebEngineWidgets", "qtpy.QtWebChannel",
                      "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel"]

excludes = ["tkinter", "pytest", "textual_dev", "matplotlib", "IPython", "notebook",
            "PyQt5", "PyQt6", "PySide2", "gi"]

a = Analysis(
    [str(Path(SPECPATH) / "entry.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)


def slim_qt(entries):
    """Drop the Qt modules, QML and translations that QtWebEngineWidgets never
    touches (the hooks pull in most of PySide6: ~500 MB; the render self-test on
    the built bundle guards this list)."""
    import re
    unused = (r"3D\w*|Charts\w*|DataVisualization\w*|Graphs\w*|Location\w*|Multimedia\w*|"
              r"Quick3D\w*|Labs\w*|Sensors\w*|Spatial\w*|Test\w*|Designer\w*|Help\w*|"
              r"Bluetooth\w*|Nfc\w*|RemoteObjects\w*|Scxml\w*|SerialPort\w*|TextToSpeech\w*|"
              r"VirtualKeyboard\w*|Sql\w*|Pdf\w*|ShaderTools\w*|StateMachine\w*|HttpServer\w*|"
              r"WebSockets\w*|WebView\w*|Positioning\w*Quick")
    drop = re.compile(
        rf"(^|/)(libQt6|Qt)({unused})(\.so[.\d]*|\.abi3\.so|\.pyi?|\.dll|\.pyd)?$"
        r"|PySide6/Qt/qml/|PySide6/Qt/plugins/(multimedia|sqldrivers|designer|renderers|sceneparsers|"
        r"geometryloaders|position|sensors|texttospeech|virtualkeyboard|qmltooling|qmllint|"
        r"assetimporters|canbus|scxmldatamodel|help)/|PySide6/(include|typesystems|glue|scripts)/")
    keep = []
    for entry in entries:
        dest = entry[0].replace("\\", "/")
        if drop.search(dest):
            continue
        if "qtwebengine_locales/" in dest and not dest.endswith("en-US.pak"):
            continue
        if "PySide6/Qt/translations/" in dest and "qtwebengine_locales" not in dest:
            continue
        keep.append(entry)
    return keep


if LINUX:
    a.binaries = slim_qt(a.binaries)
    a.datas = slim_qt(a.datas)
pyz = PYZ(a.pure)

version_file = None
if WINDOWS:
    parts = (__version__.split(".") + ["0", "0", "0"])[:3] + ["0"]
    tup = ", ".join(p if p.isdigit() else "0" for p in parts)
    WORK.mkdir(parents=True, exist_ok=True)
    version_file = str(WORK / "version_info.txt")
    Path(version_file).write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Mishkin'),
      StringStruct('FileDescription', 'Chisel'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'Chisel'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Mishkin. MIT licence.'),
      StringStruct('OriginalFilename', 'Chisel.exe'),
      StringStruct('ProductName', 'Chisel'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")

icon = str(ICONS / "icon.ico") if WINDOWS else str(ICONS / "icon.icns") if MACOS else None
arch = os.environ.get("LOREWRITE_TARGET_ARCH") or None  # macOS: arm64 / x86_64 / universal2

gui_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Chisel", console=False,
              icon=icon, version=version_file, target_arch=arch, upx=False)
tui_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lorewrite", console=True,
              icon=icon, version=version_file, target_arch=arch, upx=False)
coll = COLLECT(gui_exe, tui_exe, a.binaries, a.datas, name="Chisel", upx=False)

if MACOS:
    app = BUNDLE(
        coll, name="Chisel.app", icon=icon, bundle_identifier=BUNDLE_ID, version=__version__,
        info_plist={
            "CFBundleName": "Chisel",
            "CFBundleDisplayName": "Chisel",
            "CFBundleExecutable": "Chisel",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "Copyright (c) 2026 Mishkin. MIT licence.",
        })
