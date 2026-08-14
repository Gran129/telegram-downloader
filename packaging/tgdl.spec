# PyInstaller spec for Telegram Downloader (GUI).
# Build from the repository root:  pyinstaller --noconfirm packaging/tgdl.spec
# Note: PyInstaller runs a .spec with the working directory set to the spec's
# folder (packaging/), so relative paths below are relative to packaging/.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Resolve everything from the spec's own directory (absolute), NOT the current
# working directory: PyInstaller does not reliably chdir to the spec folder on
# every platform, and CI invokes it from the repo root. SPECPATH is injected by
# PyInstaller and points at this file's directory.
try:
    _HERE = os.path.abspath(SPECPATH)  # noqa: F821 - provided by PyInstaller
except NameError:  # pragma: no cover - fallback when run oddly
    _HERE = os.path.abspath(os.getcwd())
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))

# Make the repo root importable so collect_submodules("tgdl") works.
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Fail the build loudly if tgdl cannot be found (rather than shipping a broken
# exe that raises ModuleNotFoundError at runtime).
import importlib

try:
    importlib.import_module("tgdl.gui")
except Exception as exc:  # pragma: no cover - build-time guard
    raise SystemExit(f"[tgdl.spec] cannot import tgdl from {_ROOT!r}: {exc}")

APP_NAME = "TelegramDownloader"

datas, binaries, hiddenimports = [], [], []
for pkg in ("telethon", "aiohttp", "dotenv", "tqdm", "rsa", "pyaes", "PIL"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
hiddenimports += collect_submodules("tgdl")

# Bundle the window icon so the GUI can load it at runtime.
datas += [(os.path.join(_ROOT, "tgdl", "assets", "app.png"), os.path.join("tgdl", "assets"))]

block_cipher = None

a = Analysis(
    [os.path.join(_HERE, "gui_main.py")],
    pathex=[_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windows version resource (embeds file metadata to reduce AV false positives).
# The version file is a Windows-only PE resource; skip it on other platforms so
# the spec still builds there for validation.
_version_file = os.path.join(_HERE, "version_info.txt")
exe_version = _version_file if sys.platform.startswith("win") and os.path.exists(_version_file) else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed GUI app (no console window)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(_HERE, "app.ico"),
    version=exe_version,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
