"""Auto-detection of Bannerlord installation and AIInfluence save_data paths."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional


# ── save_data folder identity ──────────────────────────────────────────
#
# Canonical rules for "is this save_data subfolder a campaign?".  Both the
# campaign list and the companion-mod heartbeat reader go through these, and
# the connector applies the same rules on the C# side (``FileContract``), so
# the tool and the mod can never disagree about what a campaign folder is.

RESERVED_SAVE_DATA_DIRS = frozenset({
    "storytools",      # our own mod→tool contract dir
    "_portrait_tmp",   # AI Influence 6.0+ Content Editor portrait capture buffer
})
"""save_data subfolders that are never campaigns."""


# A campaign id is the game's own random token: letters and digits only, and
# always the same length in practice (``aYqt3pB1kbNn``, ``hfOSV7HS5Nbj``,
# ``V7f0ShXEYJIX``, ``oRHQTILfrj64``).  The range is kept loose in case another
# Bannerlord version sizes them differently, but anything with a separator is
# out: a folder like ``aYqt3pB1kbNn_20260721_000746`` is somebody's backup copy,
# and the game itself would never load it as a campaign.
_CAMPAIGN_ID_RE = re.compile(r'^[A-Za-z0-9]{8,24}$')


def is_campaign_folder_name(name: str) -> bool:
    """True when *name* could be a campaign id.

    Name-only check — see :func:`looks_like_campaign_dir` to also verify the
    folder's contents.  Both are needed: a renamed backup can hold perfectly
    valid campaign data, and a fresh campaign can have a valid name before the
    mod has written everything into it.
    """
    if not name or name.startswith("_"):
        return False
    if name.lower() in RESERVED_SAVE_DATA_DIRS:
        return False
    return bool(_CAMPAIGN_ID_RE.match(name))


def looks_like_campaign_dir(path: Path) -> bool:
    """True when *path* carries AI Influence campaign data.

    A real campaign folder always has the diplomacy bundle or the per-campaign
    prompts tree.  Checking contents keeps unknown future scratch folders out
    without having to name them.
    """
    try:
        p = Path(path)
        if not p.is_dir():
            return False
        return (p / "aiinfluence_campaign_diplomacy.json").is_file() or (p / "prompts").is_dir()
    except Exception:
        return False


def _is_probably_bannerlord_root(p: Path) -> bool:
    """Check if a directory looks like a Bannerlord installation root."""
    return (p / "Bannerlord.exe").exists() or ((p / "bin").is_dir() and (p / "Modules").is_dir())


def _walk_up_to_root(start: Path, max_up: int = 10) -> Optional[Path]:
    """Walk up the directory tree looking for a Bannerlord root."""
    cur = start
    for _ in range(max_up + 1):
        if _is_probably_bannerlord_root(cur):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _try_modules(root: Path) -> Optional[Path]:
    """Check for AIInfluence save_data inside the Modules directory."""
    cand = root / "Modules" / "AIInfluence" / "save_data"
    return cand if cand.is_dir() else None


def _steam_libraryfolders(steam_root: Path) -> List[Path]:
    """Parse Steam's libraryfolders.vdf to find all library paths."""
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    libs: List[Path] = []
    if vdf.exists():
        try:
            txt = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s*"([^"]+)"', txt):
                libs.append(Path(m.group(1).replace('\\\\', '\\')))
        except Exception:
            pass
    libs.append(steam_root)
    uniq, seen = [], set()
    for p in libs:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp not in seen and rp.exists():
            seen.add(rp)
            uniq.append(rp)
    return uniq


def _try_workshop(lib_root: Path) -> Optional[Path]:
    """Search Steam Workshop content for AIInfluence save_data."""
    ws = lib_root / "steamapps" / "workshop" / "content" / "261550"
    if not ws.is_dir():
        return None
    try:
        for moddir in ws.iterdir():
            cand = moddir / "Modules" / "AIInfluence" / "save_data"
            if cand.is_dir():
                return cand
    except Exception:
        return None
    return None


def _try_common(lib_root: Path) -> Optional[Path]:
    """Search a Steam library's regular game install for AIInfluence save_data.

    ``lib_root`` is a Steam library folder (the parent of ``steamapps``).
    """
    cand = (lib_root / "steamapps" / "common" / "Mount & Blade II Bannerlord"
            / "Modules" / "AIInfluence" / "save_data")
    return cand if cand.is_dir() else None


def _steam_roots_from_registry() -> List[Path]:
    """Return Steam install root(s) recorded in the Windows registry (if any)."""
    roots: List[Path] = []
    try:
        import winreg  # Windows-only; harmless ImportError elsewhere
    except Exception:
        return roots
    for hive, key, value in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ):
        try:
            with winreg.OpenKey(hive, key) as k:
                val, _ = winreg.QueryValueEx(k, value)
            p = Path(str(val))
            if p.exists():
                roots.append(p)
        except OSError:
            continue
        except Exception:
            continue
    return roots


