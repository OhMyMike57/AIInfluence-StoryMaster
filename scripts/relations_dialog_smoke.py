"""Smoke: 關聯角色清單視窗 — eavesdropper & sharer views (v1.2.0).

Both views share ``dialogs.relations_dialog``; this drives each opener and the
generic dialog's wiring:

  1. one row per related character, columns per view (dist/heard vs speaker/line);
  2. multi-select; double-click / bottom / right-click add the right KEYS;
  3. delete confirms, cleans each row via on_clean(key, token), drops rows,
     closes when empty;
  4. an empty list opens no window.

Run: python scripts/relations_dialog_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dialogs import relations_dialog as RD  # noqa: E402
from services.radiation_service import Eavesdropper, Sharer  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class FakeApp:
    def __init__(self, root):
        self.root = root


def make(app, opener, **kwargs):
    """Open a dialog and return its _RelationsDialog instance."""
    created = []
    orig = RD._RelationsDialog.__init__

    def spy(self, a, spec):
        created.append(self)
        orig(self, a, spec)

    RD._RelationsDialog.__init__ = spy
    try:
        opener(app, **kwargs)
    finally:
        RD._RelationsDialog.__init__ = orig
    return created[-1] if created else None


class _Ev:
    def __init__(self, y):
        self.y, self.x_root, self.y_root = y, 300, 200


def main():
    root = tk.Tk()
    root.withdraw()
    infos = []
    RD.messagebox.showinfo = lambda title, msg, **k: infos.append(title)
    RD.messagebox.askyesno = lambda *a, **k: True
    app = FakeApp(root)

    # ── eavesdropper view ─────────────────────────────────────────────
    added, cleaned = [], []
    evs = [
        Eavesdropper("p/near", "N", "近衛", 2.0, "祿肯 (`main_hero`): 你好啊。", "u1"),
        Eavesdropper("p/far", "F", "遠客", 8.0, "祿肯 (`main_hero`): 你.啊。", "u1"),
    ]
    di = make(app, RD.open_eavesdropper_dialog,
              line_no=7, line_text="祿肯 (`main_hero`): 你好啊。", eavesdroppers=evs,
              on_add=lambda keys: (added.append(list(keys)), len(keys))[1],
              on_clean=lambda k, t: (cleaned.append((k, t)),
                                     {"observations": 1, "history": 0})[1],
              display_for=lambda k: {"p/near": "近衛(顯示)"}.get(k))
    r = di._tree.get_children()
    check("eaves: one row per eavesdropper", len(r) == 2)
    check("eaves: columns name/dist/heard, display_for wins",
          di._tree.set(r[0], "name") == "近衛(顯示)"
          and di._tree.set(r[0], "dist") == "2.0m"
          and "你好啊" in di._tree.set(r[0], "heard"))
    check("eaves: multi-select enabled", str(di._tree.cget("selectmode")) == "extended")
    di._tree.selection_set([r[0]]); di._tree.focus(r[0])
    di._render_preview()
    check("eaves: preview shows the focused row's full heard line",
          "你好啊。" in di._preview.get("1.0", "end"))
    di._on_double()
    check("eaves: double-click adds the focused key", added == [["p/near"]])
    di._tree.selection_set(list(r))
    di._clean_selected()
    check("eaves: delete cleans each row with the utterance token",
          sorted(cleaned) == [("p/far", "u1"), ("p/near", "u1")])
    check("eaves: window closed after clearing", not di.win.winfo_exists())

    # ── sharer view ───────────────────────────────────────────────────
    added.clear(); cleaned.clear()
    shs = [
        Sharer("p/a", "A", "甲", "(劇情描述)", "(劇情描述): 大家好。", "大家好。"),
        Sharer("p/b", "B", "乙", "乙 (`B`)", "乙 (`B`): 大家好。", "大家好。"),
    ]
    di = make(app, RD.open_sharer_dialog,
              line_no=3, line_text="(劇情描述): 大家好。", sharers=shs,
              on_add=lambda keys: (added.append(list(keys)), len(keys))[1],
              on_clean=lambda k, t: (cleaned.append((k, t)), {"history": 1})[1])
    r = di._tree.get_children()
    check("share: one row per sharer", len(r) == 2)
    check("share: columns name/speaker/line",
          di._tree.set(r[0], "speaker") == "(劇情描述)"
          and "大家好" in di._tree.set(r[0], "line"))
    di._tree.selection_set([r[0]]); di._tree.focus(r[0])
    di._add_selected()
    check("share: add passes the key", added == [["p/a"]])
    di._tree.selection_set(list(r))
    di._clean_selected()
    check("share: delete cleans with the CONTENT token",
          sorted(cleaned) == [("p/a", "大家好。"), ("p/b", "大家好。")])
    check("share: window closed after clearing", not di.win.winfo_exists())

    # right-click labels differ by count and view
    di = make(app, RD.open_sharer_dialog, line_no=3, line_text="x", sharers=shs,
              on_add=lambda k: len(k), on_clean=lambda k, t: {"history": 1})
    r = di._tree.get_children()
    di._tree.selection_set([r[0]]); di._tree.identify_row = lambda _y: r[0]
    di._on_right_click(_Ev(10))
    labels = [i[0] for i in di._ctx.items if i]
    check("share single-row menu: add / clean sharer",
          "將共用者加入" in labels[0] and "刪除共用者" in labels[1])
    di._ctx.hide()
    di._tree.selection_set(list(r)); di._tree.identify_row = lambda _y: r[0]
    di._on_right_click(_Ev(10))
    labels = [i[0] for i in di._ctx.items if i]
    check("share multi-row menu counts", "將 2 個共用者加入" in labels[0])
    di._ctx.hide()
    di.win.destroy()

    # empty lists open nothing
    infos.clear()
    before = len(root.winfo_children())
    RD.open_eavesdropper_dialog(app, line_no=1, line_text="x", eavesdroppers=[],
                                on_add=lambda k: 0, on_clean=lambda k, t: {})
    RD.open_sharer_dialog(app, line_no=1, line_text="x", sharers=[],
                          on_add=lambda k: 0, on_clean=lambda k, t: {})
    check("empty lists show info, open no window",
          len(infos) == 2 and len(root.winfo_children()) == before)

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] relations dialog smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] relations dialog smoke passed")


if __name__ == "__main__":
    main()
