"""Character-database service for the 資料庫 tab.

Unlike :func:`services.character_service.build_characters_and_indexes` (which
lists only the heroes the player has actually interacted with — those that have
a save JSON), this module builds rows for **every real-NPC hero** the companion
mod exported, joined with whether a save file currently exists.  It also holds
the file-management operations (generate / delete / backup / batch-generate).

Data sources (all from the Story Master export, via the terminology payload):
  * ``hero_attrs``  — {StringId: {name, clan, culture, occupation, age, gender,
                       alive, spouse, is_lord/wanderer/notable/clan_leader,
                       is_minor_faction_hero, is_child, is_template, …}}
  * ``clan_attrs``  — {clan_id: {name, kingdom, …}}  (kingdom is the
                       authoritative faction link; see character_service)
  * name maps       — kingdoms / clans / cultures {id: name}

A "real NPC" excludes template heroes (wanderer/notable blueprints such as
"盾女").  Troops (諾德戰士) and generic townsfolk are CharacterObjects, not
heroes, so they never appear here.
"""
from __future__ import annotations

import datetime
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.character_service import pristine_character_template

# Bannerlord: HeroComesOfAge = 18. Used as the minor/adult cutoff when the
# export predates the explicit ``is_child`` flag.
ADULT_AGE = 18

# Filename convention the AI Influence mod uses for a character save:
#   "<full name> (<StringId>).json"
# The full name joins given/family name with a middle dot "·" (U+00B7), e.g.
# "張恩·霍恩巴 (lord_6_1).json".  The companion mod exports the name with a
# SPACE separator ("張恩 霍恩巴"), so we substitute spaces → "·" to reproduce the
# game's filename.  Verified against real saves: 67/69 reproduced exactly; the
# 2 misses are nameless minor-faction NPCs whose name carries a "…的<faction>"
# clause the game drops (negligible — those are rarely pre-generated).
_NAME_JOIN = "·"  # ·
_FILE_ID_RE = re.compile(r"\(([^()]+)\)\s*$")
# Characters Windows forbids in filenames; replaced so a write can't fail.
_ILLEGAL_FS = re.compile(r'[\\/:*?"<>|]')


def character_filename(name: str, string_id: str) -> str:
    """Return the save filename for a hero, matching the game's convention."""
    base = (name or string_id).strip().replace(" ", _NAME_JOIN)
    return _ILLEGAL_FS.sub("_", f"{base} ({string_id})") + ".json"


def build_file_index(campaign_dir: Path, loader: Callable[[Path], Any]) -> Dict[str, Path]:
    """Map ``StringId -> save-file path`` for the character JSONs in *campaign_dir*.

    StringId is read from the file's ``StringId`` field (authoritative); the
    filename's ``(id)`` suffix is only a fallback when the file can't be read.
    """
    index: Dict[str, Path] = {}
    if not campaign_dir or not Path(campaign_dir).is_dir():
        return index
    for f in Path(campaign_dir).glob("*.json"):
        sid = None
        d = loader(f)
        if isinstance(d, dict) and "ConversationHistory" in d:
            sid = str(d.get("StringId") or "").strip() or None
        if not sid:
            m = _FILE_ID_RE.search(f.stem)
            if m:
                sid = m.group(1).strip()
        if sid:
            index.setdefault(sid, f)
    return index


def _kingdom_of(clan_id: Optional[str], a: Dict[str, Any], clan_attrs: Dict[str, Any]) -> Optional[str]:
    """Faction = the clan's kingdom (authoritative); fall back to hero field."""
    if clan_id and isinstance(clan_attrs.get(clan_id), dict):
        k = clan_attrs[clan_id].get("kingdom")
        if k:
            return k
    return a.get("kingdom")


