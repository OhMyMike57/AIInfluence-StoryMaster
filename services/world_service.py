from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import json
import re


def data_samples_base(script_dir: Path) -> Path:
    """Return the directory holding the dev sample campaigns.

    These are *dev-only* fallbacks used when no campaign is loaded (tests /
    quick local runs).  Resolution order:

    1. ``script_dir/data_samples`` — legacy in-project location (if it still
       exists).
    2. ``<parent>/AIInfluence_Research/data_samples`` — the shared, cross-
       project research library the sample campaigns were centralised into.

    Falls back to the in-project path (even if absent) so callers can still
    build a non-existent path that ``load`` helpers handle gracefully.
    """
    local = script_dir / "data_samples"
    if local.is_dir():
        return local
    shared = script_dir.parent / "AIInfluence_Research" / "data_samples"
    if shared.is_dir():
        return shared
    return local


def _find_sample_world_dir(script_dir: Path) -> Optional[Path]:
    """Best-effort: locate a ``prompts/world_data`` dir under data_samples (5.0.x layout)."""
    base = data_samples_base(script_dir)
    if base.is_dir():
        for wd in sorted(base.glob("**/prompts/world_data")):
            if wd.is_dir():
                return wd
    return None


def world_data_base(
    save_data_dir: Optional[Path],
    script_dir: Path,
    campaign_dir: Optional[Path] = None,
) -> Path:
    """Return the directory that holds ``world_info.json`` / ``world_secrets.json``.

    Layout resolution (first hit wins):

    1. **5.0.x** — ``campaign_dir/prompts/world_data/`` (per-campaign). Detected
       by the directory existing on disk; AI Influence 5.0.0 moved the world
       files here from the mod root.
    2. **4.1.0** — ``save_data_dir.parent`` (the mod root; world files were
       shared across all campaigns).
    3. **dev fallback** — a ``prompts/world_data`` dir found under
       ``data_samples`` (new layout), else ``data_samples`` itself.
    """
    # 1) New per-campaign layout (5.0.x)
    if campaign_dir is not None:
        new_base = Path(campaign_dir) / "prompts" / "world_data"
        if new_base.is_dir():
            return new_base
    # 2) Old mod-root layout (4.1.0)
    if save_data_dir is not None:
        return Path(save_data_dir).parent
    # 3) Dev/testing fallback
    sample = _find_sample_world_dir(script_dir)
    return sample if sample is not None else data_samples_base(script_dir)


def world_paths_for_app(
    save_data_dir: Optional[Path],
    script_dir: Path,
    campaign_dir: Optional[Path] = None,
) -> Tuple[Path, Path]:
    """Return (world_info.json, world_secrets.json) for the active layout.

    5.0.x stores these per-campaign under ``prompts/world_data/``; 4.1.0 stored
    them at the mod root.  See :func:`world_data_base` for resolution order.
    """
    base = world_data_base(save_data_dir, script_dir, campaign_dir)
    return base / "world_info.json", base / "world_secrets.json"


# 5.0.x unified diplomacy bundle: dynamic events live under the
# ``dynamic_events`` key together with kingdom_statements / response pressure /
# kingdom_tax.  4.1.0 used a standalone top-level-array dynamic_events.json.
DIPLOMACY_BUNDLE_FILENAME = "aiinfluence_campaign_diplomacy.json"
LEGACY_DYNAMIC_EVENTS_FILENAME = "dynamic_events.json"


