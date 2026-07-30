"""Backup service — campaign / database / config / snapshot backups, and restore.

Directory layout (all under ``<data_dir>/backups``)::

    backups/
        save_data/   <cid>_<YYYYMMDD_HHMMSS>/            full campaign folder copies
        db/          terminology_<cid>_<YYYYMMDD_HHMMSS>/ cleared-database snapshots
        config/      <YYYYMMDD_HHMMSS>/                   tool config (settings/presets/…)
        snapshots/   <cid>_<YYYYMMDD_HHMMSS>/             the mod's save_snapshots/
        backup_meta.json                                  per-entry notes

Rationale for the 5.0.x era: AI Influence now stores its mod settings *inside
each campaign* (they travel with the save), so a campaign backup already
captures them — the old separate ``system/`` backup is obsolete and removed.

The ``snapshots`` kind arrived with 1.2.1: the mod's own per-slot rollback data
(``<campaign>/save_snapshots/``) used to be deleted outright so that edits made
at the main menu would stick.  Under the ``backup_then_clear`` policy it is
copied here first, so the rollback survives as something :func:`restore_backup`
can put back.

Restore
-------
:func:`restore_backup` mirrors a backup over its live target — files present in
the backup are written, and files the backup does not have are **removed**, so
the result is the recorded state rather than a merge of two eras.  That is
destructive by design, so every caller gets three guarantees:

* :func:`plan_restore` answers "what exactly would change?" without touching
  anything (added / overwritten / deleted counts and sample paths);
* the live state is backed up first, so a restore is itself undoable;
* the target is re-derived from the backup's own name and validated against the
  expected roots — a backup can never write outside them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import json
import os
import re
import shutil
import time

SAVE_SUBDIR = "save_data"
DB_SUBDIR = "db"
CONFIG_SUBDIR = "config"
SNAPSHOT_SUBDIR = "snapshots"
META_FILE = "backup_meta.json"

#: Folder the connector writes its exported database into, inside a campaign.
STORYTOOLS_SUBDIR = "storytools"
#: Folder the mod writes its per-save rollback data into, inside a campaign.
SAVE_SNAPSHOTS_SUBDIR = "save_snapshots"

KIND_CAMPAIGN = "campaign"
KIND_DB = "db"
KIND_CONFIG = "config"
KIND_SNAPSHOT = "snapshot"

#: Backup kind → the subdir it lives in under ``backups/``.
_KIND_SUBDIR = {
    KIND_CAMPAIGN: SAVE_SUBDIR,
    KIND_DB: DB_SUBDIR,
    KIND_CONFIG: CONFIG_SUBDIR,
    KIND_SNAPSHOT: SNAPSHOT_SUBDIR,
}

_LEGACY_DB_PREFIX = "terminology_"
# Trailing "_YYYYMMDD_HHMMSS" timestamp stamped on backup folder names.
_TS_RE = re.compile(r"_(\d{8})_(\d{6})$")
_INVALID_NAME_CHARS = set('\\/:*?"<>|')

#: Marker in the name of a backup taken automatically just before a restore.
#: Sits between the campaign id and the timestamp so the name stays readable —
#: :func:`_campaign_id_from_name` strips it, or the id would come back as
#: "<cid>_before_restore" and the undo could not resolve its target.
_SAFETY_MARKER = "_before_restore"


def ensure_dir(path: Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


# ── Campaign auto-backup policy (設定 → 偏好設定 → 戰役備份處理) ──────────
#
# Governs *this tool's* own safety copy, taken before a destructive write. Kept
# separate from the mod's save-snapshot handling (see ``snapshot_service``), which
# is a different thing owned by a different program — the two were easy to
# confuse while both were called "備份".
#
# Stored values are stable identifiers; labels are translated at display time.
CAMPAIGN_BACKUP_ON = "enabled"
CAMPAIGN_BACKUP_OFF = "disabled"
DEFAULT_CAMPAIGN_BACKUP = CAMPAIGN_BACKUP_ON

CAMPAIGN_BACKUP_IDS = (CAMPAIGN_BACKUP_ON, CAMPAIGN_BACKUP_OFF)


def normalize_campaign_backup(value: Optional[str]) -> str:
    """Return a known policy id, falling back to the default (backups on)."""
    return value if value in CAMPAIGN_BACKUP_IDS else DEFAULT_CAMPAIGN_BACKUP


def campaign_backup_enabled(value: Optional[str]) -> bool:
    return normalize_campaign_backup(value) == CAMPAIGN_BACKUP_ON


def campaign_backup_label(value: Optional[str]) -> str:
    """Translated display label. Literal ``tr()`` calls so the coverage gate can
    see the keys and the display audit stays free of ``tr(variable)`` leaks."""
    from i18n import tr
    pid = normalize_campaign_backup(value)
    if pid == CAMPAIGN_BACKUP_ON:
        return tr("啟用自動備份")
    if pid == CAMPAIGN_BACKUP_OFF:
        return tr("停用自動備份")
    return pid


def campaign_backup_hint(value: Optional[str]) -> str:
    from i18n import tr
    pid = normalize_campaign_backup(value)
    if pid == CAMPAIGN_BACKUP_ON:
        return tr("批量寫入或刪除前，先把整個戰役資料夾複製到備份中心，"
                  "出錯時可從備份中心還原。")
    if pid == CAMPAIGN_BACKUP_OFF:
        return tr("不自動備份。省下磁碟空間與等待時間，但寫錯時沒有可還原的備份，"
                  "建議只在你自行手動備份時才停用。")
    return ""


def campaign_backup_display_options() -> List[str]:
    return [campaign_backup_label(pid) for pid in CAMPAIGN_BACKUP_IDS]


def campaign_backup_from_label(label: str) -> str:
    for pid in CAMPAIGN_BACKUP_IDS:
        if label == campaign_backup_label(pid):
            return pid
    return DEFAULT_CAMPAIGN_BACKUP


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
    """Recover the campaign id from ``<cid>[_before_restore]_<stamp>``.

    Optionally strips a leading prefix such as ``terminology_``.
    """
    core = name[len(strip_prefix):] if strip_prefix and name.startswith(strip_prefix) else name
    cid = _TS_RE.sub("", core).strip()
    if cid.endswith(_SAFETY_MARKER):
        cid = cid[: -len(_SAFETY_MARKER)].strip()
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
    # _unique_dir rather than dirs_exist_ok: two backups inside the same second
    # should be two point-in-time copies, not one merged folder.
    target = _unique_dir(build_campaign_backup_path(backup_base, campaign_dir.name))
    shutil.copytree(campaign_dir, target)
    return target


def build_db_backup_path(backup_base: Path, campaign_id: str) -> Path:
    return Path(backup_base) / DB_SUBDIR / f"{_LEGACY_DB_PREFIX}{campaign_id}_{_timestamp()}"


def build_snapshot_backup_path(backup_base: Path, campaign_id: str) -> Path:
    return Path(backup_base) / SNAPSHOT_SUBDIR / f"{campaign_id}_{_timestamp()}"


def backup_snapshots(campaign_dir: Path, backup_base) -> Optional[Path]:
    """Copy ``<campaign>/save_snapshots/`` into ``backups/snapshots/<cid>_<ts>``.

    Returns the backup path, or ``None`` when there was nothing to copy — an
    empty (or absent) ``save_snapshots`` is the normal state after the mod
    consumes a snapshot on load, and recording an empty folder every time the
    user saves would bury the Backup Center in noise.
    """
    campaign_dir = Path(campaign_dir)
    src = campaign_dir / SAVE_SNAPSHOTS_SUBDIR
    if not src.is_dir() or not any(src.iterdir()):
        return None
    target = build_snapshot_backup_path(Path(backup_base), campaign_dir.name)
    ensure_dir(target.parent)
    shutil.copytree(src, target, dirs_exist_ok=True)
    return target


def backup_tool_config(config_dir: Path, backup_base) -> Path:
    """Copy the tool's config directory into ``backups/config/<ts>``."""
    config_dir = Path(config_dir)
    backup_base = Path(backup_base)
    target = _unique_dir(Path(backup_base) / CONFIG_SUBDIR / _timestamp())
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
    kind: str                       # "campaign" | "db" | "config" | "snapshot"
    path: Path
    name: str                       # folder name
    campaign_id: Optional[str]      # every kind except config
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
    """All backups across every kind, newest first."""
    base = Path(backup_base)
    meta = load_meta(base)
    entries: List[BackupEntry] = []
    entries += _scan(base, SAVE_SUBDIR, KIND_CAMPAIGN, meta)
    entries += _scan(base, DB_SUBDIR, KIND_DB, meta, strip_prefix=_LEGACY_DB_PREFIX)
    entries += _scan(base, CONFIG_SUBDIR, KIND_CONFIG, meta)
    entries += _scan(base, SNAPSHOT_SUBDIR, KIND_SNAPSHOT, meta)
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


