"""Staging buffer service for character JSON edits.

Two flavours of staged change are supported:

1. **Field changes** — replace a top-level field's value
   (e.g. ``CharacterDescription`` ← new string).  Used by Phase 4's
   diff-submit dialog flow.

2. **List mutations** (Phase 5 Stage C) — add/remove ID strings from a
   list-valued field (e.g. ``KnownInfo``, ``KnownSecrets``,
   ``DynamicEvents``).  Used by ``OwnedItemsViewer`` and the disease
   tab's buffered editing.

Both kinds are pure-data containers; the caller (the main app) owns
persistence, undo history, and UI refresh.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set


JsonLoader = Callable[[Path], Dict[str, Any] | None]


# ── Field-level staging (existing) ─────────────────────────────────────

def queue_field_change(pending_changes: Dict[Path, Dict[str, Any]], path: Path, field: str, value: Any) -> None:
    """Stage a field change for a character JSON without writing to disk."""
    if path not in pending_changes:
        pending_changes[path] = {}
    pending_changes[path][field] = value


def effective_data(path: Path, pending_changes: Dict[Path, Dict[str, Any]], loader: JsonLoader) -> Dict[str, Any]:
    """Return on-disk data merged with any staged changes for the given path."""
    data = loader(path) or {}
    staged = pending_changes.get(path, {})
    if not isinstance(data, dict):
        data = {}
    if staged:
        merged = dict(data)
        merged.update(staged)
        return merged
    return data


def build_diff_items(
    pending_changes: Dict[Path, Dict[str, Any]],
    loader: JsonLoader,
    name_getter: Callable[[Path], str],
) -> List[Dict[str, Any]]:
    """Build a flat list of diff records (path, name, field, old, new) from staged changes."""
    items: List[Dict[str, Any]] = []
    for path, changes in pending_changes.items():
        original = loader(path) or {}
        if not isinstance(original, dict):
            continue
        name = name_getter(path)
        for field_name, new_val in changes.items():
            old_val = original.get(field_name)
            if old_val == new_val:
                continue
            items.append(
                {
                    "path": path,
                    "name": name,
                    "field": field_name,
                    "old": old_val,
                    "new": new_val,
                }
            )
    return items


def template_from_data(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """Extract a subset of fields from data to form a reusable template."""
    return {field_name: data.get(field_name) for field_name in fields if field_name in data}


# ── List-mutation staging (Stage C) ────────────────────────────────────

@dataclass
class ListMutation:
    """Staged add/remove operations against a list-valued field.

    Invariant maintained by :func:`queue_list_mutation`:
    ``adds`` and ``removes`` never share an ID — registering both for the
    same ID cancels the pair (treated as a no-op against current state).
    """

    adds:    Set[str] = field(default_factory=set)
    removes: Set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not self.adds and not self.removes

    def total_count(self) -> int:
        return len(self.adds) + len(self.removes)

    def copy(self) -> "ListMutation":
        return ListMutation(adds=set(self.adds), removes=set(self.removes))


def queue_list_mutation(
    pending: Dict[Path, Dict[str, ListMutation]],
    path: Path,
    field_name: str,
    *,
    add: Optional[str] = None,
    remove: Optional[str] = None,
) -> None:
    """Stage a single add/remove operation for ``path[field_name]``.

    Conflict resolution (per ID):
      * stage-add an ID that's pending-removal → cancels the pair
        (net effect: keep the existing entry).
      * stage-remove an ID that's pending-addition → cancels the pair
        (net effect: don't add the entry).
      * Re-staging the same op (add an ID twice, etc.) is idempotent.

    Empty ``ListMutation`` are removed; empty inner dicts are removed;
    the outer ``pending`` dict is therefore always minimal.
    """
    if (add is None) == (remove is None):
        raise ValueError("queue_list_mutation: pass exactly one of add= / remove=")

    bucket = pending.setdefault(path, {})
    mut = bucket.setdefault(field_name, ListMutation())

    if add is not None:
        if add in mut.removes:
            mut.removes.discard(add)  # cancel pair
        else:
            mut.adds.add(add)
    else:
        # remove path
        rid = remove
        if rid in mut.adds:
            mut.adds.discard(rid)  # cancel pair
        else:
            mut.removes.add(rid)

    # Garbage-collect empty containers so the caller can use truthiness checks.
    if mut.is_empty():
        del bucket[field_name]
        if not bucket:
            del pending[path]


def effective_list(
    path: Path,
    field_name: str,
    pending: Dict[Path, Dict[str, ListMutation]],
    current: Iterable[str],
) -> List[str]:
    """Return ``current`` with pending add/remove applied (preserving order).

    Order rules:
      1. Existing entries appear in their original order, **except** those
         in ``pending.removes`` are skipped.
      2. Entries in ``pending.adds`` are appended after the surviving
         existing entries, sorted lexicographically for stability.
    """
    mut = pending.get(path, {}).get(field_name)
    if mut is None or mut.is_empty():
        return list(current)
    out: List[str] = [x for x in current if x not in mut.removes]
    # Avoid duplicating IDs that already exist in current (defensive).
    existing = set(out)
    for new_id in sorted(mut.adds):
        if new_id not in existing:
            out.append(new_id)
            existing.add(new_id)
    return out


def pending_count(
    pending: Dict[Path, Dict[str, ListMutation]],
    *,
    path: Optional[Path] = None,
    field_name: Optional[str] = None,
) -> int:
    """Return the total mutation count, optionally filtered by path/field."""
    total = 0
    for p, fields in pending.items():
        if path is not None and p != path:
            continue
        for f, mut in fields.items():
            if field_name is not None and f != field_name:
                continue
            total += mut.total_count()
    return total


def build_list_diff_summary(
    pending: Dict[Path, Dict[str, ListMutation]],
    name_getter: Callable[[Path], str],
) -> List[Dict[str, Any]]:
    """Produce a flat diff list suitable for a confirmation dialog.

    Each entry: ``{path, name, field, op, id}`` where ``op`` is
    ``"add"`` or ``"remove"``.
    """
    items: List[Dict[str, Any]] = []
    for p, fields in pending.items():
        name = name_getter(p)
        for field_name, mut in fields.items():
            for sid in sorted(mut.adds):
                items.append({"path": p, "name": name, "field": field_name, "op": "add", "id": sid})
            for sid in sorted(mut.removes):
                items.append({"path": p, "name": name, "field": field_name, "op": "remove", "id": sid})
    return items


def discard_list_mutations(
    pending: Dict[Path, Dict[str, ListMutation]],
    *,
    path: Optional[Path] = None,
    field_name: Optional[str] = None,
) -> int:
    """Drop pending mutations matching the filters; return how many were dropped.

    * ``path=None, field_name=None``       → clear all
    * ``path=X, field_name=None``          → clear all fields under X
    * ``path=X, field_name=F``             → clear just X[F]
    * ``path=None, field_name=F``          → clear F across every path
    """
    dropped = 0
    for p in list(pending.keys()):
        if path is not None and p != path:
            continue
        bucket = pending[p]
        for f in list(bucket.keys()):
            if field_name is not None and f != field_name:
                continue
            dropped += bucket[f].total_count()
            del bucket[f]
        if not bucket:
            del pending[p]
    return dropped


def apply_list_mutations(
    pending: Dict[Path, Dict[str, ListMutation]],
    loader: JsonLoader,
    writer: Callable[[Path, Dict[str, Any]], bool],
    *,
    field_filter: Optional[Iterable[str]] = None,
) -> Dict[Path, Dict[str, Any]]:
    """Apply pending mutations to disk, returning a per-path success/error map.

    For each path:
      1. Load JSON via *loader*.
      2. For each (field, ListMutation) — only if field is in *field_filter*
         (or filter is None) — apply removes then adds.
      3. Write via *writer*.

    *writer* must return True on success.  Mutations whose write succeeds
    are removed from *pending*; failed writes leave them in place.

    Returns: ``{path: {"applied_fields": [...], "error": Optional[str]}}``.
    """
    results: Dict[Path, Dict[str, Any]] = {}
    keep_filter = set(field_filter) if field_filter is not None else None

    for p in list(pending.keys()):
        bucket = pending[p]
        applied_fields: List[str] = []
        try:
            data = loader(p) or {}
            if not isinstance(data, dict):
                data = {}
            for f in list(bucket.keys()):
                if keep_filter is not None and f not in keep_filter:
                    continue
                mut = bucket[f]
                arr = data.get(f, [])
                if not isinstance(arr, list):
                    arr = []
                # Apply removes
                if mut.removes:
                    arr = [x for x in arr if x not in mut.removes]
                # Apply adds (de-dupe)
                if mut.adds:
                    existing = set(arr)
                    for a in sorted(mut.adds):
                        if a not in existing:
                            arr.append(a)
                            existing.add(a)
                data[f] = arr
                applied_fields.append(f)
            ok = writer(p, data)
            if ok:
                # Remove the applied fields from pending
                for f in applied_fields:
                    bucket.pop(f, None)
                if not bucket:
                    del pending[p]
                results[p] = {"applied_fields": applied_fields, "error": None}
            else:
                results[p] = {"applied_fields": [], "error": "writer returned False"}
        except Exception as exc:
            results[p] = {"applied_fields": [], "error": str(exc)}
    return results
