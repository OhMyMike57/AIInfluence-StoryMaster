"""Terminology library service.

Provides a lookup layer from game-internal IDs to human-readable display
names, organized by category (characters / kingdoms / cultures / clans /
items).

Design
------
Two stacked layers, both pure-function I/O:

1. **Per-language base files** under ``locales/terminology/`` — one file
   per language code (``en.json``, ``zh_TW.json``, ``zh_CN.json``).  The
   user maintains these manually.  ``en.json`` is the guaranteed
   fallback.  Suitable for **static** translations (the 9 native kingdoms,
   7 cultures, ``main_hero`` …) that don't change between campaigns.

2. **Per-campaign cache files** under ``config/terminology_cache/<campaign_id>.json``
   (Phase 5.5).  Populated by importing JSON exports from the user's
   in-game ``ProemConfig`` mod.  Language-agnostic (the dump records the
   game language at export time but the file is keyed by stringId).
   Holds **dynamic** IDs (wanderers, custom clans, items, …) that no
   manual translation can keep up with.

Resolution chain (most-specific first)::

    campaign cache → primary language → en.json → original ID

All functions here are pure (no module-level mutable state) so the caller
(the main app) owns cache lifetime and reload behaviour.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import re


SCHEMA_VERSION = 1
FALLBACK_LANG = "en"
# Resolve the bundled locales via app_paths so it works in a frozen (PyInstaller)
# build too — __file__-relative paths break once modules live inside the bundle.
try:
    from services.app_paths import resource_dir as _resource_dir
    DEFAULT_BASE_DIR = _resource_dir() / "locales" / "terminology"
except Exception:  # pragma: no cover — fallback for odd import contexts
    DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent / "locales" / "terminology"
CAMPAIGN_CACHE_DIR_NAME = "terminology_cache"

# Categories are ordered so iteration is deterministic.  ``characters`` and
# ``kingdoms`` / ``cultures`` exist in both base and campaign payloads;
# ``clans`` and ``items`` are campaign-only in practice but the empty
# scaffold creates the keys for both so callers never need to special-case.
CATEGORIES = ("characters", "kingdoms", "cultures", "clans", "items",
              "settlements", "speakers")
# "speakers" = heroes only, i.e. characters that can actually say something.
# "characters" merges heroes with troop *templates* so troop ids still resolve
# to a display name, but that makes it useless for picking a speaker: the same
# search then offers 帝國步兵 and title words like 「盾女」 (spc_wanderer_sturgia_8,
# a troop template) alongside real people — 1343 of them in a normal campaign.
BASE_CATEGORIES = ("characters", "kingdoms", "cultures")
CAMPAIGN_CATEGORIES = CATEGORIES  # campaign cache covers everything


# ── Internal helpers ───────────────────────────────────────────────────

def _coerce_str_dict(raw: Any) -> Dict[str, str]:
    """Coerce *raw* to ``{str: str}``; drop entries whose key isn't a string."""
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(k, str)}


# ── Per-language base files ────────────────────────────────────────────

def _empty_payload(lang: str) -> Dict[str, Any]:
    """Return an empty *language* payload with all category keys present."""
    out: Dict[str, Any] = {
        "version": SCHEMA_VERSION,
        "language": lang,
    }
    for cat in CATEGORIES:
        out[cat] = {}
    return out


def _normalize_payload(payload: Any, lang: str) -> Dict[str, Any]:
    """Return a well-shaped language dict even if the file is malformed."""
    if not isinstance(payload, dict):
        return _empty_payload(lang)
    out = _empty_payload(lang)
    out["version"] = int(payload.get("version", SCHEMA_VERSION) or SCHEMA_VERSION)
    out["language"] = str(payload.get("language") or lang)
    for cat in CATEGORIES:
        out[cat] = _coerce_str_dict(payload.get(cat))
    return out


def load_terminology_for(lang: str, base_dir: Path = DEFAULT_BASE_DIR) -> Dict[str, Any]:
    """Load the terminology file for *lang*. Missing / broken files return empty scaffold."""
    path = Path(base_dir) / f"{lang}.json"
    if not path.exists():
        return _empty_payload(lang)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_payload(lang)
    return _normalize_payload(data, lang)


