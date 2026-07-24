"""Regression: 對話歷史 export / import round-trips (v1.1.0 R4-S4).

The formats only earn their keep if what comes back is what went out, so the
core assertion is byte-equality after a full round trip — including the line
shapes that broke the old exporter: eavesdropped lines (brackets, commas,
backticks), battle shouts (quotes), multi-line entries, markdown metacharacters
(``*坐起身*``), JSON metacharacters (braces, ``"``), and the ``I (名字, `id`)``
self form.

Then the same round trip is run over **every sample campaign on disk**, so a
format change that trips on real data fails here rather than in front of a user.

Run: python scripts/conversation_transfer_check.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import conversation_transfer as T  # noqa: E402

FAILS = []
SAMPLES = Path(r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research\data_samples")


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


# Every awkward shape in one list.
ENTRIES = [
    "Unidentified person (`main_hero`): 你認得這本書？",
    "I (「學者」阿馬托爾, `CharacterObject_4449`): 「你認得這本書？」",
    "祿肯·赫芬斯汀 (as introduced, `main_hero`): 我叫祿肯。",
    "埃爾加 (`bloodraven_elga`): *坐起身*",                       # md italics
    "[劇情記憶]: 手動插入的劇情。",
    "[Overheard nearby, day 91114, approx. 2.7m, dialog/player] "
    "Unidentified person (`main_hero`): 親愛的",
    '[BATTLE_ORDER][巴坦尼亞 vs X\'s party] 阿匹斯: "架起盾牆！"',   # quotes
    "MEMORY (day 91115): 洛迪爾在旅店與埃爾加會合。",
    "Your last conversation was 3 days ago.",
    "沒有說話者的純提示詞。",
    "多行\n第二行\n\n第四行（含空行）",                             # newlines
    '含 JSON 符號 { "a": [1,2] } 與 ~ 波浪號',                      # json + tilde
    "# 井號開頭  ## [99] 假標題",                                   # md heading bait
]


def main():
    # ── Markdown ──────────────────────────────────────────────────────
    md = T.build_markdown("測試角色", ENTRIES,
                          row_label=lambda i, t: f"💬 類型 · 說話者{i}")
    back = T.parse_markdown(md)
    check("MD round-trips every entry byte-for-byte", back == ENTRIES)
    check("MD numbers headings from 1", "## [1]" in md and f"## [{len(ENTRIES)}]" in md)
    check("MD keeps the readable label", "說話者0" in md)

    # a body that itself contains a '## [n]' line must not split the entry
    check("heading-shaped text inside a fence stays one entry",
          back[-1] == ENTRIES[-1] and len(back) == len(ENTRIES))

    # deleting a whole block deletes that line — no manual renumbering needed
    blocks = md.split("\n## [")
    fewer = T.parse_markdown("\n## [".join(blocks[:2] + blocks[3:]))
    check("removing a block drops exactly that entry",
          fewer == ENTRIES[:1] + ENTRIES[2:])

    # empty / malformed input is refused, not silently accepted
    for bad, why in ((" ", "empty"), ("just prose", "no headings"),
                     ("## [1]\n\n~~~\nunclosed", "unclosed fence"),
                     ("## [1]\n\nno fence here", "missing fence")):
        try:
            T.parse_markdown(bad)
            check(f"MD rejects {why}", False)
        except T.TransferError:
            check(f"MD rejects {why}", True)

    # ── clipboard: all ────────────────────────────────────────────────
    clip = T.build_clipboard_all(ENTRIES)
    check("clipboard-all is the JSON fragment",
          clip.startswith('"ConversationHistory": ['))
    res = T.parse_clipboard(clip, len(ENTRIES))
    check("fragment re-imports as a full replace",
          res.kind == "replace" and res.entries == ENTRIES)
    check("fragment survives a trailing comma",
          T.parse_clipboard(clip + ",", len(ENTRIES)).entries == ENTRIES)

    # a whole character JSON
    whole = json.dumps({"StringId": "x", "ConversationHistory": ENTRIES},
                       ensure_ascii=False)
    res = T.parse_clipboard(whole, len(ENTRIES))
    check("whole character JSON imports", res.kind == "replace" and res.entries == ENTRIES)

    # a bare array
    res = T.parse_clipboard(json.dumps(ENTRIES, ensure_ascii=False), len(ENTRIES))
    check("bare JSON array imports", res.kind == "replace" and res.entries == ENTRIES)

    # an object with no ConversationHistory is an error, not an empty history
    try:
        T.parse_clipboard('{"StringId": "x"}', len(ENTRIES))
        check("JSON without the key is refused", False)
    except T.TransferError:
        check("JSON without the key is refused", True)

    # ── clipboard: selected → patch ───────────────────────────────────
    sel = T.build_clipboard_selected(ENTRIES, [3, 10, 6])
    check("selected export is line-ordered and numbered",
          sel.startswith("[#4] ") and "[#7] " in sel and "[#11] " in sel)
    res = T.parse_clipboard(sel, len(ENTRIES))
    check("selected export re-imports as a patch", res.kind == "patch")
    check("patch maps back to the right indices",
          sorted(res.updates) == [3, 6, 10])
    check("patch round-trips multi-line entries",
          res.updates[10] == ENTRIES[10])
    patched = T.apply_patch(ENTRIES, res.updates)
    check("applying an unchanged patch changes nothing", patched == ENTRIES)

    edited = T.parse_clipboard("[#4] 埃爾加 (`bloodraven_elga`): *站起身*\n"
                               "[#1] 改寫的第一行", len(ENTRIES))
    out = T.apply_patch(ENTRIES, edited.updates)
    check("patch edits only the numbered lines",
          out[3].endswith("*站起身*") and out[0] == "改寫的第一行"
          and out[1:3] == ENTRIES[1:3] and out[4:] == ENTRIES[4:])

    # out-of-range numbers abort instead of silently dropping
    try:
        T.parse_clipboard("[#99] 不存在的行", len(ENTRIES))
        check("out-of-range line number aborts", False)
    except T.TransferError as exc:
        check("out-of-range line number aborts", "99" in str(exc))

    try:
        T.parse_clipboard("這只是一段沒有格式的文字", len(ENTRIES))
        check("unrecognised paste is refused", False)
    except T.TransferError:
        check("unrecognised paste is refused", True)

    # ── every sample campaign on disk ─────────────────────────────────
    if SAMPLES.exists():
        files = n_lines = 0
        md_bad = clip_bad = sel_bad = 0
        for p in SAMPLES.rglob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            ch = d.get("ConversationHistory")
            if not isinstance(ch, list) or not ch:
                continue
            want = [e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)
                    for e in ch]
            files += 1
            n_lines += len(want)
            if T.parse_markdown(T.build_markdown("x", ch)) != want:
                md_bad += 1
            if T.parse_clipboard(T.build_clipboard_all(ch), len(ch)).entries != want:
                clip_bad += 1
            idx = list(range(0, len(ch), 7))
            got = T.parse_clipboard(T.build_clipboard_selected(ch, idx), len(ch))
            if T.apply_patch(ch, got.updates) != want:
                sel_bad += 1
        print(f"  ..  corpus: {files} files / {n_lines} lines")
        check("corpus: MD round-trips every real line", files > 0 and md_bad == 0)
        check("corpus: clipboard-all round-trips", clip_bad == 0)
        check("corpus: [#n] patch round-trips", sel_bad == 0)
    else:
        print("  ..  (samples not present — synthetic checks only)")

    print()
    if FAILS:
        print(f"[FAIL] conversation transfer check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] conversation transfer check passed")


if __name__ == "__main__":
    main()
