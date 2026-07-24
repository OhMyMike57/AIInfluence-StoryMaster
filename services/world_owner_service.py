from __future__ import annotations

from typing import Dict, List, Any, Tuple


def remove_owners(owner_map: Dict[str, List[str]], item_id: str, selected_names: List[str]) -> Tuple[Dict[str, List[str]], int]:
    """Remove specific named owners from an item's owner list. Returns (map, removed_count)."""
    if not item_id or not selected_names:
        return owner_map, 0
    removed_set = set(selected_names)
    original = list(owner_map.get(item_id, []))
    updated = [x for x in original if x not in removed_set]
    removed_count = len(original) - len(updated)
    if updated:
        owner_map[item_id] = updated
    else:
        owner_map.pop(item_id, None)
    return owner_map, removed_count


def clear_owners(owner_map: Dict[str, List[str]], item_id: str) -> Tuple[Dict[str, List[str]], int]:
    """Remove all owners for an item. Returns (map, cleared_count)."""
    current = list(owner_map.get(item_id, [])) if item_id else []
    owner_map.pop(item_id, None)
    return owner_map, len(current)


def clone_payload(kind: str, item_id: str, label: str, owners: List[str]) -> Dict[str, Any]:
    """Build a clone payload dict from a world item's current owner list."""
    return {"kind": kind, "id": item_id, "owners": list(owners), "label": label}


def apply_clone(owner_map: Dict[str, List[str]], item_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, List[str]], int]:
    """Apply a previously cloned owner list to a target item. Returns (map, applied_count)."""
    owners = list(payload.get("owners", []))
    if not item_id:
        return owner_map, 0
    owner_map[item_id] = owners
    return owner_map, len(owners)
