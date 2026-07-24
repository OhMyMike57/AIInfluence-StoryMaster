"""Backup service — campaign / database / tool-config backups under one root.

Directory layout (all under ``<data_dir>/backups``)::

    backups/
        save_data/   <cid>_<YYYYMMDD_HHMMSS>/            full campaign folder copies
        db/          terminology_<cid>_<YYYYMMDD_HHMMSS>/ cleared-database snapshots
        config/      <YYYYMMDD_HHMMSS>/                   tool config (settings/presets/…)
        backup_meta.json                                  per-entry notes

Rationale for the 5.0.x era: AI Influence now stores its mod settings *inside
each campaign* (they travel with the save), so a campaign backup already
captures them — the old separate ``system/`` backup is obsolete and removed.
The three kinds a user cares about now are: the game's campaign save, this
tool's own config, and the connector's exported database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json
import re
import shutil
import time

SAVE_SUBDIR = "save_data"
DB_SUBDIR = "db"
CONFIG_SUBDIR = "config"
META_FILE = "backup_meta.json"

_LEGACY_DB_PREFIX = "terminology_"
# Trailing "_YYYYMMDD_HHMMSS" timestamp stamped on backup folder names.
_TS_RE = re.compile(r"_(\d{8})_(\d{6})$")
_INVALID_NAME_CHARS = set('\\/:*?"<>|')


def ensure_dir(path: Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


# ── Timestamp / name helpers ────────────────────────────────────────────

def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _parse_stamp(name: str) -> Optional[datetime]:
    m = _TS_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _campaign_id_from_name(name: str, *, strip_prefix: str = "") -> Optional[str]:
    """Recover the campaign id from ``<cid>_<stamp>`` (optionally stripping a
    leading prefix such as ``terminology_``)."""
    core = name[len(strip_prefix):] if strip_prefix and name.startswith(strip_prefix) else name
    cid = _TS_RE.sub("", core).strip()
    return cid or None


# ── Backup creation ─────────────────────────────────────────────────────

def build_campaign_backup_path(backup_base: Path, campaign_name: str) -> Path:
    return Path(backup_base) / SAVE_SUBDIR / f"{campaign_name}_{_timestamp()}"


def backup_campaign_dir(campaign_dir: Path, backup_base) -> Path:
    """Copy the whole campaign folder into ``backups/save_data/<cid>_<ts>``.

    Both arguments are coerced to ``Path`` so passing a plain string (as some
    older call sites did) no longer silently fails.
    """
    campaign_dir = Path(campaign_dir)
    backup_base = Path(backup_base)
    ensure_dir(backup_base)
    target = build_campaign_backup_path(backup_base, campaign_dir.name)
    # dirs_exist_ok guards the rare same-second collision.
    shutil.copytree(campaign_dir, target, dirs_exist_ok=True)
    return target


def build_db_backup_path(backup_base: Path, campaign_id: str) -> Path:
    return Path(backup_base) / DB_SUBDIR / f"{_LEGACY_DB_PREFIX}{campaign_id}_{_timestamp()}"


def backup_tool_config(config_dir: Path, backup_base) -> Path:
    """Copy the tool's config directory into ``backups/config/<ts>``."""
    config_dir = Path(config_dir)
    backup_base = Path(backup_base)
    target = Path(backup_base) / CONFIG_SUBDIR / _timestamp()
    ensure_dir(target)
    if config_dir.is_dir():
        for item in config_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.copytree(item, target / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target / item.name)
            except Exception:
                pass
    return target


# ── Backup listing ──────────────────────────────────────────────────────

@dataclass
class BackupEntry:
    kind: str                       # "campaign" | "db" | "config"
    path: Path
    name: str                       # folder name
    campaign_id: Optional[str]      # campaign/db only
    timestamp: Optional[datetime]   # parsed from name, else folder mtime
    note: str = ""
    size: Optional[int] = None      # bytes; filled lazily by the UI

    @property
    def sort_key(self) -> float:
        return self.timestamp.timestamp() if self.timestamp else 0.0


def _folder_mtime(p: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime)
    except Exception:
        return None