def dynamic_events_path_for_app(campaign_dir: Optional[Path], script_dir: Path) -> Path:
    """Return the file that holds dynamic events for the current campaign.

    Resolution (first hit wins):
      1. **5.0.x** — ``campaign_dir/aiinfluence_campaign_diplomacy.json``
         (events under the ``dynamic_events`` key).
      2. **4.1.0** — ``campaign_dir/dynamic_events.json`` (bare array).
      3. Dev fallback — search data_samples campaign subfolders for either.
    """
    if campaign_dir is not None:
        bundle = campaign_dir / DIPLOMACY_BUNDLE_FILENAME
        if bundle.exists():
            return bundle
        return campaign_dir / LEGACY_DYNAMIC_EVENTS_FILENAME
    # Fallback: look for any campaign folder under data_samples with either file.
    base = data_samples_base(script_dir)
    if base.is_dir():
        for name in (DIPLOMACY_BUNDLE_FILENAME, LEGACY_DYNAMIC_EVENTS_FILENAME):
            for p in sorted(base.glob(f"**/{name}")):
                # Skip mod snapshot copies — they are restore points, not live data.
                if "save_snapshots" not in p.parts:
                    return p
    return base / LEGACY_DYNAMIC_EVENTS_FILENAME  # non-existent; load handles it


def load_dynamic_events(path: Path, loader: Callable[[Path], Any]) -> List[dict]:
    """Load and return the dynamic events list from disk.

    Accepts both layouts: a 5.0.x bundle dict (events under ``dynamic_events``)
    and the legacy 4.1.0 bare array.
    """
    data = loader(path) if path.exists() else []
    if isinstance(data, dict):
        ev = data.get("dynamic_events", [])
        return ev if isinstance(ev, list) else []
    return data if isinstance(data, list) else []


# ── Economic effects data ─────────────────────────────────────────────────────

def economic_effects_path_for_app(campaign_dir: Optional[Path], script_dir: Path) -> Path:
    """Return economic_effects.json path for the current campaign.

    economic_effects.json lives INSIDE the campaign folder (per-save data).
    """
    if campaign_dir is not None:
        return campaign_dir / "economic_effects.json"
    # Fallback: look for any campaign subfolder under data_samples that has the file.
    base = data_samples_base(script_dir)
    if base.is_dir():
        for subdir in sorted(base.iterdir()):
            if subdir.is_dir():
                p = subdir / "economic_effects.json"
                if p.exists():
                    return p
    return base / "economic_effects.json"


def load_economic_effects(path: Path, loader: Callable[[Path], Any]) -> List[dict]:
    """Load and return the economic effects list from disk."""
    data = loader(path) if path.exists() else []
    return data if isinstance(data, list) else []


# ── Disease data ──────────────────────────────────────────────────────────────

def _disease_sample_campaign(script_dir: Path) -> Optional[Path]:
    """Return the first data_samples campaign dir that contains diseases.json."""
    base = data_samples_base(script_dir)
    if base.is_dir():
        for subdir in sorted(base.iterdir()):
            if subdir.is_dir() and (subdir / "diseases.json").exists():
                return subdir
    return None


def disease_paths_for_app(
    campaign_dir: Optional[Path], script_dir: Path
) -> Tuple[Path, Path]:
    """Return (diseases.json, disease_instances.json) paths for the current campaign.

    Both files live INSIDE the campaign folder (per-save data).
    """
    if campaign_dir is not None:
        return campaign_dir / "diseases.json", campaign_dir / "disease_instances.json"
    fallback = _disease_sample_campaign(script_dir)
    if fallback:
        return fallback / "diseases.json", fallback / "disease_instances.json"
    base = data_samples_base(script_dir)
    return base / "diseases.json", base / "disease_instances.json"


def load_disease_data(
    def_path: Path, inst_path: Path, loader: Callable[[Path], Any]
) -> Tuple[List[dict], List[dict]]:
    """Load (disease definitions, disease instances) from disk."""
    defs = loader(def_path) if def_path.exists() else []
    insts = loader(inst_path) if inst_path.exists() else []
    return (
        defs if isinstance(defs, list) else [],
        insts if isinstance(insts, list) else [],
    )


def dump_disease_instances(path: Path, instances: List[dict]) -> None:
    """Write disease instances to disk (definitions are read-only)."""
    raw = json.dumps(instances, ensure_ascii=False, indent=2)
    path.write_text(_compact_simple_arrays(raw), encoding="utf-8")


