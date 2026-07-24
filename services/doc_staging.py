"""Per-character staged working copies (v0.36.0 主工作區暫存機制).

One unified model replaces per-operation staging: every main-workspace edit
checks out a deep-copied **working document** for that character's JSON,
mutates it, and the UI renders from the working copy.  Nothing touches disk
until the user hits the global 💾 儲存 (top-right); ↩ 取消 discards.

Three parallel maps, all keyed by the character JSON ``Path``:

* ``base``       — deep-copied disk snapshot taken at checkout time.  All
  dirty/diff computations compare **pending vs base** (no disk re-reads).
* ``pending``    — the working document callers mutate.
* ``base_mtime`` — the file's mtime at checkout, for detecting that the game
  (or anything external) rewrote the file while changes were pending.

The caller (the app) owns persistence (`commit_all` takes its writer),
logging, and UI refresh.  ``staging_service`` (the Stage-C list-mutation
buffer) is superseded by this module for the main workspace.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

JsonLoader = Callable[[Path], Optional[dict]]
JsonWriter = Callable[[Path, dict], bool]


class DocStaging:
    def __init__(self) -> None:
        self.base:       Dict[Path, dict]  = {}
        self.pending:    Dict[Path, dict]  = {}
        self.base_mtime: Dict[Path, float] = {}

    # ── checkout / store / read ───────────────────────────────────────────
    def checkout(self, path, loader: JsonLoader) -> dict:
        """Return the working copy for *path*, creating it from disk on first use."""
        path = Path(path)
        if path not in self.pending:
            data = loader(path)
            data = data if isinstance(data, dict) else {}
            self.base[path] = copy.deepcopy(data)
            self.pending[path] = copy.deepcopy(data)
            self.base_mtime[path] = self._mtime(path)
        return self.pending[path]

    def put(self, path, doc: dict, loader: JsonLoader) -> None:
        """Replace the working copy wholesale (e.g. the JSON tab's editor).

        Captures the disk baseline first when *path* was not yet staged, so
        the diff still compares against what was on disk before the edit.
        """
        path = Path(path)
        if path not in self.base:
            data = loader(path)
            self.base[path] = copy.deepcopy(data if isinstance(data, dict) else {})
            self.base_mtime[path] = self._mtime(path)
        self.pending[path] = doc

    def peek(self, path, loader: JsonLoader) -> dict:
        """Effective read: the working copy when staged, else fresh disk data.

        Read-only by contract — mutate only documents obtained via checkout().
        """
        path = Path(path)
        if path in self.pending:
            return self.pending[path]
        data = loader(path)
        return data if isinstance(data, dict) else {}

    # ── dirtiness ─────────────────────────────────────────────────────────
    def is_dirty(self, path) -> bool:
        path = Path(path)
        return path in self.pending and self.pending[path] != self.base.get(path)

    def dirty_paths(self) -> List[Path]:
        return [p for p in self.pending if self.pending[p] != self.base.get(p)]

    def prune_clean(self) -> int:
        """Drop staged entries whose working copy equals its baseline."""
        clean = [p for p in self.pending if self.pending[p] == self.base.get(p)]
        for p in clean:
            self._drop(p)
        return len(clean)

    # ── diff / conflicts ──────────────────────────────────────────────────
    def diff_all(self, name_getter: Callable[[Path], str]) -> List[Dict[str, Any]]:
        """Field-level diff records for a review dialog.

        Each: ``{path, name, field, old, new}`` — one per changed field,
        compared against the checkout-time baseline.
        """
        items: List[Dict[str, Any]] = []
        for p in self.dirty_paths():
            base = self.base.get(p) or {}
            cur = self.pending[p]
            name = name_getter(p)
            for field in list(base.keys()) + [k for k in cur.keys() if k not in base]:
                old, new = base.get(field), cur.get(field)
                if old == new:
                    continue
                items.append({"path": p, "name": name, "field": field,
                              "old": old, "new": new})
        return items

    def conflicted_paths(self) -> List[Path]:
        """Dirty paths whose file changed on disk since checkout (mtime moved)."""
        out = []
        for p in self.dirty_paths():
            if self._mtime(p) != self.base_mtime.get(p, 0.0):
                out.append(p)
        return out

    # ── discard / commit ──────────────────────────────────────────────────
    def discard(self, path=None) -> int:
        """Drop the working copy for *path* (or all).  Returns dropped count."""
        if path is not None:
            p = Path(path)
            if p in self.pending:
                self._drop(p)
                return 1
            return 0
        n = len(self.pending)
        self.base.clear()
        self.pending.clear()
        self.base_mtime.clear()
        return n

    def commit_all(self, writer: JsonWriter) -> Dict[Path, Optional[str]]:
        """Write every dirty working copy to disk via *writer*.

        Returns ``{path: None | error}``.  Successful writes are dropped from
        staging; failures stay staged so the user can retry.
        """
        results: Dict[Path, Optional[str]] = {}
        for p in self.dirty_paths():
            try:
                ok = writer(p, self.pending[p])
            except Exception as exc:  # writer must not kill the batch
                ok, err = False, str(exc)
            else:
                err = None if ok else "writer returned False"
            if ok:
                results[p] = None
                self._drop(p)
            else:
                results[p] = err
        # Clean entries (checked out but unchanged) can go too.
        self.prune_clean()
        return results

    # ── internals ─────────────────────────────────────────────────────────
    def _drop(self, p: Path) -> None:
        self.pending.pop(p, None)
        self.base.pop(p, None)
        self.base_mtime.pop(p, None)

    @staticmethod
    def _mtime(p: Path) -> float:
        try:
            return Path(p).stat().st_mtime
        except OSError:
            return 0.0


def list_delta(base_doc: dict, staged_doc: dict, field: str) -> tuple:
    """(adds, removes) for a list-valued *field*, staged vs base — the derived
    replacement for the old ListMutation pending sets (owned info/secrets/events)."""
    def _ids(doc):
        arr = (doc or {}).get(field)
        if not isinstance(arr, list):
            return set()
        return {str(x).strip() for x in arr if str(x).strip()}
    b, s = _ids(base_doc), _ids(staged_doc)
    return (s - b, b - s)