def _scan(base: Path, subdir: str, kind: str, meta: Dict[str, dict],
          *, strip_prefix: str = "") -> List[BackupEntry]:
    root = Path(base) / subdir
    if not root.is_dir():
        return []
    out: List[BackupEntry] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        cid = _campaign_id_from_name(p.name, strip_prefix=strip_prefix) if kind != "config" else None
        ts = _parse_stamp(p.name) or _folder_mtime(p)
        note = meta.get(f"{subdir}/{p.name}", {}).get("note", "")
        out.append(BackupEntry(kind=kind, path=p, name=p.name,
                               campaign_id=cid, timestamp=ts, note=note))
    return out


def list_backups(backup_base) -> List[BackupEntry]:
    """All backups across the three kinds, newest first."""
    base = Path(backup_base)
    meta = load_meta(base)
    entries: List[BackupEntry] = []
    entries += _scan(base, SAVE_SUBDIR, "campaign", meta)
    entries += _scan(base, DB_SUBDIR, "db", meta, strip_prefix=_LEGACY_DB_PREFIX)
    entries += _scan(base, CONFIG_SUBDIR, "config", meta)
    entries.sort(key=lambda e: e.sort_key, reverse=True)
    return entries


# ── Metadata (notes) ────────────────────────────────────────────────────

def _meta_path(base: Path) -> Path:
    return Path(base) / META_FILE


def load_meta(backup_base) -> Dict[str, dict]:
    p = _meta_path(Path(backup_base))
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_meta(backup_base, meta: Dict[str, dict]) -> bool:
    try:
        base = Path(backup_base)
        ensure_dir(base)
        _meta_path(base).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _meta_key(entry: BackupEntry) -> str:
    return f"{entry.path.parent.name}/{entry.name}"


def set_note(backup_base, entry: BackupEntry, note: str) -> bool:
    meta = load_meta(backup_base)
    key = _meta_key(entry)
    note = (note or "").strip()
    if note:
        meta.setdefault(key, {})["note"] = note
    else:
        meta.pop(key, None)
    entry.note = note
    return save_meta(backup_base, meta)


def valid_backup_name(name: str) -> bool:
    name = (name or "").strip()
    return bool(name) and not (set(name) & _INVALID_NAME_CHARS)


def rename_backup(backup_base, entry: BackupEntry, new_name: str) -> tuple[bool, str]:
    """Rename a backup folder within its own subdir. Returns ``(ok, message)``."""
    new_name = (new_name or "").strip()
    if not valid_backup_name(new_name):
        return (False, "invalid_name")
    if new_name == entry.name:
        return (True, "unchanged")
    dst = entry.path.parent / new_name
    if dst.exists():
        return (False, "exists")
    try:
        old_key = _meta_key(entry)
        entry.path.rename(dst)
    except Exception as e:
        return (False, str(e))
    # Move any note to the new key.
    meta = load_meta(backup_base)
    if old_key in meta:
        meta[f"{dst.parent.name}/{new_name}"] = meta.pop(old_key)
        save_meta(backup_base, meta)
    entry.path = dst
    entry.name = new_name
    return (True, "ok")


def delete_backup(backup_base, entry: BackupEntry) -> bool:
    try:
        key = _meta_key(entry)
        shutil.rmtree(entry.path)
    except Exception:
        return False
    meta = load_meta(backup_base)
    if meta.pop(key, None) is not None:
        save_meta(backup_base, meta)
    return True


# ── Legacy migration ────────────────────────────────────────────────────

def migrate_legacy(backup_base) -> int:
    """Move root-level ``terminology_*`` folders into ``db/``.

    Older builds wrote cleared-database snapshots straight under ``backups/``;
    this tidies them into the new ``db/`` subdir. The obsolete ``system/``
    subdir is deliberately left untouched (not listed, not deleted). Returns
    the number of folders moved.
    """
    base = Path(backup_base)
    if not base.is_dir():
        return 0
    db_root = base / DB_SUBDIR
    moved = 0
    for p in base.iterdir():
        if not p.is_dir() or not p.name.startswith(_LEGACY_DB_PREFIX):
            continue
        ensure_dir(db_root)
        dst = db_root / p.name
        n = 1
        while dst.exists():
            dst = db_root / f"{p.name}_{n}"
            n += 1
        try:
            shutil.move(str(p), str(dst))
            moved += 1
        except Exception:
            pass
    return moved