def load_world_items(info_path: Path, secret_path: Path, loader: Callable[[Path], Any]) -> Tuple[List[dict], List[dict]]:
    """Load and return (world_info items, world_secrets items) from disk."""
    info_data = loader(info_path) if info_path.exists() else []
    sec_data = loader(secret_path) if secret_path.exists() else []
    return (
        info_data if isinstance(info_data, list) else [],
        sec_data if isinstance(sec_data, list) else [],
    )


def _compact_simple_arrays(text: str) -> str:
    # Collapse arrays that contain only scalar values into one line.
    pattern = re.compile(
        r'\[\n((?:\s+(?:"[^"]*"|-?\d+(?:\.\d+)?|true|false|null)(?:,)?\n)+)\s*\]',
        re.IGNORECASE,
    )

    def repl(match: re.Match[str]) -> str:
        block = match.group(1)
        vals = []
        for ln in block.splitlines():
            v = ln.strip().rstrip(',')
            if v:
                vals.append(v)
        return "[" + ", ".join(vals) + "]"

    prev = None
    cur = text
    max_iterations = 500
    iterations = 0
    while cur != prev and iterations < max_iterations:
        prev = cur
        cur = pattern.sub(repl, cur)
        iterations += 1
    return cur


def dump_world_items(path: Path, items: List[dict]) -> None:
    """Write world items to disk with compact single-line arrays for readability."""
    raw = json.dumps(items, ensure_ascii=False, indent=2)
    path.write_text(_compact_simple_arrays(raw), encoding="utf-8")


def clone_items(items: List[dict]) -> List[dict]:
    """Return a deep copy of a list of world items."""
    return json.loads(json.dumps(items, ensure_ascii=False))


def move_item(items: List[dict], idx: int, delta: int) -> Tuple[int, bool]:
    """Move item at idx by delta positions. Returns (new_idx, moved)."""
    if idx < 0 or idx >= len(items):
        return idx, False
    new_idx = max(0, min(len(items) - 1, idx + delta))
    if new_idx == idx:
        return idx, False
    item = items.pop(idx)
    items.insert(new_idx, item)
    return new_idx, True


def build_owner_index_from_characters(
    characters: Sequence[Tuple[str, Path]], loader: Callable[[Path], Any]
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Build (info_owner_map, secret_owner_map) from all character JSON files."""
    info_owners: Dict[str, set] = {}
    secret_owners: Dict[str, set] = {}
    for display, pth in characters:
        d = loader(pth) or {}
        known_info = d.get("KnownInfo", []) if isinstance(d, dict) else []
        known_secrets = d.get("KnownSecrets", []) if isinstance(d, dict) else []
        if isinstance(known_info, list):
            for info_id in known_info:
                key = str(info_id).strip()
                if key:
                    info_owners.setdefault(key, set()).add(display)
        if isinstance(known_secrets, list):
            for sec_id in known_secrets:
                key = str(sec_id).strip()
                if key:
                    secret_owners.setdefault(key, set()).add(display)
    return (
        {k: sorted(v) for k, v in info_owners.items()},
        {k: sorted(v) for k, v in secret_owners.items()},
    )


def owners_for_item(owner_map: Dict[str, List[str]], item_id: str) -> List[str]:
    """Return the list of character display names that own the given item."""
    return list(owner_map.get(item_id, [])) if item_id else []


def reverse_owner_maps(
    info_owner_map: Dict[str, List[str]], secret_owner_map: Dict[str, List[str]]
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Invert item→characters maps to character→items maps for save operations."""
    info_rev: Dict[str, List[str]] = {}
    for iid, owners in info_owner_map.items():
        for name in owners:
            info_rev.setdefault(name, []).append(iid)

    sec_rev: Dict[str, List[str]] = {}
    for sid, owners in secret_owner_map.items():
        for name in owners:
            sec_rev.setdefault(name, []).append(sid)

    return info_rev, sec_rev
