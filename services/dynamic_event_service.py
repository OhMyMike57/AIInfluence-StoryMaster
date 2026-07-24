"""Pure-function helpers for the dynamic events feature (Phase 5 Stage F).

All functions accept dicts/lists/Paths and return the same — no Tk, no
side effects (other than clearly documented file I/O delegated to caller).

Key responsibilities:

* **Type normalisation** — game writes lowercase strings (``military``);
  the UI dropdown shows translated labels.  ``normalize_type()`` and
  ``type_label_for()`` bridge the two.
* **Sort & filter** — sorting events newest-first by
  ``creation_campaign_days``; filter logic kept here so unit tests don't
  need Tk.
* **Orphan reference scan** — find character JSONs whose
  ``DynamicEvents`` list refers to event IDs no longer present in
  ``dynamic_events.json`` (Stage F.5 batch clean).
* **Char-side scrubbing** — ``clean_char_event_refs(char_data, ids_to_drop)``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple


# ── Type normalisation ────────────────────────────────────────────────

# Single source of truth for the 10 known categories.  Keys are stored
# lowercase to match what the game writes; UI labels resolve via
# *type_label_map_factory* so i18n stays in the UI layer.
KNOWN_TYPE_KEYS: Tuple[str, ...] = (
    "military",
    "political",
    "economic",
    "social",
    "mysterious",
    "news",
    "local",
    "rumor",
    "diseaseoutbreak",
    "other",
)


def normalize_type(raw: Any) -> str:
    """Lower-case the raw type string and strip whitespace + word separators.

    The game writes some categories with separators (e.g. ``"disease_outbreak"``)
    while ``KNOWN_TYPE_KEYS`` stores them collapsed (``"diseaseoutbreak"``).
    Stripping ``_``, ``-`` and spaces makes the two representations match
    without needing per-key aliases.

    Returns ``""`` for missing / non-string input so callers can treat
    it as "unknown" without crashing.
    """
    if raw is None:
        return ""
    s = str(raw).strip().lower()
    return s.replace("_", "").replace("-", "").replace(" ", "")


# ── Sorting ───────────────────────────────────────────────────────────

def sort_events_by_creation(events: Iterable[dict], *, descending: bool = True) -> List[dict]:
    """Return events sorted by ``creation_campaign_days``.

    Events without a numeric creation day are pushed to the end (oldest)
    when *descending* is True.
    """
    def _key(e: dict) -> float:
        v = e.get("creation_campaign_days")
        try:
            return float(v) if v is not None else float("-inf")
        except (TypeError, ValueError):
            return float("-inf")
    return sorted(events, key=_key, reverse=descending)


# ── Filtering ─────────────────────────────────────────────────────────

# The player's character id inside every AI Influence save.
PLAYER_ID = "main_hero"


def event_involves_player(event: dict) -> bool:
    """True when *event* concerns the player.

    The mod's own ``player_involved`` flag is unreliable: the generator often
    writes ``main_hero`` into ``characters_involved`` (and/or ``applicable_npcs``)
    while leaving the flag at its ``false`` default, so filtering on the flag
    alone hid genuinely player-centric events.  Treat an explicit id reference
    as equally authoritative.
    """
    if event.get("player_involved", False):
        return True
    for field in ("characters_involved", "applicable_npcs"):
        v = event.get(field)
        if isinstance(v, (list, tuple, set)) and any(str(x) == PLAYER_ID for x in v):
            return True
    return False


def filter_events(
    events: Iterable[dict],
    *,
    type_eq:        Optional[str] = None,
    importance_eq:  Optional[int] = None,
    kingdom_in:     Optional[str] = None,
    player_only:    bool = False,
    keyword:        Optional[str] = None,
) -> List[dict]:
    """Apply filter predicates against an iterable of event dicts.

    ``None`` means "don't filter on this field".  Type comparison is
    case-insensitive (matches normalised lowercase).  Keyword search is
    a substring match against title + description + type.
    """
    type_eq_n = normalize_type(type_eq) if type_eq else ""
    kw_n      = (keyword or "").strip().lower()

    out: List[dict] = []
    for e in events:
        if type_eq_n and normalize_type(e.get("type")) != type_eq_n:
            continue
        if importance_eq is not None:
            try:
                if int(e.get("importance", 0)) != int(importance_eq):
                    continue
            except (TypeError, ValueError):
                continue
        if kingdom_in:
            kingdoms = [str(k) for k in e.get("kingdoms_involved", []) or []]
            if kingdom_in not in kingdoms:
                continue
        if player_only and not event_involves_player(e):
            continue
        if kw_n:
            haystack = (
                str(e.get("title", "")).lower() + " "
                + str(e.get("description", "")).lower() + " "
                + normalize_type(e.get("type"))
            )
            if kw_n not in haystack:
                continue
        out.append(e)
    return out


# ── Orphan reference scan (Stage F.5) ─────────────────────────────────

def find_orphan_event_refs(
    char_iter: Iterable[Tuple[str, Path, dict]],
    valid_event_ids: Set[str],
) -> List[Tuple[str, Path, List[str]]]:
    """Scan character JSONs for ``DynamicEvents`` IDs not in *valid_event_ids*.

    Parameters
    ----------
    char_iter
        Iterable of ``(display_name, path, char_data)`` triples — caller
        owns loading & passing in already-parsed dicts so we don't pay
        the I/O cost twice when the caller already has them in memory.
    valid_event_ids
        The set of event IDs currently present in ``dynamic_events.json``.

    Returns
    -------
    list of ``(display_name, path, orphan_ids)`` for each character
    that has at least one orphan.  Empty list = clean baseline.
    """
    out: List[Tuple[str, Path, List[str]]] = []
    for display, path, data in char_iter:
        if not isinstance(data, dict):
            continue
        refs = data.get("DynamicEvents", [])
        if not isinstance(refs, list):
            continue
        orphans = [str(r) for r in refs if str(r) not in valid_event_ids]
        if orphans:
            out.append((display, path, orphans))
    return out


def clean_char_event_refs(char_data: dict, orphan_ids: Set[str]) -> dict:
    """Return a shallow-copy of *char_data* with orphans removed from DynamicEvents.

    The original dict is not mutated.  When DynamicEvents becomes empty
    the field is preserved (set to empty list) rather than dropped, to
    match the game's expectation that the field exists.
    """
    if not isinstance(char_data, dict):
        return char_data
    refs = char_data.get("DynamicEvents", [])
    if not isinstance(refs, list):
        return dict(char_data)
    cleaned = [r for r in refs if str(r) not in orphan_ids]
    out = dict(char_data)
    out["DynamicEvents"] = cleaned
    return out


# ── Reverse scan: events whose characters_involved point to nowhere ───

def find_dangling_character_refs(
    events: Iterable[dict],
    valid_char_ids: Set[str],
) -> List[Tuple[str, List[str]]]:
    """Inspect each event's ``characters_involved`` for unknown character IDs.

    Returned list of ``(event_id, dangling_ids)`` is informational only
    — Stage F.5 explicitly recommends warning rather than auto-cleaning,
    since the game may keep history references to deleted characters.
    """
    out: List[Tuple[str, List[str]]] = []
    for e in events:
        chars = e.get("characters_involved", []) or []
        if not isinstance(chars, list):
            continue
        dangling = [str(c) for c in chars if str(c) not in valid_char_ids]
        if dangling:
            out.append((str(e.get("id", "?")), dangling))
    return out


# ── Edit application ──────────────────────────────────────────────────

# Whitelist of fields that the editor allows mutating.  Any edit submitted
# for a field outside this set is silently dropped — keeps IDs / creation
# timestamps immutable.  ``event_history`` is editable (with auto-derived
# top-level fields, see below).  Stage D (Phase 6) added the diplomacy/economic
# fields below the original eight.
EDITABLE_EVENT_FIELDS: Tuple[str, ...] = (
    "title",
    "type",
    "description",
    "importance",
    "expiration_campaign_days",
    "kingdoms_involved",
    "characters_involved",
    "event_history",
    # ── Stage D additions ──
    "player_involved",
    "applicable_npcs",
    "participating_kingdoms",
    "kingdom_engagement",
    "economic_effects",
    "next_statement_attempt_days",
    "failed_statement_attempts",
)

# The six AI-recognised audience tags for ``applicable_npcs`` (decompile +
# real-data confirmed).  ``all`` is mutually exclusive with the rest in the UI.
APPLICABLE_NPC_KEYS: Tuple[str, ...] = (
    "all",
    "lords",
    "companions",
    "faction_leaders",
    "village_notables",
    "merchants",
)

# Numeric fields of an event-embedded economic_effect (snake_case).  Coerced to
# float on edit; ``duration_days`` stays int-ish but we keep it float-tolerant.
_ECO_EFFECT_FLOAT_FIELDS: Tuple[str, ...] = (
    "prosperity_delta", "prosperity_delta_per_day",
    "food_delta", "food_delta_per_day",
    "security_delta", "security_delta_per_day",
    "loyalty_delta", "loyalty_delta_per_day",
    "income_multiplier",
)


def normalize_economic_effect(eff: Any) -> dict:
    """Return a cleaned copy of one event-embedded economic_effect dict.

    Coerces the numeric delta/multiplier fields to float and
    ``duration_days`` to int; preserves ``target_*`` / ``reason`` /
    ``market_price_modifiers`` (each ``{category_id, price_change_percent}``)
    and any unknown keys verbatim.  Non-dict input yields ``{}``.
    """
    if not isinstance(eff, dict):
        return {}
    out = dict(eff)
    for k in _ECO_EFFECT_FLOAT_FIELDS:
        if k in out:
            try:
                out[k] = float(out[k])
            except (TypeError, ValueError):
                out[k] = 0.0
    if "duration_days" in out:
        try:
            out["duration_days"] = int(float(out["duration_days"]))
        except (TypeError, ValueError):
            out["duration_days"] = 0
    if "reason" in out and out["reason"] is not None:
        out["reason"] = str(out["reason"])
    mpm = out.get("market_price_modifiers")
    if isinstance(mpm, list):
        clean_mpm: List[dict] = []
        for m in mpm:
            if not isinstance(m, dict):
                continue
            m2 = dict(m)
            if "category_id" in m2 and m2["category_id"] is not None:
                m2["category_id"] = str(m2["category_id"])
            if "price_change_percent" in m2:
                try:
                    m2["price_change_percent"] = float(m2["price_change_percent"])
                except (TypeError, ValueError):
                    m2["price_change_percent"] = 0.0
            clean_mpm.append(m2)
        out["market_price_modifiers"] = clean_mpm
    return out


def _hist_day(h: Any) -> float:
    """Return ``campaign_days`` of a history entry as float (``-inf`` on miss)."""
    try:
        return float(h.get("campaign_days", float("-inf")))
    except (TypeError, ValueError, AttributeError):
        return float("-inf")


def apply_event_edits(event: dict, edits: Dict[str, Any]) -> dict:
    """Return a copy of *event* with whitelisted edits applied.

    Unknown fields in *edits* are ignored.  Importance is coerced to
    int and clamped to 1..9.  Numeric fields are coerced to float.
    List-valued fields are deduplicated while preserving order.

    Special-case for ``event_history``: when the history list is edited,
    the in-game display reads the **latest** entry (highest ``campaign_days``)
    rather than the top-level ``description``.  We therefore auto-mirror:

    * ``event.description`` ← latest history entry's description
    * ``event.creation_campaign_days`` ← earliest history entry's day

    This keeps event-level fields consistent with the new history list and
    ensures temporal logic (creation must precede every history update) is
    preserved no matter how the user re-sequenced entries.
    """
    if not isinstance(event, dict):
        return event
    out = dict(event)
    for field, value in (edits or {}).items():
        if field not in EDITABLE_EVENT_FIELDS:
            continue
        if field == "importance":
            try:
                v = int(value)
            except (TypeError, ValueError):
                continue
            out["importance"] = max(1, min(9, v))
            continue
        if field == "expiration_campaign_days":
            try:
                out["expiration_campaign_days"] = float(value)
            except (TypeError, ValueError):
                pass
            continue
        if field in ("kingdoms_involved", "characters_involved",
                     "participating_kingdoms", "applicable_npcs"):
            if isinstance(value, (list, tuple, set)):
                seen: Set[str] = set()
                deduped: List[str] = []
                for x in value:
                    s = str(x)
                    if s not in seen:
                        seen.add(s)
                        deduped.append(s)
                out[field] = deduped
            continue
        if field == "player_involved":
            out["player_involved"] = bool(value)
            continue
        if field == "kingdom_engagement":
            if isinstance(value, dict):
                eng: Dict[str, int] = {}
                for k, v in value.items():
                    try:
                        eng[str(k)] = max(0, min(100, int(v)))
                    except (TypeError, ValueError):
                        continue
                out["kingdom_engagement"] = eng
            continue
        if field in ("next_statement_attempt_days", "failed_statement_attempts"):
            # Free-form {kingdom_id: number} maps; the editor only ever clears
            # these (→ {}) but we accept a passthrough dict for completeness.
            if isinstance(value, dict):
                out[field] = dict(value)
            continue
        if field == "economic_effects":
            if isinstance(value, list):
                out["economic_effects"] = [
                    normalize_economic_effect(e) for e in value if isinstance(e, dict)
                ]
            continue
        if field == "event_history":
            if isinstance(value, list):
                new_hist: List[dict] = []
                for h in value:
                    if not isinstance(h, dict):
                        continue
                    h2 = dict(h)
                    if "campaign_days" in h2:
                        try:
                            h2["campaign_days"] = float(h2["campaign_days"])
                        except (TypeError, ValueError):
                            pass
                    if "description" in h2:
                        h2["description"] = str(h2["description"])
                    new_hist.append(h2)
                out["event_history"] = new_hist
            continue
        if field == "type":
            out["type"] = str(value)
            continue
        # title / description — coerce to string
        out[field] = str(value)

    # ── Auto-derive top-level description + creation day from history ──
    # Only re-derive when the history list itself was just edited; spurious
    # description-only edits (legacy callers) should not silently overwrite.
    if "event_history" in (edits or {}):
        history = out.get("event_history") or []
        if isinstance(history, list) and history:
            latest = max(history, key=_hist_day)
            earliest = min(history, key=_hist_day)
            if isinstance(latest, dict) and "description" in latest:
                out["description"] = str(latest.get("description", ""))
            if isinstance(earliest, dict):
                try:
                    out["creation_campaign_days"] = float(
                        earliest.get("campaign_days",
                                      out.get("creation_campaign_days", 0.0))
                    )
                except (TypeError, ValueError):
                    pass
    return out


# ── New-event factory (Stage D) ───────────────────────────────────────

def new_event_template(
    *,
    event_type: str,
    creation_campaign_days: float,
    title: str = "",
    description: str = "",
    importance: int = 5,
) -> dict:
    """Return a fresh dynamic-event dict in 5.0.x bundle shape.

    ``id`` is a new uuid4; the event starts at *creation_campaign_days* with a
    single "Initial Event" history entry and an expiry 100 days out (matching
    the mod's default lifespan).  Diplomacy/economic collections start empty so
    the user fills them via the editor.  ``creation_time`` / ``expiration_time``
    are set to the current UTC instant (real-world timestamps; the mod's expiry
    logic keys off the campaign-day fields, not these).
    """
    import uuid
    from datetime import datetime, timezone

    day = 0.0
    try:
        day = float(creation_campaign_days or 0.0)
    except (TypeError, ValueError):
        day = 0.0
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    try:
        imp = max(1, min(9, int(importance)))
    except (TypeError, ValueError):
        imp = 5
    desc = str(description or title or "")
    return {
        "id": str(uuid.uuid4()),
        "type": str(event_type or "other"),
        "title": str(title or ""),
        "description": desc,
        "event_history": [
            {
                "campaign_days": day,
                "update_reason": "Initial Event",
                "description": desc,
            }
        ],
        "player_involved": False,
        "kingdoms_involved": [],
        "characters_involved": [],
        "importance": imp,
        "applicable_npcs": [],
        "economic_effects": [],
        "creation_time": now_iso,
        "creation_campaign_days": day,
        "expiration_time": now_iso,
        "expiration_campaign_days": day + 100.0,
        "participating_kingdoms": [],
        "kingdom_statements": [],
        "kingdom_engagement": {},
        "next_statement_attempt_days": {},
        "failed_statement_attempts": {},
    }


# ── I/O wrappers (delegating writer for testability) ──────────────────

# Keep in sync with services.world_service.DIPLOMACY_BUNDLE_FILENAME
# (duplicated here to avoid a service-to-service import).
DIPLOMACY_BUNDLE_FILENAME = "aiinfluence_campaign_diplomacy.json"


def write_dynamic_events(
    path: Path,
    events: List[dict],
    writer: Callable[[Path, Any], bool],
    loader: Optional[Callable[[Path], Any]] = None,
) -> bool:
    """Persist *events* to *path* via injected writer (returns True on success).

    Two on-disk layouts are supported:

    * **5.0.x bundle** (``aiinfluence_campaign_diplomacy.json``) — events are
      one key of a larger document.  We read the existing bundle, replace only
      ``dynamic_events``, and write the whole document back so the sibling keys
      (``kingdom_statements`` / ``kingdom_response_pressure`` /
      ``saved_campaign_days`` / ``kingdom_tax`` / ``Version``) survive intact.
      Requires *loader*; aborts (returns False) if the existing bundle cannot
      be parsed — overwriting it with a guess could destroy statements/tax data.
    * **4.1.0 legacy** (``dynamic_events.json``) — bare top-level array,
      written directly.

    Bundle mode triggers on the well-known filename, or — defensively — when
    the existing file parses to a dict.
    """
    is_bundle = path.name == DIPLOMACY_BUNDLE_FILENAME
    existing: Any = None
    if loader is not None and path.exists():
        existing = loader(path)
        if isinstance(existing, dict):
            is_bundle = True

    if is_bundle:
        if not isinstance(existing, dict):
            # Bundle file unreadable (or no loader injected): refuse rather than
            # clobber the non-event keys with a fabricated document.
            return False
        bundle = dict(existing)
        bundle["dynamic_events"] = events
        return bool(writer(path, bundle))

    return bool(writer(path, events))
