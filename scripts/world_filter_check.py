"""Regression for services.world_filter (訊息與秘密 編輯器篩選邏輯).

Run: python scripts/world_filter_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import world_filter as wf  # noqa: E402

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} - {label}")
    if not ok:
        print(f"        got : {got}\n        want: {want}")
        FAILS.append(label)


# ── Fixture ───────────────────────────────────────────────────────────────────
META = {
    "A": {"HasAttrs": True,  "Kingdom": "k1", "Clan": "c1"},
    "B": {"HasAttrs": True,  "Kingdom": "k1", "Clan": "c2"},
    "C": {"HasAttrs": True,  "Kingdom": "k2", "Clan": "c3"},
    "D": {"HasAttrs": True,  "Kingdom": "",   "Clan": "c4"},   # minor faction
    "E": {"HasAttrs": True,  "Kingdom": "",   "Clan": ""},     # clanless → 無陣營
    "F": {"HasAttrs": False},                                   # no companion data
}
KNAMES = {"k1": "王國一", "k2": "王國二"}
CNAMES = {"c1": "氏族A", "c2": "氏族B", "c3": "氏族C", "c4": "氏族D"}
ALL = set(META)

PRESETS = {"g1": ["A", "C", "X"]}        # X not in roster
INFO = {"i1": ["B", "D"]}
SECRET = {"s1": ["E"]}

# ── faction_rows ─────────────────────────────────────────────────────────────
rows = wf.faction_rows(META, KNAMES)
check("faction_rows keys+minor",
      [(k, key) for k, key, _d in rows],
      [("kingdom", "k1"), ("kingdom", "k2"), ("kingdom", wf.MINOR_KEY)])
check("faction_rows minor display", rows[-1][2], "無陣營")

# ── clan_rows ────────────────────────────────────────────────────────────────
check("clan_rows scoped to k1",
      wf.clan_rows(META, CNAMES, ["k1"]), [("c1", "氏族A"), ("c2", "氏族B")])
check("clan_rows minor bucket",
      wf.clan_rows(META, CNAMES, [wf.MINOR_KEY]), [("c4", "氏族D")])
check("clan_rows all when no kingdom selected",
      [cid for cid, _ in wf.clan_rows(META, CNAMES, [])], ["c1", "c2", "c3", "c4"])

# ── faction_candidates ───────────────────────────────────────────────────────
check("faction k1", wf.faction_candidates(ALL, META, ["k1"], []), {"A", "B"})
check("faction k1+k2", wf.faction_candidates(ALL, META, ["k1", "k2"], []), {"A", "B", "C"})
check("faction minor", wf.faction_candidates(ALL, META, [wf.MINOR_KEY], []), {"D", "E"})
check("faction clan-only c1", wf.faction_candidates(ALL, META, [], ["c1"]), {"A"})
check("faction k1+clan c2", wf.faction_candidates(ALL, META, ["k1"], ["c2"]), {"B"})
check("faction empty → all", wf.faction_candidates(ALL, META, [], []), ALL)
check("faction excludes no-attrs",
      "F" not in wf.faction_candidates(ALL, META, ["k1", "k2", wf.MINOR_KEY], []), True)

# ── ref_candidates ───────────────────────────────────────────────────────────
check("ref group g1 (X dropped)",
      wf.ref_candidates([("group", "g1")], PRESETS, INFO, SECRET, ALL), {"A", "C"})
check("ref info i1", wf.ref_candidates([("info", "i1")], PRESETS, INFO, SECRET, ALL), {"B", "D"})
check("ref union group+info",
      wf.ref_candidates([("group", "g1"), ("info", "i1")], PRESETS, INFO, SECRET, ALL),
      {"A", "C", "B", "D"})
check("ref empty → all", wf.ref_candidates([], PRESETS, INFO, SECRET, ALL), ALL)

print()
if FAILS:
    print(f"[FAIL] world_filter check: {len(FAILS)} failing")
    sys.exit(1)
print("[PASS] world_filter check passed")
