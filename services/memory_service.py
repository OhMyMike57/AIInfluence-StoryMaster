"""AI Influence 5.0.5+ memory-system helpers (pure, UI-free).

The memory system is dual-track (see
``AIInfluence_Research/findings/5.0.5-5.0.7_記憶系統與工具適配.md``):

* **AI memory** — ``MEMORY (day N): text`` lines inside ``ConversationHistory``.
  Never consumed by consolidation; this is the AI's long-term memory.
* **Memory book** — the character JSON top-level ``Memories[]`` list of
  ``MemoryEntry``; this is what the in-game 記憶之書 UI shows.

These helpers parse / format / build both tracks and resolve memory images.
All functions are pure and Tk-free so they can be unit-tested headless.
"""
from __future__ import annotations

import datetime as _dt
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.json_utils import parse_conversation_line
from services.time_format import CAMPAIGN_START_DAY

# Canonical MemoryEntry field order (matches the 6.0.2 on-disk sample).
# ``scene`` arrived in 6.0: an English scene description the Memory Book keeps so
# an illustration can be generated later, even when image generation was off at
# the time.  6.0 entries carry the text in ``summary`` and leave ``memory_text``
# null; 5.0.x entries are the other way round, so both are read leniently.
MEMORY_ENTRY_FIELDS = (
    "id", "campaign_day", "created_time", "title", "summary",
    "scene", "memory_text", "image_path", "involved_hero_ids",
)


def collapse_single_line(text: Any) -> str:
    """Collapse multi-line text to a single whitespace-normalised line.

    Mirrors the mod's ``CollapseSpeechTextToSingleLine`` so a memory line we
    write matches the shape the mod produces.
    """
    return " ".join(seg.strip() for seg in str(text or "").splitlines() if seg.strip()).strip()


def format_memory_line(day: Any, text: Any) -> str:
    """Build a native ``MEMORY (day N): {single-line}`` history line."""
    try:
        d = int(round(float(day)))
    except (TypeError, ValueError):
        d = 0
    return f"MEMORY (day {d}): {collapse_single_line(text)}"


def parse_memory_lines(ch: Any) -> List[Dict[str, Any]]:
    """Return ``[{index, day, text, raw}]`` for MEMORY lines in *ch*.

    ``index`` is the position inside ConversationHistory (so callers can edit /
    delete the exact entry); ``day`` is an int.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(ch, list):
        return out
    for i, e in enumerate(ch):
        p = parse_conversation_line(e)
        if p["kind"] == "memory":
            try:
                day = int(round(float(p["day"]))) if p["day"] is not None else 0
            except (TypeError, ValueError):
                day = 0
            out.append({"index": i, "day": day, "text": p["text"] or "", "raw": e})
    return out


def memory_entries(data: Any) -> List[Dict[str, Any]]:
    """The character JSON ``Memories[]`` list (only dict entries)."""
    v = (data or {}).get("Memories") if isinstance(data, dict) else None
    return [e for e in v if isinstance(e, dict)] if isinstance(v, list) else []


def _raw_day(entry: Dict[str, Any]) -> float:
    try:
        return float(entry.get("campaign_day", 0))
    except (TypeError, ValueError):
        return 0.0


def entry_uses_elapsed(entry: Dict[str, Any]) -> bool:
    """Is this entry's ``campaign_day`` counted from the campaign start?

    6.0 switched ``Memories[].campaign_day`` from the absolute campaign-day
    counter (5.0.x wrote 91128.6) to days elapsed since the campaign began
    (6.0 writes 5.1, 23.9, 56.3…), which made every 6.0 memory render as
    「0年春6日」.  Memories are the only field that changed — DialogueObservations,
    RecentEvents and VisitedSettlements are all still absolute.

    The two scales cannot collide: an elapsed value only reaches
    ``CAMPAIGN_START_DAY`` after 1084 in-game years, so a small number is
    always elapsed and a large one is always absolute.
    """
    return _raw_day(entry) < CAMPAIGN_START_DAY


def book_uses_elapsed(entries: List[Dict[str, Any]]) -> bool:
    """Which convention to write for a NEW entry in this book.

    The newest entry wins (it was written by whichever version the player is
    running now), so a save that was carried across the 5.0.x → 6.0 boundary
    keeps growing in the scale the game currently reads.  An empty book falls
    back to 6.0's convention.
    """
    valid = [e for e in entries if isinstance(e, dict)]
    return entry_uses_elapsed(valid[-1]) if valid else True


def entry_day(entry: Dict[str, Any]) -> int:
    """Rounded **absolute** campaign day of a MemoryEntry.

    Both storage conventions are normalised to the absolute counter so callers
    (display, date pickers, sorting) never have to care which one is on disk.
    Use :func:`to_stored_day` to convert back before writing.
    """
    d = _raw_day(entry)
    if d < CAMPAIGN_START_DAY:
        d += CAMPAIGN_START_DAY
    return int(round(d))


def to_stored_day(absolute_day: Any, elapsed: bool) -> float:
    """Absolute campaign day → the value to store, honouring *elapsed*."""
    try:
        d = float(absolute_day)
    except (TypeError, ValueError):
        d = float(CAMPAIGN_START_DAY)
    return max(0.0, d - CAMPAIGN_START_DAY) if elapsed else d


def legacy_memory_text(entry: Dict[str, Any]) -> str:
    """A 5.0.x ``memory_text`` worth showing, or ``""``.

    6.0 stopped writing this field, so the editor no longer offers it.  Old
    saves still carry one, and it is only *worth surfacing* when it says
    something ``summary`` doesn't — a straight duplicate (which is what our own
    5.0.x-era 新增條目 used to produce) is noise.
    """
    body = str(entry.get("memory_text") or "").strip()
    return "" if body == str(entry.get("summary") or "").strip() else body


def new_memory_entry(
    *, day: Any, title: str = "", summary: str = "", memory_text: str = "",
    scene: str = "", image_path: str = "", involved_hero_ids: Optional[List[str]] = None,
    entry_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a fresh MemoryEntry.

    ``created_time`` uses the local wall-clock in ISO-8601 with offset —
    matching the 5.0.7 sample (``datetime.now().astimezone().isoformat()``);
    Newtonsoft parses it back cleanly.

    ``day`` is the value to *store*, i.e. already in this book's convention —
    see :func:`to_stored_day` / :func:`book_uses_elapsed`.

    ``memory_text`` is left empty unless a caller explicitly supplies one.  It
    used to be back-filled from ``summary`` because the 5.0.x Memory Book read
    it; 6.0 reads ``summary`` only and writes ``memory_text`` null, so mirroring
    the text would just plant a second stale copy nobody displays.
    """
    try:
        camp_day = float(day)
    except (TypeError, ValueError):
        camp_day = 0.0
    return {
        "id": entry_id or uuid.uuid4().hex,
        "campaign_day": camp_day,
        "created_time": _dt.datetime.now().astimezone().isoformat(),
        "title": title or "",
        "summary": summary or "",
        "scene": scene or "",
        "memory_text": memory_text or "",
        "image_path": image_path or "",
        "involved_hero_ids": list(involved_hero_ids or []),
    }


