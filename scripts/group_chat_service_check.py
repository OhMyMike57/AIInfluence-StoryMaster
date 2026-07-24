"""Regression: group-chat detection (player anchor) + repair against a real save.

The 5.0.7 sample oRHQTILfrj64 has a 4-person group chat (blood-raven companions).
Two members (哈夫爾/娜迪雅) retained the player's opening line; two (埃爾加/索爾沃)
had it consolidated into a MEMORY summary — so the anchor heuristic detects the
two that retained it (documenting the known false-negative the curation popup
compensates for).  Repair math is verified on synthetic data.

Run: python scripts/group_chat_service_check.py
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import group_chat_service as G  # noqa: E402

FAILS = []
SAMPLE = Path(r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research"
              r"\data_samples\AIInfluence 5.0.7\save_data\oRHQTILfrj64")


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    # ── detection (synthetic) ──
    opening = "洛迪爾 (`main_hero`): 大家聽我說"
    reply = "某人 (`x`): 好"
    data = {
        "A": {"ConversationHistory": [opening, "A (`a`): 我在", reply]},
        "B": {"ConversationHistory": ["B (`b`): 嗨", opening]},
        "C": {"ConversationHistory": ["洛迪爾 (`main_hero`): 只跟你說的悄悄話", "C (`c`): 嗯"]},  # 1-on-1
        "D": {"ConversationHistory": []},
    }
    res = G.detect_group(data)
    check("detects the shared-opening group (A,B)", res["participants"] == ["A", "B"])
    check("excludes the 1-on-1 partner (C)", "C" not in res["participants"])
    check("anchor is the shared player line text", res["anchor"] == "大家聽我說")

    empty = G.detect_group({"X": {"ConversationHistory": ["洛迪爾 (`main_hero`): 只有一人"]}})
    check("no group when no shared player line", empty["participants"] == [])

    # ── repair (synthetic) ──
    npc = {"LastInteractionTimeDays": -1.0,
           "CounterpartySocial": {"main_hero": {"interaction_count": 3, "trust_level": 5}}}
    r = G.apply_repair(npc, 91130.5, fix_last_interaction=True, fix_interaction_count=True)
    check("repair sets LastInteractionTimeDays", r["LastInteractionTimeDays"] == 91130.5)
    check("repair +1 interaction_count", r["CounterpartySocial"]["main_hero"]["interaction_count"] == 4)
    check("repair keeps other social fields", r["CounterpartySocial"]["main_hero"]["trust_level"] == 5)
    check("repair does not mutate input", npc["LastInteractionTimeDays"] == -1.0)

    r2 = G.apply_repair({}, 100.0, fix_last_interaction=False, fix_interaction_count=True)
    check("repair creates 5.0.x count location when absent",
          r2["CounterpartySocial"]["main_hero"]["interaction_count"] == 1)

    day = G.group_day({"A": {"LastInteractionTimeDays": -1.0},
                       "B": {"LastInteractionTimeDays": 91130.5}}, ["A", "B"])
    check("group_day = max LastInteractionTimeDays", day == 91130.5)

    # ── real sample ──
    if SAMPLE.exists():
        char_data = {}
        for f in SAMPLE.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if isinstance(d, dict) and "ConversationHistory" in d:
                char_data[f.stem] = d
        res = G.detect_group(char_data)
        parts = set(res["participants"])
        check("sample: detects halvor+nadia (retained opening)",
              {"哈夫爾 (bloodraven_halvor)", "娜迪雅 (bloodraven_nadia)"} <= parts)
        check("sample: does not misfire huge group", len(parts) <= 4)
    else:
        print("  ..  (5.0.7 sample not present — synthetic checks only)")

    print()
    if FAILS:
        print(f"[FAIL] group_chat_service check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] group_chat_service check passed")


if __name__ == "__main__":
    main()
