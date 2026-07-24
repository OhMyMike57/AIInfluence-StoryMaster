"""Smoke: WorldItemSummary renders info / secret items (v0.26.0).

The 訊息與秘密 page swapped raw-JSON previews for a summary card; this verifies
the widget renders both schemas (info: usageChance/category; secret:
knowledgeChance/accessLevel/tags) plus the placeholder / empty paths.

Run: python scripts/world_item_summary_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widgets.world_item_summary import WorldItemSummary  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    root = tk.Tk()
    root.withdraw()
    w = WorldItemSummary(root)

    # info item
    w.load({"id": "info1", "usageChance": 8, "category": "world",
            "applicableNPCs": ["lords", "companions"], "description": "公開內文"})
    txt = w._text.get("1.0", "end")
    check("info: id shown", "info1" in txt)
    check("info: body shown", "公開內文" in txt)
    check("info: category shown", "world" in txt)
    check("info: npc label mapped", "貴族" in txt)  # lords → 貴族

    # secret item
    w.load({"id": "sec1", "knowledgeChance": 65, "accessLevel": "high",
            "applicableNPCs": ["lords"], "tags": ["t1", "t2"],
            "description": "秘密內文"})
    txt = w._text.get("1.0", "end")
    check("secret: body shown", "秘密內文" in txt)
    check("secret: accessLevel as category", "high" in txt)
    check("secret: tags shown", "t1" in txt and "t2" in txt)

    # placeholder / empty / clear must not raise
    w.load_text("請選擇條目")
    check("placeholder shown", "請選擇條目" in w._text.get("1.0", "end"))
    w.load(None)
    w.clear()

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] world_item_summary smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] world_item_summary smoke passed")


if __name__ == "__main__":
    main()
