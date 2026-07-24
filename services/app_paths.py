"""Application path resolution — handles both source runs and frozen (PyInstaller
onedir) builds, and the user-relocatable writable data directory.

Three distinct roots
--------------------
* **resource_dir()** — read-only *bundled* assets (``locales/``, ``companion_mod/``,
  ``docs/``, icon).  Frozen → PyInstaller's ``sys._MEIPASS``; source → repo root.
* **exe_dir()** — the folder the program runs from (frozen → the ``.exe``'s folder;
  source → repo root).  Used for *auto-detection* (walking up to find the game)
  and legacy-file migration.
* **data_dir** — *writable* user data (config / logs / cache / backups).  Default
  is ``%APPDATA%\\AIInfluenceStoryTools`` for a shipped EXE, or the repo root in a
  source run (so development keeps writing beside the code as before).  The user
  can redirect it from the Settings tab; the choice is stored in a tiny pointer
  file (``data_location.txt``) next to the default location so it bootstraps
  before any settings are read.

All functions are dependency-free (os / sys / pathlib only) so services and the
regression scripts can import this without pulling in tkinter.
"""
from __future__ import annotations

from i18n import tr

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "AIInfluenceStoryTools"
POINTER_FILE = "data_location.txt"


def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def app_version() -> str:
    """Tool version from the bundled VERSION.txt (single source of truth,
    also used by build_exe.ps1 for the zip name)."""
    try:
        return (resource_dir() / "VERSION.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return "?"


def resource_dir() -> Path:
    """Read-only bundled-asset root (locales, companion_mod, docs, icon)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    # Source run: repo root is the parent of this services/ package.
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    """Folder the program runs from (the .exe's folder when frozen)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    """Where writable data lives by default.

    Frozen (shipped EXE) → ``%APPDATA%\\AIInfluenceStoryTools`` (always writable,
    survives upgrades).  Source run → repo root, preserving the historical
    "config/ and backups/ next to the code" development behaviour.
    """
    if is_frozen():
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / ("." + APP_NAME)
    return Path(__file__).resolve().parent.parent


def pointer_file() -> Path:
    """Bootstrap pointer that records a user-chosen data dir (if any)."""
    return default_data_dir() / POINTER_FILE


def resolve_data_dir() -> Path:
    """Effective writable data dir: a valid pointer override, else the default."""
    try:
        ptr = pointer_file()
        if ptr.is_file():
            text = ptr.read_text(encoding="utf-8").strip()
            if text:
                return Path(text)
    except Exception:
        pass
    return default_data_dir()


def ensure_data_dir() -> Path:
    """Resolve the data dir and make sure it exists."""
    d = resolve_data_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fall back to the default if the override is unwritable.
        d = default_data_dir()
        d.mkdir(parents=True, exist_ok=True)
    return d


def set_data_dir(new_path) -> tuple[bool, str]:
    """Persist *new_path* as the data dir via the pointer file (takes effect on
    next launch) and **migrate** the existing data there.

    Migration copies every item from the current data dir (config / logs /
    terminology cache / backups …) into the target, *without* clobbering items
    that already exist there.  The old copy is left in place (safe).  The target
    is created if missing.  Pass a falsy value to reset to the default location.

    Returns ``(ok, message)``.
    """
    try:
        default_data_dir().mkdir(parents=True, exist_ok=True)
        if not new_path:
            if pointer_file().exists():
                pointer_file().unlink()
            return (True, tr("已重設為預設資料目錄（重啟後生效）"))

        target = Path(new_path)
        target.mkdir(parents=True, exist_ok=True)
        old = resolve_data_dir()
        if old.resolve() != target.resolve():
            for item in old.iterdir():
                if item.name == POINTER_FILE:
                    continue  # the pointer lives with the default location
                dst = target / item.name
                if dst.exists():
                    continue  # never clobber existing data in the target
                try:
                    if item.is_dir():
                        shutil.copytree(item, dst)
                    else:
                        shutil.copy2(item, dst)
                except Exception:
                    pass
        pointer_file().write_text(str(target), encoding="utf-8")
        return (True, tr("資料目錄已設定、既有資料已遷移（重啟工具後生效）"))
    except Exception as e:
        return (False, tr("設定資料目錄失敗：{err}").format(err=e))