def _scan_steam_root_for_save_data(steam_root: Path) -> Optional[Path]:
    """Across every library of *steam_root*, look for AIInfluence save_data in a
    regular install first, then in workshop content."""
    libs = _steam_libraryfolders(steam_root)  # includes steam_root itself
    for lib in libs:
        hit = _try_common(lib)
        if hit:
            return hit
    for lib in libs:
        hit = _try_workshop(lib)
        if hit:
            return hit
    return None


def _try_gamepass() -> Optional[Path]:
    """Check common GamePass installation paths for AIInfluence."""
    cand = Path("C:/XboxGames/Mount & Blade II- Bannerlord/Content/Modules/AIInfluence/save_data")
    if cand.is_dir():
        return cand
    winapps = Path("C:/Program Files/WindowsApps")
    if winapps.exists():
        try:
            for child in winapps.glob("Mount*Bannerlord*"):
                cand2 = child / "Content" / "Modules" / "AIInfluence" / "save_data"
                if cand2.is_dir():
                    return cand2
        except Exception:
            pass
    return None


def find_bannerlord_root_from_save_data(save_data: Path) -> Optional[Path]:
    """Derive the Bannerlord installation root from a known *save_data* path.

    ``save_data`` is expected to be ``<BannerlordRoot>/Modules/AIInfluence/save_data``.
    Walking up 3 levels yields the BannerlordRoot candidate; it is validated with
    :func:`_is_probably_bannerlord_root` before being returned.

    Returns ``None`` when the path hierarchy doesn't match the expected depth.
    """
    if save_data is None:
        return None
    try:
        # save_data / .. = AIInfluence  / .. = Modules  / .. = BannerlordRoot
        candidate = Path(save_data).resolve().parents[2]
        if _is_probably_bannerlord_root(candidate):
            return candidate
    except (IndexError, Exception):
        pass
    return None


def find_proemconfig_exports_dir(
    script_dir: Path,
    save_data: Optional[Path] = None,
    override: Optional[Path] = None,
) -> Optional[Path]:
    """Return the ``ProemConfig/Profiles/Exports/IDs`` directory.

    Resolution order (first hit wins):

    1. *override* — user-supplied path from settings (``exports_ids_dir``).
    2. Derived from *save_data* — walk up to BannerlordRoot, then append
       ``Modules/ProemConfig/Profiles/Exports/IDs``.
    3. Walk up from *script_dir* until a Bannerlord root is found, then
       append the ProemConfig sub-path.

    Returns ``None`` when no candidate directory exists on disk.
    """
    _proemconfig_sub = Path("Modules") / "ProemConfig" / "Profiles" / "Exports" / "IDs"

    # 1) User override
    if override is not None:
        p = Path(override)
        if p.is_dir():
            return p

    # 2) Derive from save_data
    if save_data is not None:
        root = find_bannerlord_root_from_save_data(save_data)
        if root:
            cand = root / _proemconfig_sub
            if cand.is_dir():
                return cand

    # 3) Walk up from script_dir
    root = _walk_up_to_root(Path(script_dir))
    if root:
        cand = root / _proemconfig_sub
        if cand.is_dir():
            return cand

    return None


def find_save_data(script_dir: Path) -> Optional[Path]:
    """Auto-detect the AIInfluence save_data directory via multiple strategies.

    Works regardless of where the tool itself lives — it scans the Steam
    libraries (from the registry and common locations) for the regular game
    install, not just the directory tree above the tool.  Order:

    1. Walk up from *script_dir* (tool placed inside the game tree).
    2. Steam install found via the registry → scan its libraries
       (regular ``common/`` install first, then workshop content).
    3. Steam in common locations → same scan.
    4. Xbox Game Pass install.
    """
    # 1) Tool sitting inside the game tree.
    root = _walk_up_to_root(script_dir)
    if root:
        m = _try_modules(root)
        if m:
            return m

    # 2)+3) Every Steam root we can find → scan all its libraries.
    steam_roots: List[Path] = list(_steam_roots_from_registry())
    pf86 = os.environ.get("ProgramFiles(x86)")
    if pf86:
        steam_roots.append(Path(pf86) / "Steam")
    steam_roots += [
        Path("C:/Program Files (x86)/Steam"),
        Path.home() / "AppData/Local/Steam",
        Path("C:/Steam"),
    ]
    # Also honour a steamapps ancestor of the tool, if any.
    if root:
        for parent in [root] + list(root.parents):
            if parent.name.lower() == "steamapps":
                steam_roots.append(parent.parent)
                break

    seen: set = set()
    for sr in steam_roots:
        try:
            key = sr.resolve()
        except Exception:
            key = sr
        if key in seen or not sr.exists():
            continue
        seen.add(key)
        hit = _scan_steam_root_for_save_data(sr)
        if hit:
            return hit

    # 4) Game Pass.
    gp = _try_gamepass()
    if gp:
        return gp
    return None