def load_fallback(base_dir: Path = DEFAULT_BASE_DIR) -> Dict[str, Any]:
    """Load the English fallback file. Always callable — returns empty scaffold if missing."""
    return load_terminology_for(FALLBACK_LANG, base_dir)


def save_terminology_for(
    lang: str,
    data: Dict[str, Any],
    base_dir: Path = DEFAULT_BASE_DIR,
) -> bool:
    """Persist *data* as the terminology file for *lang*. Returns True on success."""
    try:
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / f"{lang}.json"
        payload = _normalize_payload(data, lang)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


# ── Per-campaign cache files ───────────────────────────────────────────

def _empty_campaign_payload(campaign_id: str) -> Dict[str, Any]:
    """Return an empty *campaign* payload (language-agnostic)."""
    out: Dict[str, Any] = {
        "version": SCHEMA_VERSION,
        "campaign_id": campaign_id or "",
        "imported_at": "",
        "bannerlord_language": "",
        "source": "",
        "last_campaign_day": 0,
    }
    for cat in CATEGORIES:
        out[cat] = {}
    return out


def _normalize_campaign_payload(payload: Any, campaign_id: str) -> Dict[str, Any]:
    """Return a well-shaped campaign dict even if the file is malformed."""
    if not isinstance(payload, dict):
        return _empty_campaign_payload(campaign_id)
    out = _empty_campaign_payload(campaign_id)
    out["version"] = int(payload.get("version", SCHEMA_VERSION) or SCHEMA_VERSION)
    out["campaign_id"] = str(payload.get("campaign_id") or campaign_id or "")
    out["imported_at"] = str(payload.get("imported_at") or "")
    out["bannerlord_language"] = str(payload.get("bannerlord_language") or "")
    out["source"] = str(payload.get("source") or "")
    try:
        out["last_campaign_day"] = int(payload.get("last_campaign_day") or 0)
    except (TypeError, ValueError):
        out["last_campaign_day"] = 0
    for cat in CATEGORIES:
        out[cat] = _coerce_str_dict(payload.get(cat))
    return out


