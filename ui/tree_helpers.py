"""Reusable ``ttk.Treeview`` behaviors shared across tabs.

Keeping the click-to-sort logic in one place means the 資料庫 and 疾病 lists
(and any future Treeview) behave identically.
"""
from __future__ import annotations

import re
from tkinter import ttk

# Leading signed number in a cell, so values like "12.3%" sort by 12.3.
_LEAD_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def enable_select_all(tree: ttk.Treeview) -> None:
    """Bind Ctrl+A to "select every row" on a multi-select Treeview.

    Tk gives Treeview no select-all of its own, which is why lists used to need
    an explicit 全選 button.  Applied to every ``selectmode="extended"`` list so
    the shortcut works the same everywhere.  A no-op on ``browse`` trees, which
    can only ever hold one selection.
    """
    if str(tree.cget("selectmode")) != "extended":
        return

    def _select_all(_event=None):
        tree.selection_set(tree.get_children(""))
        return "break"

    tree.bind("<Control-a>", _select_all)
    tree.bind("<Control-A>", _select_all)


# Modifier bits in a Tk event's ``state`` field.
_SHIFT, _CONTROL = 0x0001, 0x0004


def enable_drag_select(tree: ttk.Treeview) -> None:
    """Let the user rubber-band a range of rows by holding the button and dragging.

    ``ttk.Treeview`` has no drag-select of its own — plain Tk only extends the
    selection with Shift/Ctrl clicks — so selecting a run of rows meant clicking
    the first and Shift-clicking the last.  Dragging past the top/bottom edge
    scrolls, so a range longer than the visible list still works.

    Coexisting with Ctrl/Shift multi-select (the point of this rewrite): a
    ``tk.Listbox`` does both natively, but our custom handler used to replace
    the selection on *any* B1 motion, so the tiny jitter of a Ctrl-click
    rubber-banded a contiguous range over the multi-selection the user was
    building.  Two guards fix it, matching the Listbox feel:

      * a click with Shift or Control held is left entirely to Tk, and
      * rubber-banding only begins once the pointer reaches a *different* row,
        so a click that trembles in place never touches the selection.

    A no-op on single-selection trees.  Bound with ``add="+"`` so Tk's own
    click handling (Ctrl/Shift, focus, activation) still runs.
    """
    if str(tree.cget("selectmode")) != "extended":
        return

    state = {"anchor": None, "dragging": False}

    def _press(event):
        state["dragging"] = False
        # A modifier-held click is a Ctrl/Shift multi-select — hand it wholly to
        # Tk; engaging here would fight it.
        if event.state & (_SHIFT | _CONTROL):
            state["anchor"] = None
            return None
        # Ignore presses on headings and column separators — those belong to
        # sorting and column resizing.
        if tree.identify_region(event.x, event.y) not in ("tree", "cell"):
            state["anchor"] = None
            return None
        state["anchor"] = tree.identify_row(event.y)
        return None

    def _motion(event):
        anchor = state["anchor"]
        if not anchor:
            return None
        # Drag beyond the edge → scroll so long ranges are reachable.
        if event.y < 0:
            tree.yview_scroll(-1, "units")
        elif event.y > tree.winfo_height():
            tree.yview_scroll(1, "units")
        row = tree.identify_row(event.y)
        if not row:
            return "break" if state["dragging"] else None
        rows = list(tree.get_children(""))
        try:
            i, j = rows.index(anchor), rows.index(row)
        except ValueError:
            return None
        # Until the pointer has actually left the pressed row this is a click,
        # not a drag — leave the selection (and Tk's own click handling) alone.
        if not state["dragging"]:
            if row == anchor:
                return None
            state["dragging"] = True
        lo, hi = (i, j) if i <= j else (j, i)
        tree.selection_set(rows[lo:hi + 1])
        return "break"

    def _release(_event):
        state["anchor"] = None
        state["dragging"] = False

    tree.bind("<ButtonPress-1>", _press, add="+")
    tree.bind("<B1-Motion>", _motion, add="+")
    tree.bind("<ButtonRelease-1>", _release, add="+")


def make_sortable(tree: ttk.Treeview, numeric_cols=()) -> None:
    """Wire click-to-sort on every column heading (toggles asc/desc).

    Reorders the existing rows via ``tree.move`` (no re-render) — fine for the
    few-thousand-row cap.  Sort state lives on the tree instance.  Columns in
    *numeric_cols* are compared by their leading signed number.
    """
    numeric = set(numeric_cols)
    tree._sort_state = {}
    # Every sortable list is a list users select in, so the selection niceties
    # belong here too (both self-limit to multi-selection trees).
    enable_select_all(tree)
    enable_drag_select(tree)

    def _num_key(v):
        m = _LEAD_NUM_RE.search(str(v))
        if not m:
            return (1, 0.0)   # blanks / non-numeric sort last (asc)
        try:
            return (0, float(m.group()))
        except (TypeError, ValueError):
            return (1, 0.0)

    def sort_by(col):
        rev = not tree._sort_state.get(col, False)
        tree._sort_state = {col: rev}
        rows = []
        for iid in tree.get_children(""):
            val = tree.item(iid, "text") if col == "#0" else tree.set(iid, col)
            rows.append((val, iid))

        def key(pair):
            if col in numeric:
                return _num_key(pair[0])
            return (0, str(pair[0]).lower())

        rows.sort(key=key, reverse=rev)
        for idx, (_v, iid) in enumerate(rows):
            tree.move(iid, "", idx)

    cols = ("#0",) + tuple(tree["columns"])
    for c in cols:
        tree.heading(c, command=lambda col=c: sort_by(col))