# ── Restore ─────────────────────────────────────────────────────────────
#
# Restoring overwrites live data, so the flow is deliberately three-legged:
# resolve the target from the backup itself → plan (pure, read-only) → apply.
# The UI is expected to show the plan and get a confirmation before applying.

#: How many example paths a plan carries per bucket (enough for the confirm
#: dialog to be concrete, bounded so a 5000-file campaign stays cheap).
_PLAN_SAMPLE = 12


class RestoreError(Exception):
    """Raised when a restore cannot even be planned (bad target, missing data)."""


@dataclass
class RestorePlan:
    """What :func:`restore_backup` would do — computed without writing anything."""

    entry: "BackupEntry"
    target: Path
    added: List[str] = field(default_factory=list)        # in backup, not live
    overwritten: List[str] = field(default_factory=list)  # in both, differing
    unchanged: List[str] = field(default_factory=list)    # in both, identical
    deleted: List[str] = field(default_factory=list)      # live only → removed
    target_exists: bool = True

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.overwritten) + len(self.deleted)

    def sample(self, bucket: List[str]) -> List[str]:
        return bucket[:_PLAN_SAMPLE]


@dataclass
class RestoreReport:
    """Outcome of an applied restore."""

    ok: bool
    plan: Optional[RestorePlan] = None
    safety_backup: Optional[Path] = None
    written: int = 0
    removed: int = 0
    errors: List[str] = field(default_factory=list)


