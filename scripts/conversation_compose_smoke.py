"""Smoke: 編寫 N 個對話行 window (v1.1.0 R4-S5, simplified).

The algorithm is covered by ``compose_plan_check``; this covers the wiring
between the (now much smaller) widget set and that algorithm:

  1. Rows build for a sparse selection with the real line numbers next to them,
     each holding the WHOLE line verbatim (no speaker split, no special-casing).
  2. ✗ deletes/restores a loaded row and drops an inserted row; 在末尾新增一行
     appends after the last loaded line.
  3. Committing sends the merged history with everything unloaded untouched.
  4. Committing an unchanged window writes nothing; a blanked row is dropped.
  5. The autosize is the cheap estimator, not the 60 ms displaylines call.

Run: python scripts/conversation_compose_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dialogs import conversation_compose_dialog as CD  # noqa: E402
from dialogs.conversation_compose_dialog import _ComposeEditor, _fast_line_count  # noqa: E402
from services import compose_plan as CP  # noqa: E402

FAILS = []

ENTRIES = [
    "Unidentified person (`main_hero`): 你認得這本書？",                       # 1
    "I (「學者」阿馬托爾, `CharacterObject_4449`): 「認得。」",                  # 2
    "埃爾加 (`bloodraven_elga`): *坐起身*",                                     # 3
    "[劇情記憶]: 手動插入的劇情。",                                             # 4
    "[Overheard nearby, day 91114, approx. 2.7m, dialog/player] "
    "Unidentified person (`main_hero`): 親愛的",                                # 5
    '[BATTLE_ORDER][巴坦尼亞 vs X\'s party] 阿匹斯: "架起盾牆！"',              # 6
    "MEMORY (day 91115): 洛迪爾在旅店與埃爾加會合。",                           # 7
    "沒有說話者的純提示詞。",                                                   # 8
]


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class FakeApp:
    def __init__(self, root):
        self.root = root


def settle(root, ed, limit=200):
    for _ in range(limit):
        root.update()
        if not ed._rendering:
            return
    raise AssertionError("renderer never finished")


def main():
    root = tk.Tk()
    root.withdraw()
    answers = {"yes": True}
    CD.messagebox.askyesno = lambda *a, **k: answers["yes"]
    infos = []
    CD.messagebox.showinfo = lambda title, msg, **k: infos.append(title)
    CD.messagebox.showwarning = lambda title, msg, **k: infos.append(title)

    app = FakeApp(root)
    commits = []

    def open_ed(indices):
        ed = _ComposeEditor(app, ENTRIES, npc_name="「學者」阿馬托爾",
                            npc_id="CharacterObject_4449", indices=indices,
                            on_commit=lambda e, s: commits.append((e, s)))
        settle(root, ed)
        return ed

    # ── cheap autosize, not the 60 ms displaylines call ────────────────
    check("fast line count: short line = 1", _fast_line_count("hi") == 1)
    check("fast line count: newlines counted", _fast_line_count("a\nb\nc") == 3)
    check("fast line count: long CJK line wraps",
          _fast_line_count("字" * 60) >= 2)

    # ── sparse selection loads whole lines ─────────────────────────────
    ed = open_ed([1, 5, 7])
    check("only the selected rows load", len(ed._rows) == 3)
    check("rows show their real line numbers",
          [w.num.cget("text") for w in ed._uis] == ["2", "6", "8"])
    check("each row holds the WHOLE line verbatim",
          [w.text.get("1.0", "end-1c") for w in ed._uis]
          == [ENTRIES[1], ENTRIES[5], ENTRIES[7]])
    check("no per-row speaker widget", not hasattr(ed._uis[0], "speaker"))

    # committing unchanged writes nothing
    infos.clear()
    ed._confirm()
    check("no changes → nothing committed", not commits and len(infos) == 1)

    # edit the battle line (whole line, including its prefix)
    ed._uis[1].text.delete("1.0", "end")
    ed._uis[1].text.insert("1.0", '[BATTLE_ORDER][巴坦尼亞 vs X\'s party] 阿匹斯: "撤！"')
    ed._confirm()
    check("edit commits the merged history", len(commits) == 1)
    merged = commits[0][0]
    check("edited whole line written verbatim", merged[5].endswith('"撤！"'))
    check("everything else untouched",
          merged[:5] == ENTRIES[:5] and merged[6:] == ENTRIES[6:])

    # ── append at end + delete ─────────────────────────────────────────
    commits.clear()
    ed = open_ed([1, 5, 7])
    ed._append_row()
    settle(root, ed)
    ed._uis[3].text.insert("1.0", "新的一行")
    check("appended row lands after the last loaded line (after line 8)",
          ed._uis[3].num.cget("text") == "9")
    ed._toggle_delete(1)          # delete original line 6 (the battle line)
    check("deleted row shows no number", ed._uis[1].num.cget("text") == "—")
    ed._confirm()
    merged = commits[0][0]
    check("append after last loaded + delete, rest intact",
          merged == ENTRIES[:5] + ENTRIES[6:8] + ["新的一行"] + ENTRIES[8:])

    # ── ✗ on an inserted row removes it; blank row dropped ─────────────
    commits.clear()
    ed = open_ed([0])
    ed._append_row()
    settle(root, ed)
    check("an inserted row appears", len(ed._rows) == 2)
    ed._toggle_delete(1)
    check("✗ on an inserted row removes it outright", len(ed._rows) == 1)
    # a blank appended row is dropped at commit, not written as an empty line
    ed._append_row()
    settle(root, ed)
    infos.clear()
    ed._confirm()
    check("a blank appended row is not written", not commits and len(infos) == 1)

    # ── delete/restore round-trips ─────────────────────────────────────
    ed = open_ed([0, 1])
    ed._toggle_delete(1)
    check("delete disables the box", str(ed._uis[1].text.cget("state")) == "disabled")
    ed._toggle_delete(1)
    check("restore re-enables it and renumbers",
          str(ed._uis[1].text.cget("state")) == "normal"
          and ed._uis[1].num.cget("text") == "2")

    # ── the >50 warning gate (raised from 5 after the perf rewrite) ────
    check("warn threshold is 50", CD._WARN_ROWS == 50)
    warned = {"n": 0}
    CD.messagebox.askyesno = lambda *a, **k: (warned.__setitem__("n", warned["n"] + 1), False)[1]
    CD.open_compose_dialog(app, ENTRIES, npc_name="x", npc_id="x",
                           indices=list(range(6)), on_commit=lambda e, s: None)
    check("selecting 6 lines no longer warns", warned["n"] == 0)
    big = ENTRIES * 8            # 64 entries
    CD.open_compose_dialog(app, big, npc_name="x", npc_id="x",
                           indices=list(range(len(big))), on_commit=lambda e, s: None)
    check("selecting >50 lines warns and can be cancelled", warned["n"] == 1)

    infos.clear()
    CD.open_compose_dialog(app, ENTRIES, npc_name="x", npc_id="x",
                           indices=[], on_commit=lambda e, s: None)
    check("no selection warns and does not open", len(infos) == 1)

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] conversation compose smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] conversation compose smoke passed")


if __name__ == "__main__":
    main()
