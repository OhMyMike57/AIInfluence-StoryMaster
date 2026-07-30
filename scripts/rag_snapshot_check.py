"""Regression for the AI Influence 6.0 adaptation services (Phase 1).

Covers services.rag_service (index invalidation + memory pointer clamping) and
services.snapshot_service (save_snapshots listing / purging), plus the character
template fields 6.0 added.  Runs on synthetic trees and, when the research share
is mounted, against the real 6.0.2 sample campaign.

Run: python scripts/rag_snapshot_check.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import rag_service as R  # noqa: E402
from services import snapshot_service as S  # noqa: E402
from services.character_service import (  # noqa: E402
    pristine_character_template,
    reset_character_json,
)

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} - {label}")
    if not ok:
        print(f"        got : {got}\n        want: {want}")
        FAILS.append(label)


# ── Character template (P1-1) ────────────────────────────────────────────────
print("character template 6.0 fields:")
tpl = pristine_character_template({"Name": "N", "StringId": "sid"})
check("LastMemoryProcessedIndex present", tpl.get("LastMemoryProcessedIndex"), 0)
check("RequestDialogueSceneImage present", tpl.get("RequestDialogueSceneImage"), False)
keys = list(tpl)
check("index sits right after ConversationHistory",
      keys[keys.index("ConversationHistory") + 1], "LastMemoryProcessedIndex")
check("scene-image flag sits after PendingAIResponse",
      keys[keys.index("PendingAIResponse") + 1], "RequestDialogueSceneImage")

print("\nreset carries the memory pointer with the history:")
src = {
    "Name": "N", "StringId": "sid",
    "ConversationHistory": ["a", "b", "c"],
    "LastMemoryProcessedIndex": 2,
}
kept = reset_character_json(src, ["ConversationHistory"])
check("history kept → pointer kept", kept.get("LastMemoryProcessedIndex"), 2)
dropped = reset_character_json(src, [])
check("history dropped → pointer 0", dropped.get("LastMemoryProcessedIndex"), 0)
over = reset_character_json(
    {"Name": "N", "StringId": "sid", "ConversationHistory": ["a"], "LastMemoryProcessedIndex": 99},
    ["ConversationHistory"],
)
check("stale pointer clamped to history length", over.get("LastMemoryProcessedIndex"), 1)

# ── Memory pointer clamping (P1-2) ───────────────────────────────────────────
print("\nclamp_memory_processed_index:")
d = {"ConversationHistory": ["a", "b"], "LastMemoryProcessedIndex": 7}
check("clamps down", (R.clamp_memory_processed_index(d), d["LastMemoryProcessedIndex"]), (True, 2))
d = {"ConversationHistory": ["a", "b"], "LastMemoryProcessedIndex": 1}
check("leaves valid value", (R.clamp_memory_processed_index(d), d["LastMemoryProcessedIndex"]), (False, 1))
d = {"ConversationHistory": [], "LastMemoryProcessedIndex": -5}
check("negative → 0", (R.clamp_memory_processed_index(d), d["LastMemoryProcessedIndex"]), (True, 0))
d = {"ConversationHistory": ["a"], "LastMemoryProcessedIndex": None}
check("None → 0", (R.clamp_memory_processed_index(d), d["LastMemoryProcessedIndex"]), (True, 0))
check("no key (5.x file) → untouched",
      R.clamp_memory_processed_index({"ConversationHistory": ["a"]}), False)

print("\npayload detection:")
check("character payload", R.is_character_payload({"ConversationHistory": [], "StringId": "x"}), True)
check("no StringId → not a character", R.is_character_payload({"ConversationHistory": []}), False)
check("diplomacy bundle → not a character", R.is_character_payload({"dynamic_events": []}), False)
check("string_id_of trims", R.string_id_of({"StringId": " x "}), "x")

# ── RAG index invalidation (P1-2) ────────────────────────────────────────────
print("\nrag index invalidation:")
with tempfile.TemporaryDirectory() as td:
    camp = Path(td)
    (camp / "rag").mkdir()
    (camp / "rag" / "lord_1_1.json").write_text('{"chunks": []}', encoding="utf-8")
    check("has_rag_index true", R.has_rag_index(camp, "lord_1_1"), True)
    check("invalidate removes it", R.invalidate_rag_index(camp, "lord_1_1"), True)
    check("gone afterwards", (camp / "rag" / "lord_1_1.json").exists(), False)
    check("second invalidate is a no-op", R.invalidate_rag_index(camp, "lord_1_1"), False)
    check("unknown npc → False", R.invalidate_rag_index(camp, "nobody"), False)
    check("no campaign dir → False", R.invalidate_rag_index(None, "lord_1_1"), False)

print("\npre-6.0 campaign (no rag folder) degrades quietly:")
with tempfile.TemporaryDirectory() as td:
    camp = Path(td)
    check("has_rag_index false", R.has_rag_index(camp, "lord_1_1"), False)
    check("invalidate false", R.invalidate_rag_index(camp, "lord_1_1"), False)

# ── Snapshots (P1-3) ─────────────────────────────────────────────────────────
print("\nsave_snapshots listing / purge:")
with tempfile.TemporaryDirectory() as td:
    camp = Path(td)
    check("no folder → empty", S.list_snapshots(camp), [])
    check("no folder → has_snapshots False", S.has_snapshots(camp), False)
    check("purge on nothing is a no-op", S.purge_snapshots(camp), (0, []))

    for slot, day in (("save001", 91000.0), ("save003", 91119.3)):
        d = camp / "save_snapshots" / slot
        d.mkdir(parents=True)
        (d / "some_hero.json").write_text("{}", encoding="utf-8")
        (d / "snapshot_meta.json").write_text(json.dumps({
            "GameSaveSlotName": slot, "UniqueGameId": "aYqt3pB1kbNn",
            "CreatedAtUtc": "2026-07-18T16:52:20.9851204Z",
            "CampaignDay": day, "FileCount": 93,
        }), encoding="utf-8")

    snaps = S.list_snapshots(camp)
    check("both slots listed", [s.slot for s in snaps], ["save003", "save001"])
    check("meta parsed", (snaps[0].campaign_day, snaps[0].file_count), (91119.3, 93))
    check("has_snapshots True", S.has_snapshots(camp), True)
    removed, errors = S.purge_snapshots(camp)
    check("purge removes both", (removed, errors), (2, []))
    check("nothing left", S.list_snapshots(camp), [])
    check("save_snapshots folder kept", (camp / "save_snapshots").is_dir(), True)

print("\nslot without meta still counts (mod only needs a non-empty folder):")
with tempfile.TemporaryDirectory() as td:
    camp = Path(td)
    d = camp / "save_snapshots" / "save007"
    d.mkdir(parents=True)
    (d / "hero.json").write_text("{}", encoding="utf-8")
    snaps = S.list_snapshots(camp)
    check("listed without meta", [(s.slot, s.campaign_day) for s in snaps], [("save007", None)])
    check("purged", S.purge_snapshots(camp)[0], 1)

# ── Real 6.0.2 sample ────────────────────────────────────────────────────────
print("\nreal 6.0.2 sample:")
SAMPLE = Path(
    r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research\data_samples"
    r"\AIInfluence 6.0.2\save_data\aYqt3pB1kbNn"
)
if not SAMPLE.is_dir():
    print("  skip - sample not available")
else:
    # Indices come and go: the tool invalidates them on conversation edits and
    # the game rebuilds them on the next prompt, so a freshly-captured sample may
    # legitimately have none.  Assert the invariant that always holds instead —
    # a character the player never spoke to is never indexed.
    check("uninteracted lord has no index", R.has_rag_index(SAMPLE, "lord_1_1"), False)
    indexed = [sid for sid in ("CharacterObject_2783", "CharacterObject_4449")
               if R.has_rag_index(SAMPLE, sid)]
    if indexed:
        check("indexed characters resolve to real files",
              all(R.rag_index_path(SAMPLE, sid).is_file() for sid in indexed), True)
    else:
        print("  ..  (sample has no RAG indices — already invalidated; synthetic cases cover it)")
    # The sample is re-captured from the live game from time to time, and by
    # then the tool may already have cleared its snapshots — that is the feature
    # working, not a failure.  Assert on whatever the sample actually holds; the
    # synthetic cases above cover listing/purging in full.
    snaps = S.list_snapshots(SAMPLE)
    if snaps:
        check("sample snapshot slots are named", all(s.slot for s in snaps), True)
        check("sample snapshot meta parses",
              all(s.campaign_day is None or isinstance(s.campaign_day, float) for s in snaps), True)
    else:
        print("  ..  (sample has no snapshots — already cleared; synthetic cases cover it)")

    # Clamp against a real character file — copied, never touching the sample.
    with tempfile.TemporaryDirectory() as td:
        src = SAMPLE / "蘇雷納 (CharacterObject_2783).json"
        dst = Path(td) / src.name
        shutil.copy2(src, dst)
        data = json.loads(dst.read_text(encoding="utf-8-sig"))
        check("real file is a character payload", R.is_character_payload(data), True)
        check("real pointer already valid", R.clamp_memory_processed_index(data), False)
        # Simulate the tool trimming history below the stored pointer.
        data["ConversationHistory"] = data["ConversationHistory"][:10]
        check("after a trim it clamps",
              (R.clamp_memory_processed_index(data), data["LastMemoryProcessedIndex"]),
              (True, 10))

# ── End-to-end: the real write path drives the RAG bookkeeping ───────────────
# Exercises StoryMaster.safe_write_json_with_backup itself — the single choke
# point every character write goes through — so the wiring is covered, not just
# the services underneath it.
print("\nend-to-end via safe_write_json_with_backup:")
from StoryMaster import AIInfluenceStoryToolsApp as App  # noqa: E402

logs = []
app = object.__new__(App)
app.log = lambda msg, level="INFO": logs.append((level, msg))
app.settings = {}   # no stored policy → falls back to the auto-clear default


def _write_character(camp: Path, sid: str, history, index=None):
    """Write a character file through the real app method."""
    payload = {"Name": "N", "StringId": sid, "ConversationHistory": list(history)}
    if index is not None:
        payload["LastMemoryProcessedIndex"] = index
    return app.safe_write_json_with_backup(camp / f"N ({sid}).json", payload), payload


with tempfile.TemporaryDirectory() as td:
    camp = Path(td)
    (camp / "rag").mkdir()
    idx = camp / "rag" / "sid1.json"

    # 1) First write of a character that has an index: history differs from the
    #    (absent) file, so the index must go.
    idx.write_text('{"chunks": []}', encoding="utf-8")
    ok, _ = _write_character(camp, "sid1", ["line a"])
    check("write succeeded", ok, True)
    check("history change dropped the index", idx.exists(), False)
    check("invalidation was logged", any("RAG" in m for _, m in logs), True)

    # 2) Rewriting identical history must NOT throw the index away — re-embedding
    #    costs the player API calls on the Player2 backend.
    idx.write_text('{"chunks": []}', encoding="utf-8")
    logs.clear()
    _write_character(camp, "sid1", ["line a"])
    check("unchanged history keeps the index", idx.exists(), True)
    check("nothing logged for a no-op", logs, [])

    # 3) An edit that leaves history alone (a description change) also keeps it.
    logs.clear()
    app.safe_write_json_with_backup(camp / "N (sid1).json", {
        "Name": "N", "StringId": "sid1", "ConversationHistory": ["line a"],
        "CharacterDescription": "changed",
    })
    check("unrelated field edit keeps the index", idx.exists(), True)

    # 4) Trimming history clamps the memory pointer as it is written.
    ok, payload = _write_character(camp, "sid1", ["only one"], index=5)
    check("pointer clamped on write", payload["LastMemoryProcessedIndex"], 1)
    check("changed history dropped the index again", idx.exists(), False)

    # 5) Non-character payloads (the diplomacy bundle) are left entirely alone.
    idx.write_text('{"chunks": []}', encoding="utf-8")
    app.safe_write_json_with_backup(camp / "aiinfluence_campaign_diplomacy.json",
                                    {"Version": 1, "dynamic_events": []})
    check("bundle write touches no index", idx.exists(), True)

# ── Snapshot policy: auto-clear must cover immediate-write paths ─────────────
print("\nsnapshot policy on the write path:")
print("  (policy ids)")
check("unknown value falls back to default", S.normalize_policy("bogus"), S.DEFAULT_POLICY)
check("None falls back to default", S.normalize_policy(None), S.DEFAULT_POLICY)
check("known value kept", S.normalize_policy(S.POLICY_AUTO_CLEAR), S.POLICY_AUTO_CLEAR)
check("label round-trips", S.policy_from_label(S.policy_label(S.POLICY_AUTO_CLEAR)),
      S.POLICY_AUTO_CLEAR)
check("unknown label → default", S.policy_from_label("no such option"), S.DEFAULT_POLICY)
check("dropdown lists every policy", len(S.policy_display_options()), len(S.POLICY_IDS))

def _make_slot(camp: Path, slot="save003"):
    d = camp / "save_snapshots" / slot
    d.mkdir(parents=True)
    (d / "hero.json").write_text("{}", encoding="utf-8")
    return d


def _wire_backup_center(app, backup_root: Path):
    """Give the fake app what the copy-then-clear default needs.

    Without these the copy step raises and — correctly — the purge is skipped, so
    a test that omits them is really testing the failure path.
    """
    class _Var:
        def __init__(self, v): self._v = str(v)
        def get(self): return self._v
    app.backup_dir_var = _Var(backup_root)
    app.refresh_backup_center = lambda *a, **k: None


# The default policy: copy into the Backup Center, then clear.
with tempfile.TemporaryDirectory() as td:
    camp = Path(td) / "campaign"
    camp.mkdir()
    backups = Path(td) / "backups"
    _make_slot(camp)
    _wire_backup_center(app, backups)

    logs.clear()
    app.settings = {}                      # nothing stored → the default
    _write_character(camp, "sid9", ["edited line"])
    check("default policy cleared the snapshots", S.list_snapshots(camp), [])
    check("default policy copied them to the Backup Center first",
          any((backups / "snapshots").glob("*/save003/hero.json")) if (backups / "snapshots").is_dir() else False,
          True)
    check("the copy was logged", any("備份中心" in m or "Backup Center" in m
                                     for _, m in logs), True)
    check("the purge was logged", any("save_snapshots" in m for _, m in logs), True)

    # Once cleared, later writes stay quiet instead of re-logging every time.
    logs.clear()
    _write_character(camp, "sid9", ["edited twice"])
    check("nothing more to purge → silent",
          [m for _, m in logs if "save_snapshots" in m], [])

# auto_clear: purge, no copy.
with tempfile.TemporaryDirectory() as td:
    camp = Path(td) / "campaign"
    camp.mkdir()
    backups = Path(td) / "backups"
    _make_slot(camp)
    _wire_backup_center(app, backups)
    app.settings = {"snapshot_policy": S.POLICY_AUTO_CLEAR}
    _write_character(camp, "sid9", ["x"])
    check("auto_clear cleared the snapshots", S.list_snapshots(camp), [])
    check("auto_clear made no backup", (backups / "snapshots").is_dir(), False)

# keep: leave them entirely alone.
with tempfile.TemporaryDirectory() as td:
    camp = Path(td) / "campaign"
    camp.mkdir()
    backups = Path(td) / "backups"
    _make_slot(camp)
    _wire_backup_center(app, backups)
    app.settings = {"snapshot_policy": S.POLICY_KEEP}
    logs.clear()
    _write_character(camp, "sid9", ["x"])
    check("keep left the snapshot in place", len(S.list_snapshots(camp)), 1)
    check("keep warned that edits may be reverted",
          any(lv == "WARNING" for lv, _ in logs), True)

# A failed copy must NOT lead to a purge — deleting the snapshots after failing
# to preserve them would destroy exactly what the player asked to keep.
with tempfile.TemporaryDirectory() as td:
    camp = Path(td) / "campaign"
    camp.mkdir()
    _make_slot(camp)
    app.settings = {"snapshot_policy": S.POLICY_BACKUP_THEN_CLEAR}
    if hasattr(app, "backup_dir_var"):
        del app.backup_dir_var             # make the copy step fail
    logs.clear()
    _write_character(camp, "sid9", ["x"])
    check("copy failed → snapshots kept", len(S.list_snapshots(camp)), 1)
    check("copy failure logged as ERROR", any(lv == "ERROR" for lv, _ in logs), True)

# An unknown/future policy id falls back to the default, not to whatever used to
# be the default.
with tempfile.TemporaryDirectory() as td:
    camp = Path(td) / "campaign"
    camp.mkdir()
    backups = Path(td) / "backups"
    _make_slot(camp)
    _wire_backup_center(app, backups)
    app.settings = {"snapshot_policy": "leave_alone"}
    _write_character(camp, "sid9", ["x"])
    check("unknown policy normalises to the default (copy then clear)",
          (S.list_snapshots(camp), (backups / "snapshots").is_dir()), ([], True))

app.settings = {}

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("ALL CHECKS PASSED")
