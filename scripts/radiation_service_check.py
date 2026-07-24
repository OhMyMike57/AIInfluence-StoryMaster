"""Regression: dialogue-radiation helpers (v1.2.0 Phase 3a).

Locks the two things the eavesdropper feature relies on, both against real 6.0
save data:

  1. line → utterance → eavesdropper resolution finds the same cross-character
     listeners the raw data has;
  2. cleaning a listener is *exact* — it removes the utterance's observation and
     the matching CH overheard line (when present), and touches nothing else.

Run: python scripts/radiation_service_check.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import radiation_service as R  # noqa: E402

FAILS = []
SAMPLE_60 = Path(r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research"
                 r"\data_samples\AIInfluence 6.0.2\save_data")


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def _obs(utt, role, heard, canon="", dist=None):
    return {"utterance_id": utt, "hearing_role": role, "heard_line": heard,
            "canonical_line": canon, "distance": dist}


def synthetic():
    # A said line u1 (speaker), B and C overheard it; A also overheard u2.
    speaker = {
        "StringId": "A", "Name": "阿甲",
        "ConversationHistory": [
            "阿甲 (`A`): [劇情描述:在酒館] 你好啊。",                       # u1, spoken
            "[Overheard nearby, day 5, approx. 3.0m, dialog/npc] "
            "丙丙 (`C`): [劇情.:別處] 噓。",                                # u2, overheard by A
        ],
        "DialogueObservations": [
            _obs("u1", "direct", "阿甲 (`A`): [劇情描述:在酒館] 你好啊。",
                 canon="[劇情描述:在酒館] 你好啊。"),
            _obs("u2", "overheard", "丙丙 (`C`): [劇情.:別處] 噓。",
                 canon="[劇情描述:別處] 噓。", dist=3.0),
        ],
    }
    b = {
        "StringId": "B", "Name": "乙乙",
        "ConversationHistory": [
            "[Overheard nearby, day 5, approx. 2.0m, dialog/npc] "
            "阿甲 (`A`): [劇情描述:在酒館] 你好啊。",                       # the CH copy
        ],
        "DialogueObservations": [
            _obs("u1", "overheard", "阿甲 (`A`): [劇情描述:在酒館] 你好啊。",
                 canon="[劇情描述:在酒館] 你好啊。", dist=2.0),
        ],
    }
    c = {  # overheard u1 too, but the CH line already expired
        "StringId": "C", "Name": "丙丙",
        "ConversationHistory": [],
        "DialogueObservations": [
            _obs("u1", "overheard", "阿甲 (`A`): [劇.描述:在.館] 你.啊。",
                 canon="[劇情描述:在酒館] 你好啊。", dist=8.0),
        ],
    }
    return speaker, b, c


def main():
    A, B, C = synthetic()
    idx = R.build_index([("A", A), ("B", B), ("C", C)])

    # ── line → utterance ──────────────────────────────────────────────
    check("spoken line maps via canonical",
          R.line_to_utterance(A["ConversationHistory"][0], A) == "u1")
    check("overheard line maps via heard_line tail",
          R.line_to_utterance(A["ConversationHistory"][1], A) == "u2")
    check("a non-dialogue line maps to nothing",
          R.line_to_utterance("MEMORY (day 5): x", A) is None)

    # ── eavesdroppers ─────────────────────────────────────────────────
    ev = R.eavesdroppers_for_line(A["ConversationHistory"][0], A, idx)
    check("u1 has two eavesdroppers (B and C)", len(ev) == 2)
    check("eavesdroppers sorted nearest-first",
          [e.listener_id for e in ev] == ["B", "C"])
    check("eavesdropper carries distance + distorted text",
          ev[0].distance == 2.0 and ev[0].listener_name == "乙乙"
          and "你好啊" in ev[0].heard_line)
    check("distant listener's text is more distorted",
          "." in ev[1].heard_line)

    # counts aligned to CH; the viewer is excluded from their own overheard line
    counts = R.line_eaves_counts(A["ConversationHistory"], A, idx, viewer_key="A")
    check("per-line counts: spoken line has 2, overheard line has 0",
          counts == [2, 0])

    # ── cleaning is exact ─────────────────────────────────────────────
    # B still has the CH copy → both observation and CH line go.
    import copy
    b2 = copy.deepcopy(B)
    res = R.clean_eavesdropper(b2, "u1")
    check("clean B: 1 observation + 1 CH line removed",
          res == {"observations": 1, "history": 1})
    check("clean B: observation gone", b2["DialogueObservations"] == [])
    check("clean B: CH overheard line gone", b2["ConversationHistory"] == [])

    # C's CH copy already expired → only the observation goes, no crash.
    c2 = copy.deepcopy(C)
    res = R.clean_eavesdropper(c2, "u1")
    check("clean C: only the observation removed (CH copy already expired)",
          res == {"observations": 1, "history": 0} and c2["DialogueObservations"] == [])

    # cleaning an unrelated utterance changes nothing
    b3 = copy.deepcopy(B)
    res = R.clean_eavesdropper(b3, "does-not-exist")
    check("clean with a wrong utterance is a no-op",
          res == {"observations": 0, "history": 0} and b3 == B)

    # after cleaning B, the index rebuilt from the new data drops B
    idx2 = R.build_index([("A", A), ("B", b2), ("C", c2)])
    check("rebuilt index reflects the cleanup",
          not idx2.get("u1"))

    # ── sharing (identical content across characters) ─────────────────
    # A group line: G1 spoke it (I-form), G2 and G3 hold the same content with
    # a third-person prefix; G3 also has a distinct line.
    content = "[劇情描述:在旅店裡] 大家好，今天天氣不錯。"
    g1 = {"StringId": "G1", "Name": "甲", "ConversationHistory": [
        f"I (甲, `G1`): {content}"],
        "DialogueObservations": [_obs("g", "direct",
            f"甲 (`G1`): {content}", canon=content)]}
    g2 = {"StringId": "G2", "Name": "乙", "ConversationHistory": [
        f"甲 (`G1`): {content}"]}
    g3 = {"StringId": "G3", "Name": "丙", "ConversationHistory": [
        f"甲 (`G1`): {content}", "丙 (`G3`): 只有我有的一句。"]}
    lone = {"StringId": "Z", "Name": "丁", "ConversationHistory": [
        "MEMORY (day 5): 記憶不算共用。"]}
    sidx = R.build_share_index([("g1", g1), ("g2", g2), ("g3", g3), ("z", lone)])

    check("share_content strips the speaker prefix (I-form == name-form)",
          R.share_content(g1["ConversationHistory"][0])
          == R.share_content(g2["ConversationHistory"][0]) == content)
    check("gap/memory lines never share",
          R.share_content("MEMORY (day 5): x") == ""
          and R.share_content("Your last conversation was 3 days ago.") == "")

    sh = R.sharers_for_line(g1["ConversationHistory"][0], sidx, exclude_key="g1")
    check("group line shared by the two other participants",
          sorted(s.listener_id for s in sh) == ["G2", "G3"])
    check("sharer keeps how their copy attributes it",
          all(s.speaker == "甲 (`G1`)" for s in sh))
    check("a line only one character has → no sharers",
          R.sharers_for_line(g3["ConversationHistory"][1], sidx, exclude_key="g3") == [])

    counts = R.line_share_counts(g3["ConversationHistory"], sidx, viewer_key="g3")
    check("share counts: shared line 2, lone line 0", counts == [2, 0])

    # cleaning a sharer removes their copy + the matching observation
    g1c = copy.deepcopy(g1)
    res = R.clean_sharer(g1c, content)
    check("clean sharer removes the CH line and the observation",
          res == {"history": 1, "observations": 1}
          and g1c["ConversationHistory"] == [] and g1c["DialogueObservations"] == [])
    g3c = copy.deepcopy(g3)
    res = R.clean_sharer(g3c, content)
    check("clean sharer leaves that character's other lines intact",
          res["history"] == 1 and g3c["ConversationHistory"] == ["丙 (`G3`): 只有我有的一句。"])

    # ── real 6.0 corpus ───────────────────────────────────────────────
    if SAMPLE_60.exists():
        camps = [d for d in SAMPLE_60.iterdir() if d.is_dir()]
        # newest capture with the richest radiation
        best = None
        for camp in camps:
            items = _load_campaign(camp)
            index = R.build_index(items)
            multi = {u: v for u, v in index.items() if len(v) >= 2}
            if best is None or len(multi) > best[1]:
                best = (camp, len(multi), items, index)
        camp, n_multi, items, index = best
        check(f"6.0 corpus: utterances with ≥2 eavesdroppers found ({n_multi})",
              n_multi > 0)

        # every eavesdropper's observation really carries that utterance_id
        data_by_key = dict(items)
        bad = 0
        for utt, evs in index.items():
            for e in evs:
                d = data_by_key[e.listener_key]
                if not any(str(o.get("utterance_id")) == utt
                           and str(o.get("hearing_role")).lower() == "overheard"
                           for o in d.get("DialogueObservations") or []):
                    bad += 1
        check("6.0 corpus: every indexed eavesdropper is backed by a real obs",
              bad == 0)

        # clean one real listener and confirm exactness
        utt = next(u for u, v in index.items() if len(v) >= 1)
        e = index[utt][0]
        import copy as _c
        listener = _c.deepcopy(data_by_key[e.listener_key])
        n_obs_before = len(listener.get("DialogueObservations") or [])
        n_ch_before = len(listener.get("ConversationHistory") or [])
        res = R.clean_eavesdropper(listener, utt)
        check("6.0 corpus: clean removes ≥1 observation",
              res["observations"] >= 1)
        check("6.0 corpus: obs count drops by exactly what was removed",
              len(listener["DialogueObservations"]) == n_obs_before - res["observations"])
        check("6.0 corpus: CH count drops by exactly what was removed",
              len(listener["ConversationHistory"]) == n_ch_before - res["history"])
        # no other utterance's observations were touched
        others_before = [o for o in data_by_key[e.listener_key].get("DialogueObservations") or []
                         if str(o.get("utterance_id")) != utt]
        others_after = [o for o in listener["DialogueObservations"]
                        if str(o.get("utterance_id")) != utt]
        check("6.0 corpus: other utterances untouched",
              others_before == others_after)

        # sharing: real group / broadcast lines are shared across characters
        sindex = R.build_share_index(items)
        multi_share = {c: v for c, v in sindex.items() if len(v) >= 2}
        check(f"6.0 corpus: contents shared by ≥2 characters found ({len(multi_share)})",
              len(multi_share) > 0)
        biggest = max(sindex.values(), key=len)
        check("6.0 corpus: a broadcast/group line is shared by several characters",
              len(biggest) >= 3)
        # every sharer really holds that content
        bad_share = 0
        for content_key, sharers in sindex.items():
            for s in sharers:
                d = data_by_key[s.listener_key]
                if not any(R.share_content(ln) == content_key
                           for ln in d.get("ConversationHistory") or []):
                    bad_share += 1
        check("6.0 corpus: every indexed sharer really holds the content",
              bad_share == 0)
    else:
        print("  ..  (6.0.2 sample not present — synthetic checks only)")

    print()
    if FAILS:
        print(f"[FAIL] radiation service check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] radiation service check passed")


def _load_campaign(camp: Path):
    items = []
    for p in camp.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if isinstance(d, dict) and "StringId" in d and "ConversationHistory" in d:
            items.append((str(p), d))
    return items


if __name__ == "__main__":
    main()