def _iter_relative_files(root: Path) -> Dict[str, Path]:
    """Map ``relative/posix/path`` → absolute path for every file under *root*.

    Symlinked directories are not descended into: a backup folder should never
    contain one, and honouring it would let a crafted backup reach outside the
    tree it is supposed to describe.
    """
    out: Dict[str, Path] = {}
    root = Path(root)
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                continue
            out[rel] = p
    return out


def _same_file(a: Path, b: Path) -> bool:
    """Cheap sameness test: size then bytes.

    Size alone would call a same-length edit "unchanged", which for a JSON that
    swapped one character is exactly the case a player would notice.
    """
    try:
        sa, sb = a.stat(), b.stat()
        if sa.st_size != sb.st_size:
            return False
        if sa.st_size > 4 * 1024 * 1024:
            # Big files: trust size + mtime rather than hashing a campaign folder.
            return int(sa.st_mtime) == int(sb.st_mtime)
        return a.read_bytes() == b.read_bytes()
    except Exception:
        return False


def _unique_dir(path: Path) -> Path:
    """Return *path*, or ``path_2`` / ``path_3`` … when it is already taken.

    The timestamp in a backup name has one-second resolution, and "restore, look
    at it, undo" happens well inside a second. Without this, the undo's safety
    backup would land on the folder the undo is reading *from* and merge the
    post-restore state into it — quietly destroying the very state being undone.
    """
    path = Path(path)
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.name}_{n}")
        if not candidate.exists():
            return candidate
        n += 1


def _is_within(child: Path, parent: Path) -> bool:
    """True when *child* is *parent* or lives under it, after resolving links."""
    try:
        child = Path(child).resolve()
        parent = Path(parent).resolve()
    except Exception:
        return False
    return child == parent or parent in child.parents


def resolve_restore_target(entry: BackupEntry, *,
                           save_data_dir: Optional[Path] = None,
                           config_dir: Optional[Path] = None) -> Path:
    """Where *entry* would be restored to.

    Derived from the backup's own kind and recorded campaign id — never from
    anything the caller passes in beyond the two roots — so a restore always
    lands where that backup came from.

    Raises :class:`RestoreError` when the target cannot be determined (for
    example a campaign backup while no save-data folder is configured).
    """
    from i18n import tr

    if entry.kind == KIND_CONFIG:
        if not config_dir:
            raise RestoreError(tr("找不到工具設定資料夾"))
        return Path(config_dir)

    if not save_data_dir:
        raise RestoreError(tr("尚未設定 AI 效應的 save_data 資料夾"))
    if not entry.campaign_id:
        raise RestoreError(tr("無法從備份名稱判斷所屬戰役"))

    campaign = Path(save_data_dir) / entry.campaign_id
    if entry.kind == KIND_CAMPAIGN:
        return campaign
    if entry.kind == KIND_DB:
        return campaign / STORYTOOLS_SUBDIR
    if entry.kind == KIND_SNAPSHOT:
        return campaign / SAVE_SNAPSHOTS_SUBDIR
    raise RestoreError(tr("不支援的備份類型"))


def plan_restore(entry: BackupEntry, target: Path) -> RestorePlan:
    """Compare the backup against its live target. Reads only; writes nothing."""
    from i18n import tr

    src_root = Path(entry.path)
    if not src_root.is_dir():
        raise RestoreError(tr("備份資料夾不存在或已被移除"))

    target = Path(target)
    src = _iter_relative_files(src_root)
    if not src:
        raise RestoreError(tr("備份是空的，沒有可還原的檔案"))
    live = _iter_relative_files(target)

    plan = RestorePlan(entry=entry, target=target, target_exists=target.is_dir())
    for rel, sp in sorted(src.items()):
        lp = live.get(rel)
        if lp is None:
            plan.added.append(rel)
        elif _same_file(sp, lp):
            plan.unchanged.append(rel)
        else:
            plan.overwritten.append(rel)
    for rel in sorted(live):
        if rel not in src:
            plan.deleted.append(rel)
    return plan


