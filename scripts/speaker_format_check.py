"""Regression: speaker-prefix grammar (services.speaker_format).

The mod reads these prefixes back, so a prefix the tool rewrites must come out
byte-for-byte identical unless the user deliberately changed something.  The
grammar was reverse-engineered from save data (the format strings are encrypted
in the obfuscated DLL), so the only honest proof is:

    for every speaker prefix in every sample campaign:  build(parse(x)) == x

That corpus sweep is check 3 below and covers 4.1.0 / 5.0.2 / 5.0.7 / 6.0.2.
Checks 1–2 pin the individual constructs, check 4 the per-target rewriting that
makes one 寫入劇情 produce the right shape in each character file.

Run: python scripts/speaker_format_check.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import speaker_format as SF  # noqa: E402
from services.json_utils import split_line_prefix  # noqa: E402
from services.world_service import data_samples_base  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main() -> int:
    # ── 1. each construct parses into the right fields ───────────────────
    print("constructs:")
    sp = SF.parse("埃爾加 (`bloodraven_elga`)")
    check("plain named", sp.identity == "埃爾加" and sp.hero_id == "bloodraven_elga"
          and sp.relation == SF.RELATION_NONE and sp.wrapper is None)

    sp = SF.parse("I (「釤刀」蘇雷納, `CharacterObject_2783`)")
    check("self-line keeps the real name separately",
          sp.is_self and sp.self_name == "「釤刀」蘇雷納"
          and sp.hero_id == "CharacterObject_2783")

    sp = SF.parse("Stranger (as introduced, `main_hero`)")
    check("as-introduced + still anonymous",
          sp.identity == SF.IDENTITY_STRANGER and sp.is_player
          and sp.relation == SF.RELATION_INTRODUCED and sp.is_anonymous)

    sp = SF.parse("祿肯·赫芬斯汀 (as introduced, `main_hero`)")
    check("as-introduced with a claimed name",
          sp.identity == "祿肯·赫芬斯汀" and sp.is_player and not sp.is_anonymous)

    sp = SF.parse("Unidentified person (`main_hero`)")
    check("unidentified player", sp.is_anonymous and sp.is_player)

    sp = SF.parse("[Overheard nearby, day 91114, approx. 2.7m, dialog/player] "
                  "Unidentified person (`main_hero`)")
    check("overheard wrapper parsed",
          isinstance(sp.wrapper, SF.Overheard) and sp.wrapper.day == 91114.0
          and sp.wrapper.distance == 2.7 and sp.wrapper.channel == "dialog/player"
          and sp.is_anonymous)

    # Three engagement shapes seen in real captures: kingdom vs party,
    # clan vs a bare enemy label, kingdom vs party.  All opaque strings.
    for engagement, speaker in (
            ("巴坦尼亞 vs 執政官·阿匹斯's party", "執政官·阿匹斯"),
            ("弗蘭迪亞 vs 維達爾's party", "巴索洛恩"),
            ("赫芬斯汀 vs 劫掠者", "馬洛溫")):
        line = f"[BATTLE_ORDER][{engagement}] {speaker}"
        sp = SF.parse(line)
        check(f"battle engagement kept opaque: {engagement}",
              isinstance(sp.wrapper, SF.Battle)
              and sp.wrapper.engagement == engagement
              and sp.identity == speaker and sp.hero_id == ""
              and SF.build(sp) == line)

    check("story tag is raw, not speech", SF.parse("[劇情記憶]").kind == "raw")
    check("parenthesised 6.0 tag is raw too", SF.parse("(劇情描述)").kind == "raw")
    check("MEMORY is raw", SF.parse("MEMORY (day 91115)").kind == "raw")
    check("legacy Player parses without crashing", SF.parse("Player").kind == "raw")
    check("empty prefix is raw", SF.parse("").kind == "raw")

    # ── 2. editing one facet leaves the rest alone ───────────────────────
    print("\nedits:")
    base = SF.parse("Unidentified person (`main_hero`)")
    check("identity swap keeps the id",
          SF.build(SF.with_identity(base, "祿肯")) == "祿肯 (`main_hero`)")
    check("relation swap adds as-introduced",
          SF.build(SF.with_relation(SF.with_identity(base, "祿肯"),
                                    SF.RELATION_INTRODUCED))
          == "祿肯 (as introduced, `main_hero`)")
    wrapped = SF.with_wrapper(base, SF.Overheard(day=12, distance=3.5,
                                                 channel="ambient-npc"))
    check("wrapper can be added to a plain speaker",
          SF.build(wrapped)
          == "[Overheard nearby, day 12, approx. 3.5m, ambient-npc] "
             "Unidentified person (`main_hero`)")
    check("wrapper can be removed",
          SF.build(SF.with_wrapper(wrapped, None)) == "Unidentified person (`main_hero`)")
    check("raw prefixes ignore edits",
          SF.build(SF.with_identity(SF.parse("[劇情記憶]"), "X")) == "[劇情記憶]")

    # ── 3. corpus sweep: every real prefix round-trips exactly ───────────
    print("\ncorpus round-trip:")
    base_dir = data_samples_base(ROOT)
    prefixes, files = set(), 0
    if base_dir and Path(base_dir).is_dir():
        for dirpath, _dirs, names in os.walk(base_dir):
            for name in names:
                if not name.endswith(".json"):
                    continue
                try:
                    data = json.loads(Path(dirpath, name).read_text(encoding="utf-8"))
                except Exception:
                    continue
                ch = data.get("ConversationHistory") if isinstance(data, dict) else None
                if not isinstance(ch, list):
                    continue
                files += 1
                for entry in ch:
                    pre, _text = split_line_prefix(entry)
                    if pre:
                        prefixes.add(pre)

    if not prefixes:
        print("  (no sample campaigns found — corpus sweep skipped)")
    else:
        bad = [p for p in prefixes if SF.build(SF.parse(p)) != p]
        speech = [p for p in prefixes if SF.parse(p).kind == "speech"]
        print(f"  scanned {files} character files, {len(prefixes)} distinct prefixes "
              f"({len(speech)} parsed as speech)")
        check(f"every prefix round-trips ({len(bad)} broken)", not bad)
        for p in bad[:5]:
            print(f"        {p!r} -> {SF.build(SF.parse(p))!r}")
        # The corpus must actually exercise the interesting constructs, or a
        # green sweep would prove nothing.
        kinds = [SF.parse(p) for p in prefixes]
        check("corpus contains self-lines", any(k.is_self for k in kinds))
        check("corpus contains as-introduced",
              any(k.relation == SF.RELATION_INTRODUCED for k in kinds))
        check("corpus contains anonymous speakers", any(k.is_anonymous for k in kinds))
        check("corpus contains overheard wrappers",
              any(isinstance(k.wrapper, SF.Overheard) for k in kinds))
        check("corpus contains battle wrappers",
              any(isinstance(k.wrapper, SF.Battle) for k in kinds))

    # ── 4. per-target rewriting (batch 寫入劇情) ──────────────────────────
    print("\nper-target rewriting:")
    spoken = SF.make_named("蘇雷納", "CharacterObject_2783")
    same = SF.resolve_for_target(spoken, "CharacterObject_2783", "「釤刀」蘇雷納")
    check("into the speaker's own file → self-line",
          SF.build(same) == "I (「釤刀」蘇雷納, `CharacterObject_2783`)")
    other = SF.resolve_for_target(spoken, "bloodraven_elga", "埃爾加")
    check("into anybody else's file → third person",
          SF.build(other) == "蘇雷納 (`CharacterObject_2783`)")
    back = SF.resolve_for_target(same, "bloodraven_elga", "埃爾加")
    check("a self-line copied elsewhere becomes third person",
          SF.build(back) == "「釤刀」蘇雷納 (`CharacterObject_2783`)")
    check("wrapper survives per-target rewriting",
          isinstance(SF.resolve_for_target(
              SF.with_wrapper(spoken, SF.Battle("A vs B")),
              "CharacterObject_2783", "蘇雷納").wrapper, SF.Battle))
    check("raw prefixes are never rewritten",
          SF.resolve_for_target(SF.parse("[劇情記憶]"), "x", "y").kind == "raw")

    print()
    if FAILS:
        print(f"[FAIL] speaker format check: {len(FAILS)} failing")
        return 1
    print("[PASS] speaker format check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
