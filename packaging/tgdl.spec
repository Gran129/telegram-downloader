# PyInstaller spec for Telegram Downloader (GUI).
# Build from the repository root:  pyinstaller --noconfirm packaging/tgdl.spec
# Note: PyInstaller runs a .spec with the working directory set to the spec's
# folder (packaging/), so relative paths below are relative to packaging/.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Make the repo root importable so collect_submodules("tgdl") works.
_ROOT = os.path.abspath(os.path.join(os.getcwd(), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

APP_NAME = "TelegramDownloader"

datas, binaries, hiddenimports = [], [], []
for pkg in ("telethon", "aiohttp", "dotenv", "tqdm", "rsa", "pyaes"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
hiddenimports += collect_submodules("tgdl")

# Bundle the window icon so the GUI can load it at runtime.
datas += [("../tgdl/assets/app.png", "tgdl/assets")]

block_cipher = None

a = Analysis(
    ["gui_main.py"],
    pathex=[".."],
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
    icon="app.ico",
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
