# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — onedir build of AI Influence: Story Master.

Distribution model: ZIP-and-run (onedir), no installer. Build via build_exe.ps1.

Bundled (read-only) assets land beside the exe in `_internal/` and are resolved
at runtime through services.app_paths.resource_dir(); writable user data
(config / logs / cache / backups) lives under %APPDATA%\\AIInfluenceStoryTools
(see services.app_paths.default_data_dir).
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Read-only assets to ship inside the bundle (src, dest-in-bundle).
datas = [
    ('locales', 'locales'),            # terminology JSONs (i18n base library)
    ('assets', 'assets'),              # app icon + splash image
    ('VERSION.txt', '.'),              # single source for the About-tab version
]
# NOTE: internal dev docs (docs/) are intentionally NOT bundled — the shipped
# EXE carries only runtime assets. User-facing notes live in README_*.txt.
# ttkbootstrap ships theme data + dynamically-loaded submodules.
datas += collect_data_files('ttkbootstrap')
hiddenimports = collect_submodules('ttkbootstrap')
# Pillow: memory-page / event images. PIL._tkinter_finder is the hidden import
# ImageTk needs to bind to Tk; PyInstaller doesn't always pick it up.
hiddenimports += ['PIL', 'PIL.ImageTk', 'PIL._tkinter_finder']

a = Analysis(
    ['StoryMaster.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scripts', 'PyInstaller', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Startup splash (bootloader shows it before Python/UI is ready; main() closes
# it via pyi_splash once the window is up). Covers the few-second cold start.
splash = Splash(
    'assets/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    always_on_top=False,            # don't force the splash above other windows
)

exe = EXE(
    pyz,
    a.scripts,
    splash,                         # splash target in the exe
    exclude_binaries=True,          # onedir: binaries go in COLLECT below
    name='StoryMaster',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX off — fewer AV false positives
    console=False,                  # windowed (no console window)
    disable_windowed_traceback=False,
    icon='assets/app.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,                # splash runtime (Tk) binaries
    strip=False,
    upx=False,
    upx_exclude=[],
    name='StoryMaster',
)
