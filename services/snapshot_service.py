"""AI Influence 6.0 save-snapshot handling (``<campaign>/save_snapshots/``).

Why this exists
---------------
From 6.0.1 the mod snapshots its whole campaign folder on every game save, and
**restores that snapshot automatically on load** — clearing the live folder first
and consuming (deleting) the snapshot afterwards.  So the normal player flow
"save → quit to main menu → edit with this tool → load" silently throws the edits
away: the snapshot taken at save time is copied back over them, and files the
tool *created* are removed by the clear step.

Two folders are excluded from the mod's copy, and are therefore safe to edit
regardless: ``prompts/`` (player description, rules, world_data) and
``save_snapshots/`` itself.

Countermeasure
--------------
Deleting the snapshot folders puts the load path back on its "no snapshot for
this slot" branch, where the live campaign data is used as-is.  That is the same
state a campaign reaches after loading once (snapshots are consumed), so it is
not an exotic condition for the mod.

Cost: the player loses the mod's ability to roll its data back when loading an
*older* save slot — i.e. behaviour returns to AI Influence 5.x.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

SNAPSHOTS_DIR_NAME = "save_snapshots"
SNAPSHOT_META_NAME = "snapshot_meta.json"

# ── Handling policy (設定 → 偏好設定 → 存檔備份處理) ──────────────────────
#
# Only one policy ships today; the setting exists as a dropdown because a second
# one is already planned (writing edits into the newest snapshot instead of
# deleting it — see PLAN_6X_ADAPTATION Backlog B-1).  Keep the stored value a
# stable identifier and the label a translated string, so adding a policy later
# never breaks saved settings.
POLICY_AUTO_CLEAR = "auto_clear"
DEFAULT_POLICY = POLICY_AUTO_CLEAR

POLICY_IDS = (POLICY_AUTO_CLEAR,)


def normalize_policy(value: Optional[str]) -> str:
    """Return a known policy id, falling back to the default."""
    return value if value in POLICY_IDS else DEFAULT_POLICY


def policy_label(value: Optional[str]) -> str:
    """Translated display label for a policy id.

    Written as literal ``tr()`` calls rather than a lookup table so the i18n
    coverage gate can see the keys and the display audit stays free of
    ``tr(variable)`` leaks.
    """
    from i18n import tr
    pid = normalize_policy(value)
    if pid == POLICY_AUTO_CLEAR:
        return tr("自動清除存檔備份")
    return pid


def policy_display_options() -> List[str]:
    """Translated labels for the settings dropdown, in POLICY_IDS order."""
    return [policy_label(pid) for pid in POLICY_IDS]


def policy_from_label(label: str) -> str:
    """Map a display label back to its policy id (default when unrecognised)."""
    for pid in POLICY_IDS:
        if label == policy_label(pid):
            return pid
    return DEFAULT_POLICY


@dataclass
class SnapshotInfo:
    """One snapshot slot under ``<campaign>/save_snapshots/``."""

    slot: str
    """Folder name — the game's save slot name (e.g. ``save003``)."""

    campaign_day: Optional[float] = None
    """In-game day the snapshot was taken, from ``snapshot_meta.json``."""

    created_at: Optional[str] = None
    """UTC ISO-8601 creation stamp, from ``snapshot_meta.json``."""

    file_count: Optional[int] = None
    """File count the mod recorded when writing the snapshot."""


def snapshots_dir(campaign_dir: Optional[Path]) -> Optional[Path]:
    """Return ``<campaign>/save_snapshots``, or None when unresolvable."""
    if not campaign_dir:
        return None
    try:
        return Path(campaign_dir) / SNAPSHOTS_DIR_NAME
    except Exception:
        return None


def list_snapshots(campaign_dir: Optional[Path]) -> List[SnapshotInfo]:
    """List snapshot slots, newest campaign day first.

    Slots without a readable ``snapshot_meta.json`` are still listed (the mod
    only needs a non-empty folder to trigger a restore), just without metadata.
    """
    root = snapshots_dir(campaign_dir)
    if not root:
        return []
    try:
        if not root.is_dir():
            return []
        out: List[SnapshotInfo] = []
        for d in root.iterdir():
            if not d.is_dir():
                continue
            info = SnapshotInfo(slot=d.name)
            try:
                meta = json.loads((d / SNAPSHOT_META_NAME).read_text(encoding="utf-8-sig"))
                if isinstance(meta, dict):
                    day = meta.get("CampaignDay")
                    info.campaign_day = float(day) if isinstance(day, (int, float)) else None
                    created = meta.get("CreatedAtUtc")
                    info.created_at = created if isinstance(created, str) else None
                    count = meta.get("FileCount")
                    info.file_count = int(count) if isinstance(count, int) else None
            except Exception:
                pass
            out.append(info)
        out.sort(key=lambda s: (s.campaign_day if s.campaign_day is not None else -1.0), reverse=True)
        return out
    except Exception:
        return []


def has_snapshots(campaign_dir: Optional[Path]) -> bool:
    """True when at least one snapshot slot exists for *campaign_dir*."""
    return bool(list_snapshots(campaign_dir))


def purge_snapshots(campaign_dir: Optional[Path]) -> Tuple[int, List[str]]:
    """Delete every snapshot slot for *campaign_dir*.

    Returns ``(removed_count, errors)``.  The ``save_snapshots`` folder itself is
    left in place (empty) — the mod treats an empty folder as "no snapshot", and
    keeping it avoids fighting the mod over directory creation.
    """
    root = snapshots_dir(campaign_dir)
    if not root:
        return 0, []
    errors: List[str] = []
    removed = 0
    try:
        if not root.is_dir():
            return 0, []
        for d in sorted(root.iterdir()):
            try:
                if d.is_dir():
                    shutil.rmtree(d)
                else:
                    d.unlink()
                removed += 1
            except Exception as e:
                errors.append(f"{d.name}: {e}")
    except Exception as e:
        errors.append(str(e))
    return removed, errors
