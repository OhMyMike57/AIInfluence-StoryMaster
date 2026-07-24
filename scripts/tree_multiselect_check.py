"""Regression: drag-select coexists with Ctrl/Shift multi-select (v1.1.0 R4).

The 對話歷史／資料庫／疾病／對話觀察 lists are ``ttk.Treeview``s, which have no
native drag-select, so ``ui.tree_helpers.enable_drag_select`` adds one.  The
first version replaced the selection on *any* B1 motion, so the 1-pixel jitter
of a Ctrl-click rubber-banded a contiguous range over the multi-selection the
user was building — the exact complaint this fixes.

The handler binds real Python callables (``add="+"``); we capture them with a
``bind`` shim, then fire synthetic press/motion/release events to check the two
guards directly:

  1. a plain drag across rows rubber-bands the range;
  2. a click that jitters in place leaves the selection untouched;
  3. a Ctrl/Shift-held press never engages drag (Tk keeps its native select).

Run: python scripts/tree_multiselect_check.py
"""
import os
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Capture the drag callbacks by shimming Treeview.bind *before* importing the
# helper's callers — enable_drag_select binds through this method.
_CB = {}
_ORIG_BIND = ttk.Treeview.bind
_DRAG_SEQS = ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>")


def _capturing_bind(self, sequence=None, func=None, add=None):
    if func is not None and sequence in _DRAG_SEQS:
        _CB.setdefault((str(self), sequence), []).append(func)
    return _ORIG_BIND(self, sequence, func, add)


ttk.Treeview.bind = _capturing_bind

from ui.tree_helpers import enable_drag_select, _SHIFT, _CONTROL  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class _Ev:
    def __init__(self, y, state=0, x=30):
        self.x, self.y, self.state = x, y, state


def main():
    root = tk.Tk()
    root.withdraw()
    tree = ttk.Treeview(root, columns=("a",), show="headings",
                        selectmode="extended", height=10)
    tree.heading("a", text="A")
    iids = [tree.insert("", "end", values=(f"row{i}",)) for i in range(10)]
    tree.pack()
    root.update_idletasks()

    enable_drag_select(tree)

    # A withdrawn window has no geometry, so stub the hit tests the handler uses.
    def y_of(i):
        return 20 + i * 18
    row_y = {y_of(i): iids[i] for i in range(10)}
    tree.identify_region = lambda x, y: "cell"
    tree.identify_row = lambda y: row_y.get(y, "")
    tree.winfo_height = lambda: 200

    key = str(tree)

    def fire(seq, ev):
        for fn in _CB.get((key, seq), []):
            fn(ev)

    def press(ev):
        fire("<ButtonPress-1>", ev)

    def motion(ev):
        fire("<B1-Motion>", ev)

    def release(ev):
        fire("<ButtonRelease-1>", ev)

    check("drag callbacks were captured", bool(_CB.get((key, "<B1-Motion>"))))

    # ── 1. plain drag rubber-bands the range ──────────────────────────
    tree.selection_set(())
    press(_Ev(y_of(2)))
    motion(_Ev(y_of(5)))
    check("plain drag selects the dragged-over range",
          list(tree.selection()) == iids[2:6])
    release(_Ev(y_of(5)))

    # ── 2. a click that jitters in place leaves the selection alone ───
    tree.selection_set([iids[1], iids[4], iids[7]])   # a Ctrl-built selection
    press(_Ev(y_of(4)))            # press on one of them
    motion(_Ev(y_of(4) + 2))       # 2px jitter, still the same row
    check("in-place jitter does not rubber-band",
          list(tree.selection()) == [iids[1], iids[4], iids[7]])
    release(_Ev(y_of(4)))

    # ── 3. modifier-held press never engages drag ────────────────────
    for name, mod in (("Ctrl", _CONTROL), ("Shift", _SHIFT)):
        tree.selection_set([iids[1], iids[4], iids[7]])
        press(_Ev(y_of(4), state=mod))
        motion(_Ev(y_of(8), state=mod))     # even a real move must not fire
        check(f"{name}-held drag leaves the multi-selection intact",
              list(tree.selection()) == [iids[1], iids[4], iids[7]])
        release(_Ev(y_of(8)))

    # ── drag still works right after a modifier click (anchor reset) ──
    tree.selection_set(())
    press(_Ev(y_of(0)))
    motion(_Ev(y_of(3)))
    check("plain drag works again after a modifier click",
          list(tree.selection()) == iids[0:4])
    release(_Ev(y_of(3)))

    # ── a browse (single-select) tree gets no drag bindings ───────────
    single = ttk.Treeview(root, columns=("a",), selectmode="browse")
    _CB.clear()
    enable_drag_select(single)
    check("no drag bindings added to a single-select tree",
          not _CB.get((str(single), "<B1-Motion>")))

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] tree multiselect check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] tree multiselect check passed")


if __name__ == "__main__":
    main()