def build_database_rows(
    hero_attrs: Dict[str, Any],
    clan_attrs: Dict[str, Any],
    *,
    kingdom_names: Optional[Dict[str, str]] = None,
    clan_names: Optional[Dict[str, str]] = None,
    culture_names: Optional[Dict[str, str]] = None,
    file_index: Optional[Dict[str, Path]] = None,
    exclude_templates: bool = True,
) -> List[Dict[str, Any]]:
    """Build one display row per real-NPC hero from the export."""
    hero_attrs = hero_attrs or {}
    clan_attrs = clan_attrs or {}
    kingdom_names = kingdom_names or {}
    clan_names = clan_names or {}
    culture_names = culture_names or {}
    file_index = file_index or {}

    rows: List[Dict[str, Any]] = []
    for sid, a in hero_attrs.items():
        if not isinstance(a, dict):
            continue
        # The player is not a manageable NPC. ``is_player`` exists from mod
        # v0.7.0; the StringId check covers older exports.
        if a.get("is_player") or str(sid) == "main_hero":
            continue
        if exclude_templates and a.get("is_template"):
            continue
        clan_id = a.get("clan")
        kingdom_id = _kingdom_of(clan_id, a, clan_attrs)
        age = a.get("age")
        age = int(age) if isinstance(age, (int, float)) else None
        is_child = bool(a.get("is_child")) or (age is not None and age < ADULT_AGE)
        cult = a.get("culture")
        rows.append({
            "StringId": str(sid),
            "Name": a.get("name") or str(sid),
            "Clan": clan_id,
            "ClanName": clan_names.get(clan_id, clan_id) if clan_id else "",
            "Kingdom": kingdom_id,
            "KingdomName": kingdom_names.get(kingdom_id, kingdom_id) if kingdom_id else "",
            "Culture": cult,
            "CultureName": culture_names.get(cult, cult) if cult else "",
            "Occupation": a.get("occupation"),
            "Age": age,
            "Gender": a.get("gender"),
            "Married": bool(a.get("spouse")),
            "Alive": bool(a.get("alive", True)),
            "IsLord": bool(a.get("is_lord")),
            "IsWanderer": bool(a.get("is_wanderer")),
            "IsNotable": bool(a.get("is_notable")),
            "IsClanLeader": bool(a.get("is_clan_leader")),
            "IsChild": is_child,
            "HasFile": str(sid) in file_index,
            "File": file_index.get(str(sid)),
        })
    return rows


# ── File operations ────────────────────────────────────────────────────────

def generate_character_file(
    campaign_dir: Path,
    row: Dict[str, Any],
    writer: Callable[[Path, dict], bool],
) -> Optional[Path]:
    """Create a pristine (fully-reset) blank save JSON for *row*'s hero.

    Returns the path on success, or None (write failed / already exists).
    Carries identity fields so the file is a valid 5.0.x character the game
    can load — equivalent to a freshly-reset character.
    """
    sid = str(row.get("StringId") or "").strip()
    if not sid:
        return None
    name = (row.get("Name") or sid).strip()
    path = Path(campaign_dir) / character_filename(name, sid)
    if path.exists():
        return None
    existing = {
        "Name": name,
        "StringId": sid,
        "Gender": row.get("Gender") or "male",
        "InformationAccessLevel": "medium",
        "player_bind_string_id": "main_hero",
    }
    data = pristine_character_template(existing)
    return path if writer(path, data) else None


def delete_character_file(path: Path) -> bool:
    try:
        Path(path).unlink()
        return True
    except Exception:
        return False


def backup_character_file(path: Path, backup_base: Path, campaign_id: str) -> Optional[Path]:
    """Copy a character JSON into ``<backup_base>/character/<campaign_id>/``."""
    try:
        src = Path(path)
        dest_dir = Path(backup_base) / "character" / (campaign_id or "unknown")
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = dest_dir / f"{src.stem}_{ts}.json"
        shutil.copy2(src, dest)
        return dest
    except Exception:
        return None


def batch_generate(
    campaign_dir: Path,
    rows: List[Dict[str, Any]],
    writer: Callable[[Path, dict], bool],
    *,
    exclude_minor: bool = True,
    exclude_dead: bool = False,
    exclude_notable: bool = False,
    exclude_wanderer: bool = False,
) -> Dict[str, int]:
    """Generate blank saves for rows without an existing file.

    Always skips rows that already have a file (never overwrites). Returns
    ``{"created", "skipped_existing", "skipped_excluded"}``.
    """
    created = skipped_existing = skipped_excluded = 0
    for r in rows:
        if r.get("HasFile"):
            skipped_existing += 1
            continue
        if exclude_minor and r.get("IsChild"):
            skipped_excluded += 1
            continue
        if exclude_dead and not r.get("Alive"):
            skipped_excluded += 1
            continue
        if exclude_notable and r.get("IsNotable"):
            skipped_excluded += 1
            continue
        if exclude_wanderer and r.get("IsWanderer"):
            skipped_excluded += 1
            continue
        if generate_character_file(campaign_dir, r, writer):
            created += 1
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_excluded": skipped_excluded,
    }


def count_generatable(
    rows: List[Dict[str, Any]],
    *,
    exclude_minor: bool = True,
    exclude_dead: bool = False,
    exclude_notable: bool = False,
    exclude_wanderer: bool = False,
) -> int:
    """How many rows would be generated under the given exclusions (no writes)."""
    n = 0
    for r in rows:
        if r.get("HasFile"):
            continue
        if exclude_minor and r.get("IsChild"):
            continue
        if exclude_dead and not r.get("Alive"):
            continue
        if exclude_notable and r.get("IsNotable"):
            continue
        if exclude_wanderer and r.get("IsWanderer"):
            continue
        n += 1
    return n