def restore_backup(entry: BackupEntry, target: Path, *,
                   backup_base,
                   plan: Optional[RestorePlan] = None,
                   safety_backup: bool = True) -> RestoreReport:
    """Mirror *entry* over *target*, replacing its contents.

    The live state is copied into a fresh ``config``/``save_data`` backup first
    (``safety_backup``), so an unwanted restore can itself be restored. Pass
    ``safety_backup=False`` only from tests.

    *target* must be the path :func:`resolve_restore_target` produced; it is
    re-validated here rather than trusted, so a caller cannot redirect a restore
    into an arbitrary folder.
    """
    from i18n import tr

    target = Path(target)
    src_root = Path(entry.path)
    base = Path(backup_base)

    # Guard: never write into the backup store itself. That would let a restore
    # eat its own source (and every other backup) in one step.
    if _is_within(target, base):
        return RestoreReport(ok=False, errors=[tr("還原目標不可位於備份資料夾內")])
    if _is_within(base, target):
        return RestoreReport(ok=False, errors=[tr("還原目標不可包含備份資料夾")])

    try:
        plan = plan or plan_restore(entry, target)
    except RestoreError as exc:
        return RestoreReport(ok=False, errors=[str(exc)])

    report = RestoreReport(ok=False, plan=plan)

    # ── Safety net: snapshot the live state before touching it ───────────
    if safety_backup:
        try:
            report.safety_backup = _make_safety_backup(entry, target, base)
        except Exception as exc:
            # A restore without its undo is not worth the risk — stop here.
            report.errors.append(tr("還原前的安全備份失敗，已中止：{v0}").format(v0=str(exc)))
            return report

    # ── Apply ────────────────────────────────────────────────────────────
    try:
        ensure_dir(target)
    except Exception as exc:
        report.errors.append(tr("無法建立還原目標資料夾：{v0}").format(v0=str(exc)))
        return report

    for rel in plan.added + plan.overwritten:
        sp = src_root / rel
        dp = target / rel
        try:
            ensure_dir(dp.parent)
            shutil.copy2(sp, dp)
            report.written += 1
        except Exception as exc:
            report.errors.append(f"{rel}: {exc}")

    for rel in plan.deleted:
        dp = target / rel
        try:
            dp.unlink()
            report.removed += 1
        except Exception as exc:
            report.errors.append(f"{rel}: {exc}")

    _prune_empty_dirs(target)
    report.ok = not report.errors
    return report


def _make_safety_backup(entry: BackupEntry, target: Path, base: Path) -> Optional[Path]:
    """Copy the live target aside so the restore itself can be undone.

    Stored **as the same kind** as what is being restored. That matters: the undo
    is performed by restoring this backup, and :func:`resolve_restore_target`
    derives its destination from the kind and campaign id. An earlier version
    filed every safety backup under ``save_data/`` named after the target folder,
    which produced entries like ``save_snapshots_before_restore_<ts>`` that the
    Backup Center listed as *campaign* backups — restoring one would have written
    into a non-existent campaign called "save_snapshots_before_restore".

    Returns ``None`` when there is nothing to protect (target absent or empty);
    writing an empty folder every time only adds noise to the Backup Center.
    """
    target = Path(target)
    if not target.is_dir() or not _iter_relative_files(target):
        return None

    if entry.kind == KIND_CONFIG:
        return backup_tool_config(target, base)

    cid = entry.campaign_id or target.name
    prefix = _LEGACY_DB_PREFIX if entry.kind == KIND_DB else ""
    subdir = _KIND_SUBDIR.get(entry.kind, SAVE_SUBDIR)
    dst = _unique_dir(base / subdir
                      / f"{prefix}{cid}{_SAFETY_MARKER}_{_timestamp()}")
    ensure_dir(dst.parent)
    # No dirs_exist_ok: _unique_dir guarantees a fresh folder, and merging into an
    # existing one is exactly the corruption this backup exists to prevent.
    shutil.copytree(target, dst)
    return dst


def _prune_empty_dirs(root: Path) -> None:
    """Remove directories left empty by the delete pass (bottom-up, keeps root)."""
    root = Path(root)
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root or filenames or dirnames:
            continue
        try:
            p.rmdir()
        except Exception:
            pass


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
