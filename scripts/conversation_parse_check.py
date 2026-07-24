"""Regression: 5.0.x ConversationHistory line parsing + perspective conversion.

Locks the parser (services.json_utils.parse_conversation_line) and the
sync/back-fill helper (convert_line_perspective) against the real line formats
confirmed from a 5.0.7 save (2026-07-04): self ``I (名字, `id`): …``,
third-person ``名字 (`id`): …``, overheard, gap notices, MEMORY lines, plus
legacy ``[tag]: …`` and old ``名字: …`` rows.

Run: python scripts/conversation_parse_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.json_utils import (  # noqa: E402
    LINE_CATEGORIES,
    parse_conversation_line as P,
    convert_line_perspective as C,
    line_category as LC,
    speaker_display as SD,
    split_line_prefix as SP,
    entry_speaker,
)

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    mem = "MEMORY (day 91115): 洛迪爾在旅店與埃爾加會合。"
    oh = ("[Overheard nearby, day 91115, approx. 3.0m, ambient-npc] "
          "Unidentified person (`CharacterObject_6605`): 「血鴉之子」嗎？")
    me = "I (哈夫爾, `bloodraven_halvor`): *低沉笑聲* 老大。"
    other = "埃爾加 (`bloodraven_elga`): *坐起身* 既然大家都聽見了。"
    player = "洛迪爾 (`main_hero`): 聽見了?娜迪雅"
    gap = "Your last conversation was 1 day ago."
    tag = "[劇情記憶]: 手動插入的劇情。"
    legacy = "貓人道伊德: 舊格式沒有 ID 的行。"

    # ── kind detection ──
    check("memory kind+day", P(mem)["kind"] == "memory" and P(mem)["day"] == 91115.0)
    po = P(oh)
    check("overheard fields",
          po["kind"] == "overheard" and po["speaker_id"] == "CharacterObject_6605"
          and po["day"] == 91115.0 and po["distance"] == 3.0)
    pm = P(me)
    check("self fields",
          pm["kind"] == "self" and pm["speaker"] == "哈夫爾"
          and pm["speaker_id"] == "bloodraven_halvor" and pm["is_self"])
    pd = P(other)
    check("dialogue fields",
          pd["kind"] == "dialogue" and pd["speaker"] == "埃爾加"
          and pd["speaker_id"] == "bloodraven_elga" and not pd["is_self"])
    check("player is dialogue w/ main_hero",
          P(player)["kind"] == "dialogue" and P(player)["speaker_id"] == "main_hero")
    check("gap kind", P(gap)["kind"] == "gap")
    check("tag kind", P(tag)["kind"] == "tag" and P(tag)["speaker"] == "[劇情記憶]")
    check("legacy plain kind", P(legacy)["kind"] == "plain" and P(legacy)["speaker"] == "貓人道伊德")

    # ── content is preserved verbatim (no truncation) ──
    check("self text intact", P(me)["text"] == "*低沉笑聲* 老大。")
    check("dialogue text intact", P(other)["text"] == "*坐起身* 既然大家都聽見了。")

    # ── entry_speaker back-compat ──
    check("entry_speaker dialogue", entry_speaker(other) == "埃爾加")
    check("entry_speaker self", entry_speaker(me) == "哈夫爾")
    check("entry_speaker gap None", entry_speaker(gap) is None)

    # ── perspective conversion (sync / back-fill) ──
    elga_self = "I (埃爾加, `bloodraven_elga`): *坐起身*"
    elga_third = "埃爾加 (`bloodraven_elga`): *坐起身*"
    check("self→third for other target",
          C(elga_self, "bloodraven_solvor") == elga_third)
    check("self stays for own target",
          C(elga_self, "bloodraven_elga") == elga_self)
    check("third→self for own target",
          C(elga_third, "bloodraven_elga") == elga_self)
    check("third stays for other target",
          C(elga_third, "bloodraven_solvor") == elga_third)
    check("memory never converted", C(mem, "bloodraven_elga") == mem)
    check("overheard never converted", C(oh, "bloodraven_halvor") == oh)
    check("no-target passthrough", C(elga_self, None) == elga_self)
    check("round-trip stable",
          C(C(elga_self, "bloodraven_solvor"), "bloodraven_elga") == elga_self)

    # ── 6.0 formats (R4-S3) ───────────────────────────────────────────────
    intro = "祿肯·赫芬斯汀 (as introduced, `main_hero`): 你好,阿馬托爾."
    unident = "Unidentified person (`main_hero`): [劇情描述:在旅店裡…] 當然!"
    battle = ('[BATTLE_ORDER][巴坦尼亞 vs 執政官·阿匹斯\'s party] '
              '執政官·阿匹斯: "帝國的戰士們，不要被森林遮蔽了雙眼！"')
    plain_npc = "「學者」阿馬托爾: *我走到祿肯身邊* 領主大人。"
    note = "這是一段沒有說話者的純提示詞。"

    pi = P(intro)
    check("as-introduced is dialogue, not plain", pi["kind"] == "dialogue")
    check("as-introduced keeps the name", pi["speaker"] == "祿肯·赫芬斯汀")
    check("as-introduced resolves main_hero", pi["speaker_id"] == "main_hero")
    check("as-introduced flagged", pi["introduced"] is True)
    check("as-introduced text intact", pi["text"] == "你好,阿馬托爾.")

    pb = P(battle)
    check("battle kind", pb["kind"] == "battle")
    check("battle speaker", pb["speaker"] == "執政官·阿匹斯")
    check("battle context", pb["context"] == "巴坦尼亞 vs 執政官·阿匹斯's party")
    check("battle text intact", pb["text"].startswith('"帝國的戰士們'))

    # ── category mapping (what the viewer colours by) ─────────────────────
    npc, npc_id = "「學者」阿馬托爾", "CharacterObject_4449"
    cat = lambda s: LC(P(s), npc, npc_id)  # noqa: E731
    check("player before introducing", cat(unident) == "player")
    check("player after introducing", cat(intro) == "player")
    check("player by explicit id", cat(player) == "player")
    check("self line", cat("I (「學者」阿馬托爾, `CharacterObject_4449`): 嗯。") == "self")
    check("plain line matching the npc counts as self", cat(plain_npc) == "self")
    check("other named character", cat(other) == "other")
    check("story tag", cat(tag) == "tag")
    # 6.0 also writes parenthesised narration tags — "(劇情描述): …" (20 in the
    # 2026-07-21 capture).  Without the paren form these looked like an ordinary
    # un-linked speaker instead of narration.
    paren_tag = "(劇情描述): 赫芬斯汀家族在俄爾泰西亞團聚後，正式組成傭兵戰團。"
    check("parenthesised tag is a tag", cat(paren_tag) == "tag")
    check("parenthesised tag keeps its label",
          P(paren_tag)["speaker"] == "(劇情描述)")
    check("parenthesised tag round-trips",
          "{}: {}".format(*SP(paren_tag)) == paren_tag)
    check("overheard", cat(oh) == "overheard")
    check("battle", cat(battle) == "battle")
    check("legacy memory", cat(mem) == "memory")
    check("gap notice", cat(gap) == "gap")
    check("no-speaker plain text is a note", cat(note) == "note")
    check("every category is declared",
          all(c in LINE_CATEGORIES
              for c in (cat(unident), cat(intro), cat(other), cat(tag),
                        cat(oh), cat(battle), cat(mem), cat(gap), cat(note))))

    # ── split_line_prefix: exact round-trip for every line shape ──────────
    for label, line in (("self", me), ("dialogue", other), ("player", player),
                        ("introduced", intro), ("tag", tag), ("plain", legacy),
                        ("overheard", oh), ("battle", battle), ("memory", mem)):
        pre, body = SP(line)
        check(f"split keeps a prefix for {label}", bool(pre))
        check(f"rejoin restores {label} byte-for-byte", f"{pre}: {body}" == line)
    pre, body = SP(gap)
    check("gap notice has no prefix", pre == "" and body == gap)
    pre, body = SP(note)
    check("un-prefixed text has no prefix", pre == "" and body == note)
    check("overheard prefix carries the whole bracket blob",
          SP(oh)[0].startswith("[Overheard nearby") and SP(oh)[0].endswith("`)"))
    check("non-string entry is handled", SP({"a": 1}) == ("", ""))

    # ── speaker_display returns a key, never translated text (tr(var) trap) ──
    check("unidentified → key", SD(P(unident)) == ("", "unidentified"))
    check("introduced → name + key", SD(P(intro)) == ("祿肯·赫芬斯汀", "introduced"))
    check("ordinary speaker → no key", SD(P(other)) == ("埃爾加", ""))

    print()
    if FAILS:
        print(f"[FAIL] conversation parse check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] conversation parse check passed")


if __name__ == "__main__":
    main()