def load_campaign_terminology(
    campaign_id: str,
    cache_dir: Path,
) -> Dict[str, Any]:
    """Load ``<cache_dir>/<campaign_id>.json``.

    Missing or malformed files yield an empty scaffold.  Callers should
    treat an empty payload as "no campaign-specific overrides" rather
    than as an error.
    """
    if not campaign_id:
        return _empty_campaign_payload("")
    path = Path(cache_dir) / f"{campaign_id}.json"
    if not path.exists():
        return _empty_campaign_payload(campaign_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_campaign_payload(campaign_id)
    return _normalize_campaign_payload(data, campaign_id)


def save_campaign_terminology(
    campaign_id: str,
    data: Dict[str, Any],
    cache_dir: Path,
) -> bool:
    """Persist *data* as the cache file for *campaign_id*. Returns True on success."""
    if not campaign_id:
        return False
    try:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{campaign_id}.json"
        payload = _normalize_campaign_payload(data, campaign_id)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def delete_campaign_terminology(campaign_id: str, cache_dir: Path) -> bool:
    """Delete the cache file for *campaign_id*.  Returns True if the file
    was present and removed (or already gone)."""
    if not campaign_id:
        return False
    try:
        path = Path(cache_dir) / f"{campaign_id}.json"
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


# ── Story Master companion-mod export ──────────────────────────────────
#
# The companion mod writes ``<campaign_dir>/storytools/terminology.json`` each
# session (every "name + StringId" object, including settlements).  This is the
# preferred, dependency-free source — it replaces the manual ProemConfig import.

STORYMASTER_TERMINOLOGY_FILE = "terminology.json"


def storymaster_terminology_path(campaign_dir: Path) -> Path:
    return Path(campaign_dir) / "storytools" / STORYMASTER_TERMINOLOGY_FILE


def campaign_day_now(campaign_dir: Any) -> float:
    """Latest campaign day the game reported, from ``storytools/world_snapshot.json``.

    Date pickers default to this: a line being written "now" almost always
    belongs at the current day, and typing 91119 by hand is not something a
    player can be expected to do.  Returns 0.0 when the snapshot is missing
    (no database exported yet) so callers can fall back.
    """
    if not campaign_dir:
        return 0.0
    path = Path(campaign_dir) / "storytools" / "world_snapshot.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return float(data.get("campaign_day") or 0.0)
    except Exception:
        return 0.0


def _names_only(raw: Any) -> Dict[str, str]:
    """Collapse a ``{id: {name, …}}`` (or ``{id: name}``) map to ``{id: name}``."""
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                nm = v.get("name")
                if nm:
                    out[str(k)] = str(nm)
            elif isinstance(v, str) and v:
                out[str(k)] = v
    return out


def load_storymaster_terminology(
    campaign_dir: Path,
    campaign_id: str = "",
) -> Optional[Dict[str, Any]]:
    """Read the companion mod's ``terminology.json`` into a campaign-cache payload.

    Maps the mod's per-object export to the tool's ``{category: {id: name}}``
    structure (heroes＋troops → ``characters``; ``settlements`` is new).  Returns
    ``None`` when the file is absent or unreadable so callers can fall back.
    """
    if not campaign_dir:
        return None
    path = storymaster_terminology_path(campaign_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    heroes = _names_only(data.get("heroes"))
    characters = dict(heroes)
    # Troops fill in names only where a hero id doesn't already own them.
    for k, v in _names_only(data.get("troops")).items():
        characters.setdefault(k, v)

    payload = _empty_campaign_payload(campaign_id)
    payload["source"] = "storymaster"
    payload["imported_at"] = str(data.get("exported_at") or "")
    payload["characters"] = characters
    payload["speakers"] = heroes
    payload["kingdoms"] = _names_only(data.get("kingdoms"))
    payload["cultures"] = _names_only(data.get("cultures"))
    payload["clans"] = _names_only(data.get("clans"))
    payload["items"] = _names_only(data.get("items"))
    payload["settlements"] = _names_only(data.get("settlements"))
    # Preserve the rich per-hero / per-clan attribute maps (clan, kingdom,
    # map_faction, is_lord/wanderer/notable/…, age, family) so the tool can
    # join them onto interacted characters by StringId for filtering/sorting.
    payload["hero_attrs"] = data.get("heroes") if isinstance(data.get("heroes"), dict) else {}
    payload["clan_attrs"] = data.get("clans") if isinstance(data.get("clans"), dict) else {}
    payload["troop_attrs"] = data.get("troops") if isinstance(data.get("troops"), dict) else {}
    payload["settlement_attrs"] = data.get("settlements") if isinstance(data.get("settlements"), dict) else {}
    payload["item_attrs"] = data.get("items") if isinstance(data.get("items"), dict) else {}
    payload["culture_attrs"] = data.get("cultures") if isinstance(data.get("cultures"), dict) else {}
    return payload


# ── Name ↔ ID resolution (M3 — terminology linkage) ────────────────────
#
# Lets editors accept a *name* (e.g. settlement "鄧葛蘭尼") and resolve it to the
# game id ("town_B2").  Built on the same three layers as the lookups above.

_NAME_ID_PAREN_RE = re.compile(r"^.*\(([^()]+)\)\s*$")


def merged_category(
    category: str,
    *,
    campaign: Optional[dict] = None,
    primary: Optional[dict] = None,
    fallback: Optional[dict] = None,
) -> Dict[str, str]:
    """Merge ``{id: name}`` for *category* across the three layers.

    Order is fallback → primary → campaign so the most-specific (campaign /
    companion-mod) names win on collision.
    """
    out: Dict[str, str] = {}
    for layer in (fallback, primary, campaign):
        d = (layer or {}).get(category)
        if isinstance(d, dict):
            for k, v in d.items():
                if v:
                    out[str(k)] = str(v)
    return out


def name_to_ids_index(id_to_name: Dict[str, str]) -> Dict[str, List[str]]:
    """Build ``name(lower) -> [ids]`` (duplicate names map to several ids)."""
    idx: Dict[str, List[str]] = {}
    for id_, name in (id_to_name or {}).items():
        key = str(name).strip().lower()
        if key:
            idx.setdefault(key, []).append(str(id_))
    return idx


def resolve_name_or_id(
    text: str,
    id_to_name: Dict[str, str],
    name_index: Dict[str, List[str]],
) -> Tuple[Optional[str], List[str]]:
    """Resolve *text* (a name, an id, or ``"name (id)"``) to a game id.

    Returns ``(resolved_id, candidates)``:
      * exact id, or unique name match  → ``(id, [id])``
      * ambiguous name (several ids)    → ``(None, [id, …])``
      * unknown                         → ``(None, [])``
    """
    t = (text or "").strip()
    if not t:
        return (None, [])
    # "name (id)" — trust the parenthesised id when it exists.
    m = _NAME_ID_PAREN_RE.match(t)
    if m:
        cand = m.group(1).strip()
        if cand in id_to_name:
            return (cand, [cand])
    if t in id_to_name:            # raw id
        return (t, [t])
    ids = name_index.get(t.lower())
    if ids:
        return (ids[0], list(ids)) if len(ids) == 1 else (None, list(ids))
    return (None, [])


def suggest_names(
    prefix: str,
    id_to_name: Dict[str, str],
    *,
    limit: int = 50,
) -> List[Tuple[str, str]]:
    """Return up to *limit* ``(id, name)`` pairs whose name or id contains *prefix*.

    Prefix-of-name matches sort before mere substring matches; empty prefix
    returns the first *limit* entries (name-sorted)."""
    p = (prefix or "").strip().lower()
    starts: List[Tuple[str, str]] = []
    contains: List[Tuple[str, str]] = []
    for id_, name in (id_to_name or {}).items():
        nl = str(name).lower()
        if not p:
            starts.append((id_, name))
        elif nl.startswith(p) or id_.lower().startswith(p):
            starts.append((id_, name))
        elif p in nl or p in id_.lower():
            contains.append((id_, name))
    starts.sort(key=lambda t: str(t[1]).lower())
    contains.sort(key=lambda t: str(t[1]).lower())
    return (starts + contains)[:limit]


def merge_into_campaign(
    campaign_data: Dict[str, Any],
    category: str,
    new_entries: Dict[str, str],
) -> Dict[str, Any]:
    """Return a copy of *campaign_data* with *new_entries* merged into *category*.

    Same-ID entries are overwritten (the latest game state wins) and IDs
    not mentioned in *new_entries* are preserved.  An empty dict for
    *new_entries* is a no-op.
    """
    if category not in CATEGORIES:
        raise ValueError(f"Unknown terminology category: {category}")
    out = dict(campaign_data) if isinstance(campaign_data, dict) else {}
    existing = _coerce_str_dict(out.get(category))
    if new_entries:
        for k, v in new_entries.items():
            if not isinstance(k, str):
                continue
            existing[str(k)] = str(v)
    out[category] = existing
    return out


# ── Lookups ────────────────────────────────────────────────────────────

def _lookup_in(data: dict, category: str, key: str) -> Optional[str]:
    if not key:
        return None
    if not isinstance(data, dict):
        return None
    bucket = data.get(category)
    if not isinstance(bucket, dict):
        return None
    val = bucket.get(str(key))
    if val:
        return str(val)
    return None


def _lookup(primary: dict, fallback: dict, category: str, key: str) -> Optional[str]:
    """Two-tier lookup (kept for backwards compatibility with Stage B callers)."""
    return _lookup_in(primary, category, key) or _lookup_in(fallback, category, key)


def lookup_with_campaign(
    category: str,
    key: str,
    *,
    campaign: dict,
    primary: dict,
    fallback: dict,
) -> Optional[str]:
    """Three-tier lookup: campaign → primary → fallback → ``None``."""
    return (
        _lookup_in(campaign, category, key)
        or _lookup_in(primary, category, key)
        or _lookup_in(fallback, category, key)
    )


def lookup_character(primary: dict, fallback: dict, sid: str) -> Optional[str]:
    return _lookup(primary, fallback, "characters", sid)


def lookup_kingdom(primary: dict, fallback: dict, kid: str) -> Optional[str]:
    return _lookup(primary, fallback, "kingdoms", kid)


def lookup_culture(primary: dict, fallback: dict, cid: str) -> Optional[str]:
    return _lookup(primary, fallback, "cultures", cid)


def lookup_clan(primary: dict, fallback: dict, cid: str) -> Optional[str]:
    return _lookup(primary, fallback, "clans", cid)


def lookup_item(primary: dict, fallback: dict, iid: str) -> Optional[str]:
    return _lookup(primary, fallback, "items", iid)


# ── High-level resolver for character names ────────────────────────────

# Source tag taxonomy (returned by resolve_character_name):
#   "campaign"          hit in campaign cache (most specific, freshest)
#   "library"           hit in primary-language terminology file
#   "library_fallback"  hit in en.json fallback only
#   "json"              resolved via json_resolver (character JSON meta)
#   "id_only"           nothing found — caller should style as placeholder

def resolve_character_name(
    sid: str,
    *,
    primary: dict,
    fallback: dict,
    campaign: Optional[dict] = None,
    json_resolver=None,
    exclude_library: bool = False,
) -> Tuple[str, str]:
    """Resolve a character StringId to ``(display_name, source)``.

    Resolution order::

        campaign  →  primary language  →  en.json  →  json_resolver  →  ID

    *campaign* is the per-campaign cache payload; pass an empty dict (or
    ``None``) to opt out and behave like the Stage B two-tier resolver.

    Parameters
    ----------
    sid : str
        The character StringId to look up.
    primary, fallback : dict
        Loaded terminology payloads (use :func:`load_terminology_for` /
        :func:`load_fallback`).
    campaign : dict, optional
        Loaded per-campaign payload (use :func:`load_campaign_terminology`).
        ``None`` is treated as "no campaign overrides".
    json_resolver : callable, optional
        ``(sid) -> Optional[str]``. Tried when the terminology library
        doesn't cover the id (or when *exclude_library* is True).
    exclude_library : bool, default False
        When True, skip *both* the campaign cache and the language
        library on the first pass and rely on *json_resolver* for the
        primary answer.  The library/campaign are still used as a
        last-resort fallback so synthetic IDs like ``main_hero`` still
        resolve.  Used by the main workspace's character list where the
        JSON's own Name field is authoritative.
    """
    sid = (sid or "").strip()
    if not sid:
        return ("", "id_only")

    if not exclude_library:
        if campaign is not None:
            name = _lookup_in(campaign, "characters", sid)
            if name:
                return (name, "campaign")
        name = _lookup_in(primary, "characters", sid)
        if name:
            return (name, "library")
        name = _lookup_in(fallback, "characters", sid)
        if name:
            return (name, "library_fallback")

    if json_resolver is not None:
        try:
            resolved = json_resolver(sid)
        except Exception:
            resolved = None
        if resolved:
            return (str(resolved), "json")

    # When excluded from library, still try campaign/library as last
    # resort so synthetic IDs (e.g. main_hero) still resolve.
    if exclude_library:
        if campaign is not None:
            name = _lookup_in(campaign, "characters", sid)
            if name:
                return (name, "campaign")
        name = _lookup_in(primary, "characters", sid)
        if name:
            return (name, "library")
        name = _lookup_in(fallback, "characters", sid)
        if name:
            return (name, "library_fallback")

    return (sid, "id_only")


# ── Category-level bulk helpers ────────────────────────────────────────

def get_category(data: dict, category: str) -> Dict[str, str]:
    """Return the category dict (copy) from a terminology payload."""
    raw = data.get(category) if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def set_category(data: dict, category: str, items: Dict[str, str]) -> Dict[str, Any]:
    """Return a new payload with *category* replaced by *items*."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown terminology category: {category}")
    out = dict(data) if isinstance(data, dict) else {}
    out[category] = {str(k): str(v) for k, v in items.items() if str(k).strip()}
    return out


def category_count(data: dict, category: str) -> int:
    """Return the entry count for *category*; 0 if absent or malformed."""
    raw = data.get(category) if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return 0
    return len(raw)


def total_count(data: dict, categories: Iterable[str] = CATEGORIES) -> int:
    """Return the sum of entry counts across *categories*."""
    return sum(category_count(data, c) for c in categories)
