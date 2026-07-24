"""Game-state detection service for Mount & Blade II Bannerlord.

Provides a lightweight, non-blocking snapshot of:

* Whether Bannerlord.exe is currently running (via ``psutil``).
* Whether a campaign appears to be active — heuristic based on the
  modification time of the most recently written ProemConfig export file
  in the ``Exports/IDs`` directory (a fresh export strongly implies the
  game had a campaign loaded at export time).

Design
------
All detection is done in :func:`check_game_status`, which is intended to
be called on a repeating ``root.after`` heartbeat (every ~10 seconds) from
the main UI thread.  The function is blocking but typically runs in well
under a millisecond for the process-list scan and a few microseconds for
the mtime check.

``psutil`` is an optional dependency: if it is not installed or fails to
import, :attr:`GameStatus.running` is set to ``None`` (unknown) rather
than causing a crash.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from services.path_service import is_campaign_folder_name


# ── GameStatus dataclass ───────────────────────────────────────────────

@dataclass
class GameStatus:
    """Snapshot of the detected Bannerlord + campaign state."""

    running: Optional[bool]
    """True = Bannerlord.exe detected in process list.
    False = not running.
    None  = psutil unavailable / detection failed."""

    campaign_active: bool
    """Heuristic: at least one ProemConfig export file was modified within
    *recent_threshold_seconds* of the check time.  Indicates a campaign was
    loaded recently enough to run an export.  Always False when no
    ``ids_dir`` is provided."""

    last_export_at: Optional[datetime]
    """Modification time of the most recently touched export file, or None."""

    last_campaign_day: Optional[int]
    """Campaign day read from the most-recent export file's metadata, if
    parseable.  None when unavailable."""

    state: Optional[str] = None
    """Precise state from the Story Master companion mod's heartbeat:
    ``"main_menu"`` / ``"in_campaign"`` / ``"paused"``.  ``None`` when no fresh
    heartbeat is available (mod not installed / game not running)."""

    campaign_id: Optional[str] = None
    """Active campaign folder id from the heartbeat (``active_campaign_id``);
    ``None`` at the main menu."""

    last_campaign_id: Optional[str] = None
    """Last-played campaign folder id from the heartbeat (``last_campaign_id``);
    populated even at the main menu so the tool can tell whether it has the
    last-loaded save open vs some other one."""

    heartbeat_fresh: bool = False
    """True when a heartbeat file was found and written within the freshness
    window — i.e. the companion mod is actively running.  When True, *state*
    is authoritative and *running* is True regardless of psutil."""

    detected_at: datetime = field(default_factory=datetime.now)
    """Wall-clock time at which this check was performed."""


# ── Process detection ──────────────────────────────────────────────────

_PROCESS_NAMES = frozenset(
    {"bannerlord.exe", "bannerlord"}  # case-insensitive match
)

try:
    import psutil as _psutil
    _PSUTIL_AVAILABLE = True
except ImportError:  # psutil not installed
    _psutil = None  # type: ignore[assignment]
    _PSUTIL_AVAILABLE = False


def detect_bannerlord_running() -> Optional[bool]:
    """Return True/False/None based on whether Bannerlord.exe is in the process list.

    * ``True``  — process found.
    * ``False`` — process list checked, not found.
    * ``None``  — psutil unavailable or permission error; state unknown.
    """
    if not _PSUTIL_AVAILABLE:
        return None
    try:
        for proc in _psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in _PROCESS_NAMES:
                    return True
            except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                continue
        return False
    except Exception:
        return None


# ── Export directory heuristic ─────────────────────────────────────────

def _find_newest_export_mtime(ids_dir: Path) -> Optional[datetime]:
    """Return the mtime of the most recently modified ``*.json`` in *ids_dir*."""
    if not ids_dir or not ids_dir.is_dir():
        return None
    try:
        newest_mtime: Optional[float] = None
        for p in ids_dir.glob("*.json"):
            try:
                mtime = p.stat().st_mtime
                if newest_mtime is None or mtime > newest_mtime:
                    newest_mtime = mtime
            except Exception:
                continue
        if newest_mtime is None:
            return None
        return datetime.fromtimestamp(newest_mtime)
    except Exception:
        return None


def _read_campaign_day_from_newest(ids_dir: Path) -> Optional[int]:
    """Try to extract ``campaignDay`` from the newest export JSON.

    Returns None when the directory is empty, the file is unreadable, or
    the field is absent / not an integer.
    """
    import json
    if not ids_dir or not ids_dir.is_dir():
        return None
    try:
        candidates = list(ids_dir.glob("*.json"))
        if not candidates:
            return None
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        raw = json.loads(newest.read_text(encoding="utf-8"))
        day = raw.get("campaignDay")
        if day is not None:
            return int(day)
    except Exception:
        pass
    return None


# ── Companion-mod heartbeat ─────────────────────────────────────────────

HEARTBEAT_FILENAME = "heartbeat.json"


def _clean_campaign_id(raw: Any) -> Optional[str]:
    """Return *raw* as a campaign id, or None when it isn't one.

    Older connectors (≤0.8.0) resolved the active campaign by newest-mtime
    without excluding AI Influence's own scratch folders, so on 6.0+ they can
    report ``_portrait_tmp`` — the Content Editor's portrait buffer, which is
    written constantly while that editor is open.  Reject anything that isn't a
    plausible campaign id so the banner never claims to be editing one.
    """
    if not raw:
        return None
    name = str(raw).strip()
    return name if name and is_campaign_folder_name(name) else None


def read_heartbeat(
    save_data_dir: Optional[Path],
    *,
    fresh_within_seconds: float = 15.0,
) -> Optional[Dict[str, Any]]:
    """Return the parsed Story Master heartbeat if present and fresh, else None.

    The companion mod writes ``<save_data>/storytools/heartbeat.json`` every few
    seconds while the game runs.  A file written within *fresh_within_seconds* is
    treated as "mod actively running"; older means the game is closed or the mod
    is disabled, so callers fall back to the psutil heuristic.
    """
    if not save_data_dir:
        return None
    p = Path(save_data_dir) / "storytools" / HEARTBEAT_FILENAME
    try:
        if not p.is_file():
            return None
        if (time.time() - p.stat().st_mtime) > fresh_within_seconds:
            return None
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ── Main API ───────────────────────────────────────────────────────────

def check_game_status(
    ids_dir: Optional[Path] = None,
    *,
    save_data_dir: Optional[Path] = None,
    recent_threshold_seconds: int = 600,
    heartbeat_fresh_seconds: float = 15.0,
) -> GameStatus:
    """Perform a single, synchronous game-state snapshot.

    Intended to be called from a ``root.after`` callback every ~10 seconds.

    Parameters
    ----------
    ids_dir : Path, optional
        The ``Exports/IDs`` directory.  When ``None`` or absent,
        ``campaign_active`` is always ``False``.
    recent_threshold_seconds : int
        How many seconds ago an export file must have been written to be
        considered "recent" (i.e., a campaign was loaded at export time).
        Default 600 s (10 minutes).
    """
    running = detect_bannerlord_running()

    # Precise state from the companion mod's heartbeat (authoritative when fresh).
    state: Optional[str] = None
    campaign_id: Optional[str] = None
    last_campaign_id: Optional[str] = None
    heartbeat_fresh = False
    hb = read_heartbeat(save_data_dir, fresh_within_seconds=heartbeat_fresh_seconds)
    if hb is not None:
        heartbeat_fresh = True
        s = str(hb.get("state") or "").strip()
        state = s or None
        campaign_id = _clean_campaign_id(hb.get("active_campaign_id"))
        last_campaign_id = _clean_campaign_id(hb.get("last_campaign_id"))
        running = True  # a fresh heartbeat means the game is up regardless of psutil

    last_export_at: Optional[datetime] = None
    campaign_active = False
    last_campaign_day: Optional[int] = None

    if ids_dir is not None:
        ids_path = Path(ids_dir)
        last_export_at = _find_newest_export_mtime(ids_path)
        if last_export_at is not None:
            age_seconds = (datetime.now() - last_export_at).total_seconds()
            campaign_active = age_seconds <= recent_threshold_seconds
        if campaign_active:
            last_campaign_day = _read_campaign_day_from_newest(ids_path)

    # When the heartbeat is fresh it overrides the export-mtime heuristic.
    if heartbeat_fresh:
        campaign_active = state in ("in_campaign", "paused")

    return GameStatus(
        running=running,
        campaign_active=campaign_active,
        last_export_at=last_export_at,
        last_campaign_day=last_campaign_day,
        state=state,
        campaign_id=campaign_id,
        last_campaign_id=last_campaign_id,
        heartbeat_fresh=heartbeat_fresh,
    )
