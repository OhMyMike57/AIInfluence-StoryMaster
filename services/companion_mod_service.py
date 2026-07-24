"""Core-module status service (AI Influence: Story Master).

Since v1.1.0 the *module* is the product's main body and the editor ships inside
its ``Tool/`` subfolder — installed and updated through the normal Bannerlord
module workflow (unzip into ``Modules``, tick in the launcher).  The editor no
longer installs or updates the module, so the old bundled-payload / deploy
machinery is gone; what remains is a status check: is the module present in the
game's ``Modules`` folder, and does its version match this editor?

The 關於 tab's「模組狀態檢查」and the status banner both read this.
"""
from __future__ import annotations

from i18n import tr

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import re


MOD_ID = "AIInfluence_StoryMaster"
VERSION_FILE = "module_version.txt"


# ── Path helpers ───────────────────────────────────────────────────────

def installed_mod_dir(game_dir: Path) -> Path:
    return Path(game_dir) / "Modules" / MOD_ID


# ── Version reading / comparison ───────────────────────────────────────

def _read_version_file(version_txt: Path) -> Optional[str]:
    try:
        if version_txt.is_file():
            return version_txt.read_text(encoding="utf-8-sig").strip() or None
    except Exception:
        return None
    return None


def parse_version(s: Optional[str]) -> Tuple[int, ...]:
    """Parse ``'v0.3.2'`` / ``'0.3.2'`` → ``(0, 3, 2)``.  Unparseable → ``(0,)``."""
    if not s:
        return (0,)
    nums = re.findall(r"\d+", s)
    return tuple(int(x) for x in nums) if nums else (0,)


def compare_versions(a: Optional[str], b: Optional[str]) -> int:
    """Return ``-1`` if ``a < b``, ``0`` if equal, ``1`` if ``a > b`` (numeric)."""
    pa, pb = parse_version(a), parse_version(b)
    n = max(len(pa), len(pb))
    pa = pa + (0,) * (n - len(pa))
    pb = pb + (0,) * (n - len(pb))
    return (pa > pb) - (pa < pb)


def installed_version(game_dir: Optional[Path]) -> Optional[str]:
    if not game_dir:
        return None
    return _read_version_file(installed_mod_dir(game_dir) / VERSION_FILE)


# ── Status ─────────────────────────────────────────────────────────────

@dataclass
class ModuleStatus:
    state: str                  # no_game / not_installed / version_match / version_mismatch
    installed: Optional[str]    # module version found in the game Modules folder
    editor: Optional[str]       # this editor's version (same-numbered bundle)
    module_dir: Optional[Path]  # where the module is (or would be)
    message: str                # short human-readable label

    @property
    def ok(self) -> bool:
        return self.state == "version_match"


def module_status(game_dir: Optional[Path], editor_version: Optional[str]) -> ModuleStatus:
    """Is the core module installed, and does its version match this editor?

    The module and the editor ship as one same-versioned bundle, so a mismatch
    means the player updated one half only (e.g. replaced the module folder but
    kept an old editor shortcut elsewhere).
    """
    if not game_dir or not Path(game_dir).is_dir():
        return ModuleStatus("no_game", None, editor_version, None,
                            tr("尚未設定遊戲位置"))
    target = installed_mod_dir(game_dir)
    inst = installed_version(game_dir)
    if inst is None:
        return ModuleStatus("not_installed", None, editor_version, target,
                            tr("未偵測到核心模組"))
    if compare_versions(inst, editor_version) == 0:
        return ModuleStatus("version_match", inst, editor_version, target,
                            tr("核心模組運作正常"))
    return ModuleStatus("version_mismatch", inst, editor_version, target,
                        tr("核心模組與編輯器版本不一致"))