def update_memory_entry(entry: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *entry* with editable *fields* applied (unknown keys survive)."""
    out = dict(entry)
    if "campaign_day" in fields:
        try:
            out["campaign_day"] = float(fields["campaign_day"])
        except (TypeError, ValueError):
            pass
    for k in ("title", "summary", "scene", "memory_text", "image_path"):
        if k in fields:
            out[k] = str(fields[k] or "")
    if "involved_hero_ids" in fields and isinstance(fields["involved_hero_ids"], list):
        out["involved_hero_ids"] = list(fields["involved_hero_ids"])
    return out


def resolve_memory_image(entry: Dict[str, Any], campaign_dir: Any) -> Optional[Path]:
    """Resolve a MemoryEntry's image file.

    Prefers the portable ``<campaign_dir>/memory_images/<id>.png`` (the image
    filename stem equals the entry id), falling back to the stored absolute
    ``image_path`` (which points at the machine the save was created on).
    Returns None when nothing exists.
    """
    eid = str(entry.get("id", "") or "")
    if campaign_dir and eid:
        p = Path(campaign_dir) / "memory_images" / f"{eid}.png"
        if p.exists():
            return p
    ip = entry.get("image_path")
    if ip:
        try:
            p = Path(str(ip))
            if p.exists():
                return p
        except (OSError, ValueError):
            pass
    return None


def used_memory_image_ids(campaign_dir: Any) -> set:
    """Scan every character JSON in *campaign_dir* for ``Memories[].id``.

    Returns the set of image stems actually referenced by any memory-book entry
    campaign-wide (so the image picker can mark 已使用 vs 未使用 correctly, not
    just relative to one character).  Sub-folders (e.g. ``save_snapshots``) are
    skipped by using a non-recursive glob at the campaign root.
    """
    used: set = set()
    if not campaign_dir:
        return used
    root = Path(campaign_dir)
    if not root.exists():
        return used
    import json
    for p in root.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for e in memory_entries(d):
            eid = str(e.get("id", "") or "")
            if eid:
                used.add(eid)
    return used


def orphan_memory_images(entries: List[Dict[str, Any]], campaign_dir: Any) -> List[Path]:
    """PNGs in ``<campaign_dir>/memory_images/`` not referenced by any entry id.

    These are memory-book images the mod dropped when it overwrote ``Memories[]``
    (the 5.0.x book-track loses old entries while the AI-track keeps them) — the
    raw material for rebuilding a lost book entry.
    """
    if not campaign_dir:
        return []
    d = Path(campaign_dir) / "memory_images"
    if not d.exists():
        return []
    ids = {str(e.get("id", "") or "") for e in entries}
    return sorted((p for p in d.glob("*.png") if p.stem not in ids),
                  key=lambda p: p.name)
