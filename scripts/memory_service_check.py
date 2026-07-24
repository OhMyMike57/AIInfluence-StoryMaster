"""Regression: memory_service parsing/formatting against a real 5.0.7 save.

Locks the dual-track helpers: MEMORY-line parsing from ConversationHistory,
line formatting round-trip, Memories[] access, image resolution, and orphan
detection (埃爾加's dropped book entry whose image is still on disk).

Run: python scripts/memory_service_check.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import memory_service as M  # noqa: E402
from services import time_format as TF     # noqa: E402

FAILS = []
_SAMPLES = Path(r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research\data_samples")
SAMPLE = _SAMPLES / "AIInfluence 5.0.7" / "save_data" / "oRHQTILfrj64"
SAMPLE_60 = _SAMPLES / "AIInfluence 6.0.2" / "save_data"


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    # ── pure helpers (no sample needed) ──
    check("collapse", M.collapse_single_line("a\n  b \n\nc") == "a b c")
    check("format", M.format_memory_line(91129.6, "hi\nthere") == "MEMORY (day 91130): hi there")
    check("format bad day", M.format_memory_line("x", "t") == "MEMORY (day 0): t")

    ch = [
        "MEMORY (day 91115): 第一段記憶。",
        "埃爾加 (`bloodraven_elga`): 一句對話。",
        "MEMORY (day 91129): 第二段記憶。",
    ]
    lines = M.parse_memory_lines(ch)
    check("parse count", len(lines) == 2)
    check("parse index", [l["index"] for l in lines] == [0, 2])
    check("parse day/text", lines[0]["day"] == 91115 and lines[1]["text"] == "第二段記憶。")

    e = M.new_memory_entry(day=91120, title="T", summary="S")
    check("new entry fields", set(M.MEMORY_ENTRY_FIELDS) <= set(e.keys()))
    # id must match the mod's format: 32 lowercase hex chars, no dashes
    # (e.g. 9e03df970f9142b38668dbbf45b27050) — also the memory_images filename.
    import re as _re
    check("new entry id = 32 lowercase hex (mod format)",
          bool(_re.fullmatch(r"[0-9a-f]{32}", e["id"])))
    check("new entry created_time has offset", "+" in e["created_time"] or e["created_time"].endswith("Z")
          or e["created_time"][-6] in "+-")
    check("new entry day", e["campaign_day"] == 91120.0)
    # v1.1.0: 6.0's Memory Book reads `summary` only and writes memory_text
    # null, so a new entry must NOT mirror the text into the dead field.
    check("new entry leaves memory_text empty", e["memory_text"] == "")
    check("new entry carries scene",
          M.new_memory_entry(day=1, scene="A rainy street")["scene"] == "A rainy street")

    # legacy_memory_text: surface an old save's text only when it says
    # something summary doesn't.
    check("legacy text surfaced when it differs",
          M.legacy_memory_text({"summary": "S", "memory_text": "長文"}) == "長文")
    check("legacy duplicate of summary is hidden",
          M.legacy_memory_text({"summary": "S", "memory_text": " S "}) == "")
    check("6.0 entry (memory_text null) has no legacy text",
          M.legacy_memory_text({"summary": "S", "memory_text": None}) == "")

    e2 = M.update_memory_entry(e, {"title": "T2", "campaign_day": 5})
    check("update keeps id", e2["id"] == e["id"])
    check("update applies", e2["title"] == "T2" and e2["campaign_day"] == 5.0)

    # ── campaign_day scale (6.0 switched to elapsed-since-campaign-start) ──
    START = 91056                    # 1084 × 84 = 1084年春1日
    check("CAMPAIGN_START_DAY is 1084 spring 1", TF.CAMPAIGN_START_DAY == START)
    check("5.0.x absolute day passes through",
          M.entry_day({"campaign_day": 91128.64}) == 91129)
    check("6.0 elapsed day normalised to absolute",
          M.entry_day({"campaign_day": 5.10}) == START + 5)
    check("elapsed day resolves to year 1084, not year 0",
          TF.game_days_to_date(M.entry_day({"campaign_day": 5.10}))[0] == 1084)
    check("scale detection", M.entry_uses_elapsed({"campaign_day": 5.1})
          and not M.entry_uses_elapsed({"campaign_day": 91128.6}))
    check("to_stored_day round-trips both scales",
          M.to_stored_day(START + 5, True) == 5.0
          and M.to_stored_day(START + 5, False) == float(START + 5))
    check("empty book writes 6.0's convention", M.book_uses_elapsed([]) is True)
    check("book follows its newest entry",
          M.book_uses_elapsed([{"campaign_day": 5.1}, {"campaign_day": 91128.6}]) is False
          and M.book_uses_elapsed([{"campaign_day": 91128.6}, {"campaign_day": 5.1}]) is True)

    # ── real sample ──
    if SAMPLE.exists():
        import json
        elga = json.loads((SAMPLE / "埃爾加 (bloodraven_elga).json").read_text(encoding="utf-8-sig"))
        ents = M.memory_entries(elga)
        check("sample elga has 1 book entry", len(ents) == 1)
        check("sample entry day", M.entry_day(ents[0]) == 91129)
        img = M.resolve_memory_image(ents[0], SAMPLE)
        check("sample image resolves to memory_images/<id>.png",
              img is not None and img.name == ents[0]["id"] + ".png")
        mlines = M.parse_memory_lines(elga.get("ConversationHistory"))
        check("sample elga has 2 MEMORY lines", len(mlines) == 2)
        orphans = M.orphan_memory_images(ents, SAMPLE)
        check("sample has 1 orphan image (dropped book entry)",
              any(p.stem == "3b2d1a74b9e44eac93170386712245c9" for p in orphans))
    else:
        print("  ..  (5.0.7 sample not present — pure checks only)")

    # ── 6.0 corpus: the epoch is what makes memories land in the past ──
    # A memory can only be created on or before the day the save was taken, so
    # if CAMPAIGN_START_DAY were wrong the normalised dates would overshoot.
    # This is the evidence the constant rests on — keep it enforced.
    if SAMPLE_60.exists():
        import json
        n = ahead = 0
        for camp in SAMPLE_60.iterdir():
            if not camp.is_dir():
                continue
            for p in camp.glob("*.json"):
                try:
                    d = json.loads(p.read_text(encoding="utf-8-sig"))
                except Exception:
                    continue
                if not isinstance(d, dict):
                    continue
                last = d.get("LastInteractionTimeDays")
                try:
                    last = float(last)
                except (TypeError, ValueError):
                    continue
                for e in M.memory_entries(d):
                    n += 1
                    if M.entry_day(e) > last + 1:
                        ahead += 1
        check(f"6.0 corpus: all {n} memories land on/before their save's last "
              f"interaction", n > 0 and ahead == 0)
    else:
        print("  ..  (6.0.2 sample not present — epoch corpus check skipped)")

    print()
    if FAILS:
        print(f"[FAIL] memory_service check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] memory_service check passed")


if __name__ == "__main__":
    main()
