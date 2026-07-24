"""Smoke: MemoryPage constructs, loads a real 5.0.7 character, and gates edits.

Verifies the widget renders both tracks (AI memory lines + Memories[] book),
resolves the memory image, and that toolbar buttons are disabled until edit
mode + a selection.  Uses callbacks that record calls (no disk writes).

Run: python scripts/memory_page_smoke.py
"""
import os
import sys
import json
import tkinter as tk
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widgets.memory_page import MemoryPage  # noqa: E402
from services import memory_service as M     # noqa: E402

FAILS = []
SAMPLE = Path(r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research"
              r"\data_samples\AIInfluence 5.0.7\save_data\oRHQTILfrj64")


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    root = tk.Tk()
    root.withdraw()
    calls = []
    ev = tk.BooleanVar(value=False)
    mp = MemoryPage(
        root,
        on_entry_save=lambda i, f: calls.append(("entry_save", i, f)),
        on_entry_delete=lambda i: calls.append(("entry_delete", i)),
        edit_variable=ev,
        resolve_name=lambda sid: {"bloodraven_elga": "埃爾加"}.get(sid),
    )
    mp.pack()

    # synthetic data first (no sample dependency)
    data = {
        "ConversationHistory": [
            "MEMORY (day 100): 一段記憶。",
            "某人 (`x`): 對話。",
            "MEMORY (day 120): 另一段。",
        ],
        "Memories": [
            # 5.0.x-shaped: memory_text carries text summary doesn't
            {"id": "abc", "campaign_day": 120.0, "title": "標題A", "summary": "概要A",
             "memory_text": "完整A", "image_path": "",
             "involved_hero_ids": ["bloodraven_elga", "unknown_id"]},
            # 6.0-shaped: elapsed-since-start day, scene set, memory_text null
            {"id": "def", "campaign_day": 56.25, "title": "標題B", "summary": "概要B",
             "scene": "A dim tavern", "memory_text": None, "image_path": ""},
        ],
    }
    mp.load(data, campaign_dir=None, npc_name="測試")
    check("book has 2 entries (two-row list = 4 rows)",
          len(mp._entries) == 2 and mp._entry_lb.size() == 4)
    # v1.1.0: the AI-memory track is gone — MEMORY lines are plain history now.
    check("no AI-memory list attribute", not hasattr(mp, "_line_lb"))

    # edit-mode gating: buttons disabled when not editing
    check("add disabled (read-only)", str(mp._entry_add["state"]) == "disabled")
    ev.set(True)
    check("add enabled (edit mode)", str(mp._entry_add["state"]) == "normal")

    # two-row book selection maps both rows to the entry
    mp._select_book_entry(0)
    check("book select maps to entry 0", mp._book_selected_index() == 0)
    check("book entry edit enabled", str(mp._entry_edit["state"]) == "normal")

    # adding an entry produces an entry_save(None, ...) when saved
    mp._on_entry_save(None, {"campaign_day": 100, "title": "", "summary": "一段記憶。",
                             "scene": ""})
    check("entry_save add recorded",
          any(c[0] == "entry_save" and c[1] is None for c in calls))

    # ── S6: preview reflects the 6.0 reality ──────────────────────────
    def preview():
        return mp._entry_detail.get("1.0", "end")

    mp._select_book_entry(0)   # 5.0.x-shaped entry
    p = preview()
    check("summary shown as 記憶內容, not 概要",
          "記憶內容" in p and "概要\n" not in p and "概要A" in p)
    check("memory_text is no longer a plain 完整記憶 section", "▋ 完整記憶" not in p)
    check("differing memory_text kept as read-only legacy block",
          "舊版完整記憶" in p and "完整A" in p)
    check("involved hero resolved to a name", "埃爾加 (`bloodraven_elga`)" in p)
    check("unresolvable hero id still listed", "`unknown_id`" in p)

    mp._select_book_entry(1)   # 6.0-shaped entry
    p = preview()
    check("scene section always present", "場景描述" in p and "A dim tavern" in p)
    check("scene without image explains it can be generated later",
          "補生成" in p)
    check("6.0 entry shows no legacy block", "舊版完整記憶" not in p)

    # ── campaign_day scale: 6.0 stores elapsed-since-start ────────────
    # The list's date row used to read 「0年春6日」 for every 6.0 memory.
    dates = [mp._entry_lb.get(mp._book_first_pos[i]) for i in range(len(mp._entries))]
    check("no entry renders as year 0", not any(d.startswith("0") for d in dates))
    check("elapsed day 56.25 lands in 1084",
          M.entry_day(mp._entries[1]) == 91056 + 56)

    # Re-saving without touching the date must not shift it by 91056 days:
    # the dialog reads absolute (entry_day) and writes back through
    # to_stored_day with the entry's own convention.
    for e in mp._entries:
        rt = M.to_stored_day(M.entry_day(e), M.entry_uses_elapsed(e))
        check(f"date round-trips for entry {e['id']}", abs(rt - round(float(e['campaign_day']))) < 1.0)
    check("a new entry follows the book's convention",
          M.book_uses_elapsed(mp._entries) is True)

    # the editor no longer offers memory_text, and omitting it preserves the old value
    entry = {"id": "abc", "summary": "S", "memory_text": "舊文"}
    check("update without memory_text preserves it",
          M.update_memory_entry(entry, {"summary": "S2", "scene": "x"})["memory_text"] == "舊文")

    # ── real sample: image resolves ──
    if SAMPLE.exists():
        elga = json.loads((SAMPLE / "埃爾加 (bloodraven_elga).json").read_text(encoding="utf-8-sig"))
        mp.load(elga, campaign_dir=SAMPLE, npc_name="埃爾加")
        check("sample: 1 book entry (2 rows)",
              len(mp._entries) == 1 and mp._entry_lb.size() == 2)
        mp._select_book_entry(0)
        img = M.resolve_memory_image(mp._entries[0], SAMPLE)
        check("sample: image path resolves", img is not None and img.exists())
    else:
        print("  ..  (5.0.7 sample not present — synthetic checks only)")

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] memory_page smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] memory_page smoke passed")


if __name__ == "__main__":
    main()
