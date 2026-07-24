"""Regression: persona export/import round-trip + import parsing edge cases.

Run: python scripts/persona_transfer_check.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import persona_transfer as P  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    data = {
        "Name": "埃爾加", "StringId": "bloodraven_elga",
        "CharacterDescription": "描述", "AIGeneratedPersonality": "性格",
        "AIGeneratedBackstory": "背景", "AIGeneratedSpeechQuirks": "說話",
        "AIGeneratedCognitiveStyle": "認知", "ConversationHistory": ["x"],
    }

    # export all
    js = P.build_export_json(data, list(P.PERSONA_FIELDS))
    obj = json.loads(js)
    check("export has _meta name/id", obj["_meta"]["Name"] == "埃爾加"
          and obj["_meta"]["StringId"] == "bloodraven_elga")
    check("export has exported_at with offset",
          "T" in obj["_meta"]["exported_at"])
    check("export contains all 5 fields", all(f in obj for f in P.PERSONA_FIELDS))
    check("export omits non-persona keys", "ConversationHistory" not in obj)

    # export subset keeps canonical order & only chosen
    js2 = P.build_export_json(data, ["AIGeneratedPersonality", "CharacterDescription"])
    obj2 = json.loads(js2)
    keys = [k for k in obj2 if k != "_meta"]
    check("subset export only chosen fields",
          set(keys) == {"CharacterDescription", "AIGeneratedPersonality"})
    check("subset export canonical order",
          keys == ["CharacterDescription", "AIGeneratedPersonality"])

    # import persona export (round-trip, _meta ignored)
    fields, kind = P.parse_import_json(js)
    check("import persona kind", kind == "persona")
    check("import round-trips values", fields["CharacterDescription"] == "描述"
          and fields["AIGeneratedCognitiveStyle"] == "認知")
    check("import drops _meta", "_meta" not in fields)

    # import full character JSON → extract 5 fields, kind=character
    fields2, kind2 = P.parse_import_json(json.dumps(data, ensure_ascii=False))
    check("import full-char kind", kind2 == "character")
    check("import full-char extracts persona", len(fields2) == 5)

    # partial persona (only 2 fields)
    partial = json.dumps({"CharacterDescription": "只有描述"}, ensure_ascii=False)
    f3, k3 = P.parse_import_json(partial)
    check("import partial keeps present only", f3 == {"CharacterDescription": "只有描述"})

    # invalid inputs
    for bad in ["not json", "[]", "{}", '{"Foo": 1}']:
        try:
            P.parse_import_json(bad)
            check(f"reject invalid: {bad[:12]}", False)
        except ValueError:
            check(f"reject invalid: {bad[:12]}", True)

    print()
    if FAILS:
        print(f"[FAIL] persona_transfer check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] persona_transfer check passed")


if __name__ == "__main__":
    main()
