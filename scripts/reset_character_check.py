"""Regression: 重置角色 template stays schema-compatible with AI Influence 6.0.

The reset dialog now tells the user the output is "相容 AI效應 6.0".  That claim
only holds while the template's key set matches what 6.0 actually writes, so
this pins it to the real 6.0.2 corpus:

  * every key the template produces exists in real 6.0 character files, and
  * 6.0 introduces no character-file key the template is missing —

either failing means the reset would emit or drop a field 6.0 cares about, and
the "相容 6.0" wording (and this test) must be revisited.

Also locks the field-carry contract that the dialog depends on.

Run: python scripts/reset_character_check.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.character_service import (  # noqa: E402
    RESET_ALWAYS_KEEP, RESET_PRESERVABLE_FIELDS,
    pristine_character_template, reset_character_json,
)

FAILS = []
SAMPLE_60 = Path(r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research"
                 r"\data_samples\AIInfluence 6.0.2\save_data")


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def _is_character(d):
    return isinstance(d, dict) and "StringId" in d and "ConversationHistory" in d


def main():
    tmpl = set(pristine_character_template({}).keys())

    # ── carry contract (no sample needed) ─────────────────────────────
    src = {
        "Name": "測試", "StringId": "sid_x", "Gender": "female",
        "InformationAccessLevel": "high", "player_bind_string_id": "main_hero",
        "CharacterDescription": "描述", "ConversationHistory": ["a", "b", "c"],
        "PlayerRelation": {"Value": 40, "Description": "friendly"},
        "LegacyOnlyField": 123, "LastMemoryProcessedIndex": 2,
    }
    out = reset_character_json(src, {"CharacterDescription", "ConversationHistory"})
    check("identity always carried", out["Name"] == "測試" and out["Gender"] == "female"
          and out["StringId"] == "sid_x")
    check("preserved fields carried", out["CharacterDescription"] == "描述"
          and out["ConversationHistory"] == ["a", "b", "c"])
    check("unpicked field reset to default", out["PlayerRelation"] == {"Value": 0, "Description": "neutral"})
    check("legacy-only field dropped", "LegacyOnlyField" not in out)
    check("kept history keeps its memory pointer", out["LastMemoryProcessedIndex"] == 2)

    out2 = reset_character_json(src, set())          # 全部清除（僅留身分）
    check("clearing history zeroes the memory pointer", out2["LastMemoryProcessedIndex"] == 0
          and out2["ConversationHistory"] == [])
    check("always-keep list is all carried",
          all(k in out2 for k in RESET_ALWAYS_KEEP))

    # every checkbox key is a real template key (else preserving it is a no-op)
    tmpl_keys = tmpl | set(RESET_ALWAYS_KEEP)
    unknown = [row[0] for row in RESET_PRESERVABLE_FIELDS if row[0] not in tmpl_keys]
    check("every preservable field exists in the template", not unknown)

    # ── the 6.0 compatibility claim ───────────────────────────────────
    if SAMPLE_60.exists():
        real = {}
        nfiles = 0
        for camp in SAMPLE_60.iterdir():
            if not camp.is_dir():
                continue
            for p in camp.glob("*.json"):
                try:
                    d = json.loads(p.read_text(encoding="utf-8-sig"))
                except Exception:
                    continue
                if not _is_character(d):
                    continue
                nfiles += 1
                real.update(dict.fromkeys(d.keys()))
        real_keys = set(real)
        missing_from_tmpl = sorted(real_keys - tmpl)
        extra_in_tmpl = sorted(tmpl - real_keys)
        check(f"6.0 corpus scanned ({nfiles} character files)", nfiles > 0)
        check("template covers every key 6.0 writes "
              f"(missing: {missing_from_tmpl})", not missing_from_tmpl)
        check("template writes no key absent from every 6.0 save "
              f"(extra: {extra_in_tmpl})", not extra_in_tmpl)
    else:
        print("  ..  (6.0.2 sample not present — compatibility check skipped)")

    print()
    if FAILS:
        print(f"[FAIL] reset character check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] reset character check passed")


if __name__ == "__main__":
    main()
