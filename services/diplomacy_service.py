"""Pure-function service layer for the 5.0.x diplomacy bundle (Phase 6 Stage A).

Scope
-----
* **DiplomaticAction enum** — the 28-value action list, decompile-verified
  (see AIInfluence_Research/findings/5.0.2_DiplomaticAction枚舉.md).
* **Dual-format statement adapter** — the same statement is serialized two
  ways by the mod: the bundle's top-level ``kingdom_statements`` uses
  **string** action names (C# ``SerializableKingdomStatement``), while each
  event's embedded ``kingdom_statements`` uses **integer** enum values
  (C# ``KingdomStatement``, which additionally carries ``relation_changes``
  and ``quarantine_duration_days``).  :func:`parse_statement` /
  :func:`serialize_statement` translate both into / out of one unified model.
* **Bundle accessors** — read/replace statements & response pressure on a
  loaded bundle dict; event-cascade helpers.
* **Validation** — orphan statements, unknown kingdom ids.

Round-trip guarantee
--------------------
The unified model keeps the original dict under ``_raw``.  Serialization
starts from a copy of ``_raw`` and only overwrites known fields, and only
writes a key when it already existed in the source or its value is
non-default.  Unedited statements therefore serialize back **deep-equal** to
the on-disk original (mod omits null fields — NullValueHandling.Ignore — so
we never invent keys), and unknown/future mod fields survive untouched.

settlement_id quirk
-------------------
Multi-action statements join per-action settlements with commas, writing the
literal string ``null`` for actions without one (observed:
``"town_V9,null,castle_V5"`` for 3 actions).  Single-action statements use a
plain value.  The mod ALSO sometimes writes a single shared value for a
multi-action statement (observed: 2 actions sharing ``"town_EW1"``) — when
token count doesn't match the action count we keep the raw string verbatim
(``settlement_ids = None``) so round-trip stays exact; editors should fall
back to a statement-level settlement field in that case.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# ── DiplomaticAction enum (index == numeric enum value) ───────────────────────

DIPLOMATIC_ACTIONS: Tuple[str, ...] = (
    "None",                   # 0
    "DeclareWar",             # 1
    "ProposePeace",           # 2
    "ProposeAlliance",        # 3
    "RejectPeace",            # 4
    "RejectAlliance",         # 5
    "AcceptPeace",            # 6
    "AcceptAlliance",         # 7
    "BreakAlliance",          # 8
    "ProposeTradeAgreement",  # 9
    "AcceptTradeAgreement",   # 10
    "RejectTradeAgreement",   # 11
    "EndTradeAgreement",      # 12
    "TransferTerritory",      # 13
    "DemandTerritory",        # 14
    "RejectTerritory",        # 15
    "DemandTribute",          # 16
    "AcceptTribute",          # 17
    "RejectTribute",          # 18
    "EndTribute",             # 19
    "DemandReparations",      # 20
    "AcceptReparations",      # 21
    "RejectReparations",      # 22
    "ExpelClan",              # 23
    "GrantFief",              # 24
    "ReceiveFief",            # 25
    "QuarantineSettlement",   # 26
    "SetKingdomTaxPolicy",    # 27
)

_ACTION_INDEX: Dict[str, int] = {name: i for i, name in enumerate(DIPLOMATIC_ACTIONS)}
_ACTION_INDEX_CI: Dict[str, int] = {name.lower(): i for i, name in enumerate(DIPLOMATIC_ACTIONS)}

# Actions whose per-action parameter is a settlement id.
SETTLEMENT_ACTIONS: frozenset = frozenset({
    "TransferTerritory", "DemandTerritory", "RejectTerritory",
    "GrantFief", "ReceiveFief", "QuarantineSettlement",
})

DIPLOMACY_BUNDLE_FILENAME = "aiinfluence_campaign_diplomacy.json"


def action_name(value: Any) -> str:
    """Normalize an action (int enum value / enum name / numeric string) to its name.

    Unknown numeric values are returned as their decimal string (lossless
    passthrough); unknown strings are returned unchanged.
    """
    if isinstance(value, bool):  # bool is int subclass — reject explicitly
        return str(value)
    if isinstance(value, int):
        return DIPLOMATIC_ACTIONS[value] if 0 <= value < len(DIPLOMATIC_ACTIONS) else str(value)
    if isinstance(value, str):
        s = value.strip()
        if s in _ACTION_INDEX:
            return s
        if s.lower() in _ACTION_INDEX_CI:
            return DIPLOMATIC_ACTIONS[_ACTION_INDEX_CI[s.lower()]]
        if s.lstrip("-").isdigit():
            return action_name(int(s))
        return s
    return str(value)


def action_value(name: Any) -> int:
    """Normalize an action (name / int / numeric string) to its numeric enum value.

    Raises ``ValueError`` for names not in the enum (and non-numeric strings).
    """
    if isinstance(name, bool):
        raise ValueError(f"invalid action: {name!r}")
    if isinstance(name, int):
        return name
    if isinstance(name, str):
        s = name.strip()
        if s in _ACTION_INDEX:
            return _ACTION_INDEX[s]
        if s.lower() in _ACTION_INDEX_CI:
            return _ACTION_INDEX_CI[s.lower()]
        if s.lstrip("-").isdigit():
            return int(s)
    raise ValueError(f"unknown DiplomaticAction: {name!r}")


# ── settlement_id encode / decode ─────────────────────────────────────────────

def split_settlement_ids(raw: Any, n_actions: int) -> Tuple[Optional[List[Optional[str]]], Optional[str]]:
    """Decode the comma-joined settlement_id field.

    Returns ``(aligned_list, raw_string)``:

    * ``aligned_list`` — one entry per action (None where the literal ``null``
      or empty), only when the token count matches *n_actions*; otherwise None.
    * ``raw_string`` — the original value (or None), kept for verbatim
      round-trip when alignment fails.
    """
    if raw is None or raw == "":
        # No settlements at all: vacuously aligned (all None).
        return ([None] * n_actions, None)
    s = str(raw)
    tokens: List[Optional[str]] = [
        (None if t.strip().lower() in ("", "null") else t.strip())
        for t in s.split(",")
    ]
    if len(tokens) == n_actions:
        return (tokens, s)
    return (None, s)


def join_settlement_ids(settlements: List[Optional[str]]) -> Optional[str]:
    """Encode per-action settlements back to the mod's comma-join convention.

    * all None → None (key omitted, matching NullValueHandling.Ignore)
    * single action → plain value
    * multiple actions → comma-join with literal ``null`` placeholders
    """
    if not settlements or all(x is None for x in settlements):
        return None
    if len(settlements) == 1:
        return settlements[0]
    return ",".join("null" if x is None else str(x) for x in settlements)


# ── Unified statement model ───────────────────────────────────────────────────

# Scalar params shared by both serializations: (key, default)
_SCALAR_FIELDS: Tuple[Tuple[str, Any], ...] = (
    ("daily_tribute_amount", 0),
    ("tribute_duration_days", 0),
    ("reparations_amount", 0),
    ("trade_agreement_duration_years", 1.0),
    ("tax_rate_percent", 0.0),
    ("tax_scope", None),
    ("tax_settlement_id", None),
    ("target_clan_id", None),
)
# Present only on the event-embedded serialization (C# KingdomStatement).
_EMBEDDED_ONLY_FIELDS: Tuple[Tuple[str, Any], ...] = (
    ("quarantine_duration_days", 0),
)


def parse_statement(raw: dict, *, embedded: bool) -> dict:
    """Parse a top-level (string actions) or embedded (int actions) statement
    into the unified model.  The original dict is kept under ``_raw``."""
    if not isinstance(raw, dict):
        raw = {}
    actions_raw = raw.get("actions")
    if not isinstance(actions_raw, list):
        a = raw.get("action")
        actions_raw = [] if a is None else [a]
    names = [action_name(a) for a in actions_raw]

    tk_ids = raw.get("target_kingdom_ids")
    if not isinstance(tk_ids, list):
        tk = raw.get("target_kingdom_id")
        tk_ids = [tk] if tk else []

    settlement_ids, settlement_raw = split_settlement_ids(raw.get("settlement_id"), len(names))

    model: Dict[str, Any] = {
        "_raw": dict(raw),
        "_embedded": bool(embedded),
        "kingdom_id":     str(raw.get("kingdom_id") or ""),
        "statement_text": str(raw.get("statement_text") or ""),
        "reason":         str(raw.get("reason") or ""),
        "campaign_days":  float(raw.get("campaign_days") or 0.0),
        "event_id":       raw.get("event_id"),
        "action_names":   names,
        "target_kingdom_ids": [str(x) for x in tk_ids if x],
        "settlement_ids":     settlement_ids,    # None ⇒ unaligned, use raw
        "settlement_id_raw":  settlement_raw,
        "relation_changes":   list(raw.get("relation_changes") or []),
    }
    for key, default in _SCALAR_FIELDS + _EMBEDDED_ONLY_FIELDS:
        model[key] = raw.get(key, default)
    return model


def _set_field(out: dict, raw: dict, key: str, value: Any, default: Any) -> None:
    """Write *key* only when it existed in the source or the value is non-default.

    Mirrors the mod's NullValueHandling.Ignore so unedited statements
    round-trip deep-equal and we never invent keys."""
    if key in raw or value != default:
        if value is None and key not in raw:
            return
        out[key] = value
    else:
        out.pop(key, None)


def serialize_statement(model: dict, *, embedded: bool) -> dict:
    """Serialize the unified model to the requested on-disk format.

    ``embedded=True`` → int enum actions (+ embedded-only fields);
    ``embedded=False`` → string action names (top-level list format).
    Starts from ``_raw`` so unknown fields survive; cross-format conversion
    (parse as one format, serialize as the other) is fully supported.
    """
    raw = model.get("_raw") or {}
    out = dict(raw)

    out["kingdom_id"]     = model.get("kingdom_id", "")
    out["statement_text"] = model.get("statement_text", "")
    _set_field(out, raw, "reason", model.get("reason", ""), "")
    out["campaign_days"]  = model.get("campaign_days", 0.0)
    _set_field(out, raw, "event_id", model.get("event_id"), None)

    names = list(model.get("action_names") or [])
    if embedded:
        encoded: List[Any] = [action_value(n) for n in names]
        first: Any = encoded[0] if encoded else 0
    else:
        encoded = [action_name(n) for n in names]
        first = encoded[0] if encoded else "None"
    # Plural ``actions`` mirrors the mod's NullValueHandling.Ignore: emit it only
    # when the source already had it, or the statement carries a real (non-None)
    # action.  5.0.3 omits ``actions`` for pure announcement statements that only
    # set the singular ``action`` to None — preserving that shape keeps unedited
    # data round-tripping deep-equal (and editing in a real action still writes it).
    has_real_action = any(n and n != "None" for n in names)
    if "actions" in raw or has_real_action:
        out["actions"] = encoded
    else:
        out.pop("actions", None)
    _set_field(out, raw, "action", first, 0 if embedded else "None")

    tk_ids = list(model.get("target_kingdom_ids") or [])
    _set_field(out, raw, "target_kingdom_ids", tk_ids, [])
    _set_field(out, raw, "target_kingdom_id", tk_ids[0] if tk_ids else None, None)

    if model.get("settlement_ids") is not None:
        joined = join_settlement_ids(model["settlement_ids"])
        _set_field(out, raw, "settlement_id", joined, None)
    elif model.get("settlement_id_raw") is not None:
        out["settlement_id"] = model["settlement_id_raw"]
    # else: leave whatever _raw had (typically absent)

    for key, default in _SCALAR_FIELDS:
        _set_field(out, raw, key, model.get(key, default), default)

    if embedded:
        for key, default in _EMBEDDED_ONLY_FIELDS:
            _set_field(out, raw, key, model.get(key, default), default)
        _set_field(out, raw, "relation_changes",
                   list(model.get("relation_changes") or []), [])
    else:
        # Top-level C# class has no such members — drop to mirror mod output.
        for key, _default in _EMBEDDED_ONLY_FIELDS:
            out.pop(key, None)
        out.pop("relation_changes", None)

    out.pop("_raw", None)
    out.pop("_embedded", None)
    return out


def new_statement(
    kingdom_id: str,
    event_id: Optional[str],
    campaign_days: float,
) -> dict:
    """Return a fresh unified model with sane defaults (no ``_raw`` baggage)."""
    model = parse_statement({}, embedded=False)
    model["kingdom_id"] = str(kingdom_id or "")
    model["event_id"] = event_id
    model["campaign_days"] = float(campaign_days or 0.0)
    return model


def statement_key(stmt: dict) -> str:
    """Stable lookup key for a statement (the bundle has no unique ids).

    Accepts a unified model or a raw statement dict.  Collisions (same day +
    same kingdom) are possible; callers needing uniqueness should suffix an
    ordinal.
    """
    days = stmt.get("campaign_days", 0.0)
    try:
        days_s = f"{float(days):.4f}"
    except (TypeError, ValueError):
        days_s = str(days)
    return f"{days_s}|{stmt.get('kingdom_id', '')}"


# ── Bundle accessors ──────────────────────────────────────────────────────────

def bundle_statements(bundle: dict) -> List[dict]:
    """Top-level statements list of a loaded bundle (raw dicts, string actions)."""
    v = (bundle or {}).get("kingdom_statements", [])
    return v if isinstance(v, list) else []


def replace_statements(bundle: dict, statements: List[dict]) -> dict:
    """Return a shallow-copied bundle with the top-level statements replaced."""
    out = dict(bundle or {})
    out["kingdom_statements"] = list(statements)
    return out


def bundle_pressure(bundle: dict) -> dict:
    """The ``kingdom_response_pressure`` block (always returns both sub-dicts)."""
    p = (bundle or {}).get("kingdom_response_pressure") or {}
    return {
        "PressureByKingdomId":      dict(p.get("PressureByKingdomId") or {}),
        "ResponseEventIdByKingdom": dict(p.get("ResponseEventIdByKingdom") or {}),
    }


def replace_pressure(bundle: dict, pressure: dict) -> dict:
    """Return a shallow-copied bundle with the pressure block replaced."""
    out = dict(bundle or {})
    out["kingdom_response_pressure"] = {
        "PressureByKingdomId":      dict((pressure or {}).get("PressureByKingdomId") or {}),
        "ResponseEventIdByKingdom": dict((pressure or {}).get("ResponseEventIdByKingdom") or {}),
    }
    return out


def statements_for_event(bundle: dict, event_id: str) -> List[dict]:
    """Top-level statements whose ``event_id`` matches (raw dicts)."""
    eid = str(event_id or "")
    return [s for s in bundle_statements(bundle) if str(s.get("event_id") or "") == eid]


def remove_statements_of_event(bundle: dict, event_id: str) -> Tuple[dict, int]:
    """Drop every top-level statement linked to *event_id*.

    Returns ``(new_bundle, removed_count)``.  Event-embedded statements live
    inside the event itself and disappear with it; pressure assignments are
    cleaned separately via :func:`clear_pressure_event`.
    """
    eid = str(event_id or "")
    kept, removed = [], 0
    for s in bundle_statements(bundle):
        if str(s.get("event_id") or "") == eid:
            removed += 1
        else:
            kept.append(s)
    return replace_statements(bundle, kept), removed


def clear_pressure_event(bundle: dict, event_id: str) -> Tuple[dict, List[str]]:
    """Unassign *event_id* from every kingdom's response slot.

    Returns ``(new_bundle, affected_kingdom_ids)``.  Pressure values are kept.
    """
    eid = str(event_id or "")
    p = bundle_pressure(bundle)
    affected = [k for k, v in p["ResponseEventIdByKingdom"].items() if str(v or "") == eid]
    for k in affected:
        del p["ResponseEventIdByKingdom"][k]
    return replace_pressure(bundle, p), affected


# ── Statement change application (Stage C) ───────────────────────────────────

def statement_keys(statements: List[dict]) -> List[str]:
    """Unique, order-stable keys for a statements list.

    Base key is :func:`statement_key`; collisions (same day + kingdom) get a
    ``#n`` ordinal suffix.  UI staging and :func:`apply_statement_changes`
    must both derive keys from the same list snapshot.
    """
    seen: Dict[str, int] = {}
    out: List[str] = []
    for s in statements:
        base = statement_key(s)
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(base if n == 0 else f"{base}#{n}")
    return out


def find_embedded_twin_index(event: dict, stmt: dict) -> Optional[int]:
    """Index of *stmt*'s embedded copy inside *event*'s kingdom_statements.

    Match: same kingdom_id + campaign_days within 0.01 day (the mod stores the
    same statement in both places).  Returns None when absent.
    """
    try:
        days = float(stmt.get("campaign_days") or 0.0)
    except (TypeError, ValueError):
        return None
    kid = str(stmt.get("kingdom_id") or "")
    for i, s in enumerate(event.get("kingdom_statements", []) or []):
        try:
            if (str(s.get("kingdom_id") or "") == kid
                    and abs(float(s.get("campaign_days") or 0.0) - days) < 0.01):
                return i
        except (TypeError, ValueError):
            continue
    return None


# Fields the editor may change; copied onto the embedded twin so both
# serializations stay in sync.
_EDITABLE_MODEL_FIELDS: Tuple[str, ...] = (
    "statement_text", "reason", "campaign_days",
    "action_names", "target_kingdom_ids",
    "settlement_ids", "settlement_id_raw",
) + tuple(k for k, _d in _SCALAR_FIELDS)

# Fields that exist only on the embedded serialization. A model parsed from a
# TOP-LEVEL statement doesn't know them — merging its empty defaults onto the
# twin would wipe real data (e.g. relation_changes). They are merged only when
# the model carries the embedded view: parsed embedded, or overlaid via
# :func:`parse_statement_with_twin`.
_EMBEDDED_MODEL_FIELDS: Tuple[str, ...] = ("relation_changes", "quarantine_duration_days")


def parse_statement_with_twin(stmt: dict, event: Optional[dict]) -> dict:
    """Parse a top-level statement and overlay its embedded twin's
    embedded-only fields (relation_changes / quarantine_duration_days).

    This is what editors should load: the unified model then represents the
    COMPLETE intended state, and user edits to relation_changes propagate to
    the twin on save (including clearing them).
    """
    model = parse_statement(stmt, embedded=False)
    if isinstance(event, dict):
        idx = find_embedded_twin_index(event, stmt)
        if idx is not None:
            twin = (event.get("kingdom_statements") or [])[idx]
            tm = parse_statement(twin, embedded=True)
            for k in _EMBEDDED_MODEL_FIELDS:
                model[k] = tm[k]
            model["_embedded_overlay"] = True
    return model


def merge_model_into(target: dict, source: dict) -> dict:
    """Copy the user-editable fields of *source* model onto *target* model.

    Embedded-only fields are copied only when *source* actually carries the
    embedded view (parsed embedded, or overlaid) — see _EMBEDDED_MODEL_FIELDS.
    """
    for k in _EDITABLE_MODEL_FIELDS:
        if k in source:
            v = source[k]
            target[k] = list(v) if isinstance(v, list) else v
    if source.get("_embedded") or source.get("_embedded_overlay"):
        for k in _EMBEDDED_MODEL_FIELDS:
            if k in source:
                v = source[k]
                target[k] = list(v) if isinstance(v, list) else v
    return target


def apply_statement_changes(
    bundle: dict,
    *,
    edits: Optional[Dict[str, dict]] = None,
    deletes: Optional[Set[str]] = None,
    new: Optional[List[dict]] = None,
) -> Tuple[dict, Dict[str, Any]]:
    """Apply staged statement changes to a bundle — BOTH serializations.

    Parameters
    ----------
    edits / deletes
        Keyed by :func:`statement_keys` of the bundle's CURRENT top-level
        list; ``edits`` values are unified models (from :func:`parse_statement`
        with user changes applied).
    new
        Unified models to append (from :func:`new_statement` + edits).

    For every change the event-embedded twin (located via the statement's
    original ``event_id``) is updated / removed / appended too, preserving
    twin-only state (its ``_raw``) where it exists.

    Returns ``(new_bundle, summary)`` — summary counts for the confirm dialog:
    ``edited / deleted / added / twin_updated / twin_removed / twin_added /
    missing_event`` (event ids referenced but absent).
    """
    edits = edits or {}
    deletes = deletes or set()
    new = new or []

    out = dict(bundle or {})
    events: List[dict] = [dict(e) if isinstance(e, dict) else e
                          for e in (out.get("dynamic_events") or [])]
    ev_by_id: Dict[str, dict] = {
        str(e.get("id", "")): e for e in events if isinstance(e, dict)
    }
    top = list(bundle_statements(out))
    keys = statement_keys(top)

    summary: Dict[str, Any] = {
        "edited": 0, "deleted": 0, "added": 0,
        "twin_updated": 0, "twin_removed": 0, "twin_added": 0,
        "missing_event": [],
    }

    def _twin_ctx(stmt: dict):
        eid = str(stmt.get("event_id") or "")
        ev = ev_by_id.get(eid) if eid else None
        if ev is None:
            if eid:
                summary["missing_event"].append(eid)
            return None, None
        idx = find_embedded_twin_index(ev, stmt)
        return ev, idx

    new_top: List[dict] = []
    for key, stmt in zip(keys, top):
        if key in deletes:
            summary["deleted"] += 1
            ev, idx = _twin_ctx(stmt)
            if ev is not None and idx is not None:
                emb = list(ev.get("kingdom_statements") or [])
                emb.pop(idx)
                ev["kingdom_statements"] = emb
                summary["twin_removed"] += 1
            continue
        if key in edits:
            model = edits[key]
            new_top.append(serialize_statement(model, embedded=False))
            summary["edited"] += 1
            ev, idx = _twin_ctx(stmt)   # locate twin by ORIGINAL day/kingdom
            if ev is not None:
                emb = list(ev.get("kingdom_statements") or [])
                if idx is not None:
                    tm = parse_statement(emb[idx], embedded=True)
                    merge_model_into(tm, model)
                    emb[idx] = serialize_statement(tm, embedded=True)
                    summary["twin_updated"] += 1
                else:
                    emb.append(serialize_statement(model, embedded=True))
                    summary["twin_added"] += 1
                ev["kingdom_statements"] = emb
            continue
        new_top.append(stmt)

    for model in new:
        new_top.append(serialize_statement(model, embedded=False))
        summary["added"] += 1
        eid = str(model.get("event_id") or "")
        ev = ev_by_id.get(eid) if eid else None
        if ev is not None:
            emb = list(ev.get("kingdom_statements") or [])
            emb.append(serialize_statement(model, embedded=True))
            ev["kingdom_statements"] = emb
            summary["twin_added"] += 1
        elif eid:
            summary["missing_event"].append(eid)

    out["dynamic_events"] = events
    out["kingdom_statements"] = new_top
    return out, summary


def remove_events_cascade(bundle: dict, event_ids: Set[str]) -> Tuple[dict, Dict[str, Any]]:
    """Cascade cleanup when events are deleted: drop their top-level statements
    and unassign them from the response-pressure table.

    The events themselves (and their embedded statements) are removed by the
    caller's event pipeline; this handles the bundle-level references.
    Returns ``(new_bundle, {"statements_removed": n, "pressure_cleared": [kid…]})``.
    """
    out = dict(bundle or {})
    removed_total = 0
    cleared: List[str] = []
    for eid in {str(e) for e in (event_ids or set()) if e}:
        out, n = remove_statements_of_event(out, eid)
        removed_total += n
        out, kids = clear_pressure_event(out, eid)
        cleared.extend(kids)
    return out, {"statements_removed": removed_total, "pressure_cleared": cleared}


def write_bundle_update(
    path: Any,
    *,
    writer: Any,
    loader: Any,
    events: Optional[List[dict]] = None,
    statements: Optional[List[dict]] = None,
    pressure: Optional[dict] = None,
) -> bool:
    """Read the on-disk bundle, replace only the provided sections, write back.

    Same safety contract as ``dynamic_event_service.write_dynamic_events``:
    refuses (returns False, file untouched) when the existing bundle cannot be
    parsed as a dict — sibling keys must never be guessed.
    """
    existing = loader(path) if getattr(path, "exists", lambda: False)() else None
    if not isinstance(existing, dict):
        return False
    out = dict(existing)
    if events is not None:
        out["dynamic_events"] = events
    if statements is not None:
        out["kingdom_statements"] = statements
    if pressure is not None:
        out = replace_pressure(out, pressure)
    return bool(writer(path, out))


# ── Validation ────────────────────────────────────────────────────────────────

def find_orphan_statements(bundle: dict) -> List[Tuple[str, str]]:
    """Top-level statements whose ``event_id`` matches no event in the bundle.

    Returns ``[(statement_key, event_id), …]``.  Statements without an
    event_id are not flagged (legal: empty link).
    """
    events = (bundle or {}).get("dynamic_events", [])
    valid_ids: Set[str] = {str(e.get("id", "")) for e in events if isinstance(e, dict)}
    out: List[Tuple[str, str]] = []
    for s in bundle_statements(bundle):
        eid = str(s.get("event_id") or "")
        if eid and eid not in valid_ids:
            out.append((statement_key(s), eid))
    return out


def find_unknown_kingdoms(bundle: dict, valid_kingdom_ids: Iterable[str]) -> List[Tuple[str, str]]:
    """Kingdom ids referenced anywhere in the bundle but absent from the universe.

    Scans top-level statements (speaker + targets), event ``kingdom_engagement``
    keys, and the pressure table.  Returns ``[(where, kingdom_id), …]``.
    Empty *valid_kingdom_ids* disables the check (no terminology loaded).
    """
    valid = {str(k) for k in valid_kingdom_ids if k}
    if not valid:
        return []
    out: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()

    def _flag(where: str, kid: Any) -> None:
        k = str(kid or "")
        # "all" is a legal wildcard; literal "null" is the mod's per-action
        # placeholder in target_kingdom_ids (same convention as settlement_id).
        if k and k != "all" and k.lower() != "null" and k not in valid and (where, k) not in seen:
            seen.add((where, k))
            out.append((where, k))

    for s in bundle_statements(bundle):
        key = statement_key(s)
        _flag(f"statement {key}", s.get("kingdom_id"))
        for t in (s.get("target_kingdom_ids") or []):
            _flag(f"statement {key}", t)
    for e in (bundle or {}).get("dynamic_events", []) or []:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("id", ""))[:8]
        for k in (e.get("kingdom_engagement") or {}):
            _flag(f"event {eid} engagement", k)
    p = bundle_pressure(bundle)
    for k in p["PressureByKingdomId"]:
        _flag("pressure", k)
    for k in p["ResponseEventIdByKingdom"]:
        _flag("pressure", k)
    return out
