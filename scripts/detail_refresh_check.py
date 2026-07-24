"""Regression: the open detail panel refreshes after any immediate write.

寫入劇情 (and the other immediate-write tools: 重置, 批量清空, 修剪, 載入群聊…)
wrote straight to disk and left the 對話歷史 / 對話觀察 / 摘要 tabs showing
pre-write data — the user had to click away and back to see their own edit.

The fix hangs off ``safe_write_json_with_backup``, the single write choke point,
so every current *and future* write path is covered.  This locks that in:

  1. Writing the character the panel is showing schedules a reload.
  2. Writing a different character does not.
  3. A batch write coalesces into ONE reload (debounced), not one per file.
  4. A failed write does not schedule a reload.

Run: python scripts/detail_refresh_check.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import StoryMaster as SM  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class _App(SM.AIInfluenceStoryToolsApp):
    """The real class, without building the whole UI."""
    def __init__(self):  # noqa: D107
        pass


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    tmp = Path(tempfile.mkdtemp())
    try:
        camp = tmp / "campaign"
        camp.mkdir()
        shown = camp / "顯示中 (sid_shown).json"
        other = camp / "其他人 (sid_other).json"

        # A failed write pops an error dialog; a regression must never be able
        # to open a modal, so record instead of showing.
        errors = []
        SM.messagebox.showerror = lambda *a, **k: errors.append(a)

        reloads = []
        app = _App()
        app.root = root
        app.settings = {"snapshot_policy": "none"}
        app.log = lambda *a, **k: None
        app._load_character_detail = lambda d: reloads.append(d)
        app.plain_to_path = {"顯示中": shown, "其他人": other}
        app._detail_display = "顯示中"

        def settle():
            root.update()
            root.after(120, root.quit)
            root.mainloop()

        # 1 + 3. batch write to the displayed character → exactly one reload
        for i in range(5):
            app.safe_write_json_with_backup(
                shown, {"StringId": "sid_shown", "ConversationHistory": [f"line {i}"]})
        settle()
        check("write to the open character refreshes it", reloads == ["顯示中"])
        check("a batch of 5 writes reloads once (debounced)", len(reloads) == 1)

        # 2. writing somebody else leaves the panel alone
        reloads.clear()
        app.safe_write_json_with_backup(
            other, {"StringId": "sid_other", "ConversationHistory": ["z"]})
        settle()
        check("write to another character does not refresh", reloads == [])

        # 4. a failed write schedules nothing
        reloads.clear()
        errors.clear()
        blocked = camp / "nope" / "x (sid_shown).json"   # parent doesn't exist
        app.plain_to_path["顯示中"] = blocked
        app._detail_display = "顯示中"
        try:
            ok = app.safe_write_json_with_backup(blocked, {"StringId": "sid_shown"})
        except Exception:
            ok = False
        settle()
        check("a failed write does not refresh", reloads == [] and not ok)
        check("…and the user was told", len(errors) == 1)

        # no character shown → nothing to refresh, and no crash
        reloads.clear()
        app._detail_display = None
        app.plain_to_path["顯示中"] = shown
        app.safe_write_json_with_backup(
            shown, {"StringId": "sid_shown", "ConversationHistory": ["q"]})
        settle()
        check("no open character → no reload, no error", reloads == [])
    finally:
        root.destroy()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILS:
        print(f"[FAIL] detail refresh check: {len(FAILS)} failing")
        return 1
    print("[PASS] detail refresh check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
