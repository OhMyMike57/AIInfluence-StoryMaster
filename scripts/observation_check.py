"""Regression for 對話觀察 (P1.5-2): observation_service + ObservationsPage.

Covers the pure helpers, the delete semantics (hash set must stay untouched)
and headless construction/loading of the page, including the real 6.0.2 sample
where a genuine distorted overheard line exists.

Run: python scripts/observation_check.py
"""
import json
import os
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import observation_service as O  # noqa: E402

SAMPLE = Path(
    r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research\data_samples"
    r"\AIInfluence 6.0.2\save_data\aYqt3pB1kbNn"
)
SAMPLE_CHAR = SAMPLE / "蘇雷納 (CharacterObject_2783).json"

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} - {label}")
    if not ok:
        print(f"        got : {got}\n        want: {want}")
        FAILS.append(label)


# ── Pure helpers ─────────────────────────────────────────────────────────────
print("helpers:")
direct = {"hearing_role": "direct", "speaker_name": "A", "speaker_hero_id": "sid_a",
          "canonical_line": "hello there", "heard_line": "A (`sid_a`): hello there",
          "distance": None, "campaign_days": 91099.5,
          "scene_id": "sc1", "utterance_id": "sc1:u1"}
over = {"hearing_role": "overheard", "speaker_name": "A", "speaker_hero_id": "sid_a",
        "canonical_line": "hello there", "heard_line": "A (`sid_a`): he..o th.re",
        "distance": 7.15, "campaign_days": 91099.5,
        "scene_id": "sc1", "utterance_id": "sc1:u1"}

check("observations of non-dict", O.observations("nope"), [])
check("observations filters junk", O.observations({"DialogueObservations": [direct, 5, None]}), [direct])
check("is_overheard direct", O.is_overheard(direct), False)
check("is_overheard overheard", O.is_overheard(over), True)
check("direct line not distorted", O.is_distorted(direct), False)
check("overheard line distorted", O.is_distorted(over), True)
check("distance parsed", O.distance_of(over), 7.15)
check("distance None for direct", O.distance_of(direct), None)
check("campaign day parsed", O.campaign_day_of(over), 91099.5)
check("speaker falls back to name", O.speaker_label(direct), "A")
check("speaker uses resolver", O.speaker_label(direct, lambda sid: "蘇雷納"), "蘇雷納")
check("speaker ignores empty resolver", O.speaker_label(direct, lambda sid: ""), "A")
check("scene key", O.scene_key(over), "sc1")
check("utterance key", O.utterance_key(over), "sc1:u1")
check("summarize", O.summarize({"DialogueObservations": [direct, over]}),
      {"total": 2, "direct": 1, "overheard": 1, "scenes": 1})

# ── Delete semantics ─────────────────────────────────────────────────────────
print("\ndelete keeps the hash set intact:")
data = {"DialogueObservations": [direct, over],
        "ProcessedDialogueObservationHashes": ["hashA", "hashB"]}
check("delete returns True", O.delete_observation(data, 1), True)
check("observation removed", data["DialogueObservations"], [direct])
check("hashes untouched", data["ProcessedDialogueObservationHashes"], ["hashA", "hashB"])
check("out-of-range is a no-op", O.delete_observation(data, 9), False)
check("negative index is a no-op", O.delete_observation(data, -1), False)
check("non-dict is a no-op", O.delete_observation("x", 0), False)
check("missing key is a no-op", O.delete_observation({}, 0), False)

# ── Page (headless) ──────────────────────────────────────────────────────────
print("\nObservationsPage headless:")
from widgets.observations_page import ObservationsPage  # noqa: E402

root = tk.Tk()
root.withdraw()
deleted = []
ev = tk.BooleanVar(value=False)
page = ObservationsPage(root, on_delete=lambda i: deleted.append(i), edit_variable=ev)
page.pack()
page.load({"DialogueObservations": [direct, over]})
check("both rows listed", len(page._tree.get_children()), 2)
check("delete disabled without selection", str(page._del_btn["state"]), "disabled")

page._tree.selection_set("obs::1")
page._on_select()
check("delete still disabled when not editing", str(page._del_btn["state"]), "disabled")
ev.set(True)
page._refresh_edit_state()
check("delete enabled in edit mode with selection", str(page._del_btn["state"]), "normal")
check("selected index maps to the observation", page._selected_index(), 1)

page._filter_var.set("旁聽")
page._refresh_list()
check("overheard filter keeps 1 row", len(page._tree.get_children()), 1)
page._filter_var.set("直接聽到")
page._refresh_list()
check("direct filter keeps 1 row", len(page._tree.get_children()), 1)
page._filter_var.set("全部")
page._search_var.set("nothing-matches")
page._refresh_list()
check("search with no hits empties the list", len(page._tree.get_children()), 0)
page._search_var.set("")
page._refresh_list()
check("clearing search restores rows", len(page._tree.get_children()), 2)

page.clear()
check("clear empties the tree", len(page._tree.get_children()), 0)

# ── Real 6.0.2 sample ────────────────────────────────────────────────────────
print("\nreal 6.0.2 sample:")
if not SAMPLE_CHAR.is_file():
    print("  skip - sample not available")
else:
    d = json.loads(SAMPLE_CHAR.read_text(encoding="utf-8-sig"))
    obs = O.observations(d)
    s = O.summarize(d)
    check("sample observation count", s["total"], 67)
    check("sample has overheard entries", s["overheard"], 6)
    check("sample scene count", s["scenes"], 5)
    overheard = [o for o in obs if O.is_overheard(o)]
    check("real overheard line is distorted", O.is_distorted(overheard[0]), True)
    check("real overheard has a distance", O.distance_of(overheard[0]) is not None, True)
    page.load(d)
    check("page lists every sample observation", len(page._tree.get_children()), 67)
    # Deleting must not disturb the (equally sized) hash list.
    before = len(d.get("ProcessedDialogueObservationHashes") or [])
    O.delete_observation(d, 0)
    check("sample delete drops one observation", len(O.observations(d)), 66)
    check("sample hash list unchanged",
          len(d.get("ProcessedDialogueObservationHashes") or []), before)

root.destroy()
print()
if FAILS:
    print(f"[FAIL] observation check: {len(FAILS)} failing")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("[PASS] observation check passed")
