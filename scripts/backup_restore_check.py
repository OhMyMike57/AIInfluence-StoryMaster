"""Regression: Backup Center restore (v1.2.1 B-3).

Restore is the most destructive thing this tool does — it mirrors a backup over
live campaign data, deleting files the backup does not have. Everything below
runs in a throwaway temp tree and locks the properties that make that safe:

  1. after a restore the target is byte-for-byte the backup — added, changed and
     *extra* files all end in the recorded state;
  2. the plan is honest — its added/overwritten/unchanged/deleted buckets match
     what the apply pass actually does, and planning writes nothing;
  3. the safety backup really captures the pre-restore state, so an unwanted
     restore can be undone;
  4. the target is derived from the backup itself, per kind, and a restore can
     never write into (or over) the backup store;
  5. all four kinds — campaign / db / config / snapshot — resolve and restore.

Run: python scripts/backup_restore_check.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import backup_service as B  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


# ── helpers ─────────────────────────────────────────────────────────────

def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def tree(root: Path):
    """{relative posix path: content} for every file under *root*."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = Path(dirpath) / f
            out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return out


def entry_for(path: Path, kind: str, cid=None) -> B.BackupEntry:
    return B.BackupEntry(kind=kind, path=path, name=path.name,
                         campaign_id=cid, timestamp=None)


# ── 1. round trip: restore reproduces the backup exactly ────────────────

def test_round_trip(tmp: Path):
    print("\n[round trip — target ends up identical to the backup]")
    base = tmp / "backups"
    save_data = tmp / "save_data"
    camp = save_data / "CID1"

    # The recorded state.
    write(camp / "hero.json", '{"a": 1}')
    write(camp / "keep.json", "same-in-both")
    write(camp / "nested" / "deep.json", "original")
    bk = B.backup_campaign_dir(camp, base)
    recorded = tree(bk)

    # The live folder drifts: one edit, one new file, one deletion.
    write(camp / "hero.json", '{"a": 999}')          # → overwritten
    write(camp / "extra.json", "added-after-backup")  # → deleted by restore
    (camp / "nested" / "deep.json").unlink()          # → re-added by restore

    e = entry_for(bk, B.KIND_CAMPAIGN, "CID1")
    plan = B.plan_restore(e, camp)
    check("plan: 1 overwritten", plan.overwritten == ["hero.json"])
    check("plan: 1 added back", plan.added == ["nested/deep.json"])
    check("plan: 1 deleted", plan.deleted == ["extra.json"])
    check("plan: 1 unchanged", plan.unchanged == ["keep.json"])
    check("plan: total_changes = 3", plan.total_changes == 3)

    # Planning must not have touched anything.
    check("plan wrote nothing", (camp / "extra.json").exists()
          and not (camp / "nested" / "deep.json").exists())

    rep = B.restore_backup(e, camp, backup_base=base)
    check("restore ok", rep.ok and not rep.errors)
    check("restore wrote 2", rep.written == 2)
    check("restore removed 1", rep.removed == 1)
    check("TARGET == BACKUP (byte for byte)", tree(camp) == recorded)
    check("empty dirs pruned", not (camp / "nested").exists()
          or any((camp / "nested").iterdir()))


# ── 2. the safety backup is a real undo ─────────────────────────────────

def test_safety_backup(tmp: Path):
    print("\n[safety backup captures the pre-restore state]")
    base = tmp / "backups"
    camp = tmp / "save_data" / "CID2"

    write(camp / "a.json", "v1")
    bk = B.backup_campaign_dir(camp, base)

    write(camp / "a.json", "v2-precious")     # the state we must be able to get back
    write(camp / "b.json", "also-precious")
    before = tree(camp)

    e = entry_for(bk, B.KIND_CAMPAIGN, "CID2")
    rep = B.restore_backup(e, camp, backup_base=base)
    check("restore ok", rep.ok)
    check("safety backup created", rep.safety_backup is not None
          and Path(rep.safety_backup).is_dir())
    check("safety backup == pre-restore state", tree(Path(rep.safety_backup)) == before)
    check("live really did change", tree(camp) != before)

    # And the undo works: restore the safety backup back over the target.
    undo = entry_for(Path(rep.safety_backup), B.KIND_CAMPAIGN, "CID2")
    rep2 = B.restore_backup(undo, camp, backup_base=base)
    check("undo ok", rep2.ok)
    check("undo restored the precious state", tree(camp) == before)


# ── 3. target resolution per kind ───────────────────────────────────────

def test_target_resolution(tmp: Path):
    print("\n[target is derived from the backup, per kind]")
    save_data = tmp / "sd"
    config = tmp / "cfg"

    def resolve(kind, cid):
        return B.resolve_restore_target(entry_for(tmp / "x", kind, cid),
                                        save_data_dir=save_data, config_dir=config)

    check("campaign → <save_data>/<cid>",
          resolve(B.KIND_CAMPAIGN, "C") == save_data / "C")
    check("db → <campaign>/storytools",
          resolve(B.KIND_DB, "C") == save_data / "C" / "storytools")
    check("snapshot → <campaign>/save_snapshots",
          resolve(B.KIND_SNAPSHOT, "C") == save_data / "C" / "save_snapshots")
    check("config → the config dir", resolve(B.KIND_CONFIG, None) == config)

    for kind, cid, why in [(B.KIND_CAMPAIGN, None, "campaign without a campaign id"),
                           ("bogus", "C", "an unknown kind")]:
        try:
            resolve(kind, cid)
            check(f"rejects {why}", False)
        except B.RestoreError:
            check(f"rejects {why}", True)

    try:
        B.resolve_restore_target(entry_for(tmp / "x", B.KIND_CAMPAIGN, "C"),
                                 save_data_dir=None, config_dir=config)
        check("rejects a missing save_data root", False)
    except B.RestoreError:
        check("rejects a missing save_data root", True)


# ── 4. the backup store is off-limits as a target ───────────────────────

def test_backup_store_guard(tmp: Path):
    print("\n[a restore can never write into the backup store]")
    base = tmp / "backups"
    camp = tmp / "sd" / "CID3"
    write(camp / "a.json", "x")
    bk = B.backup_campaign_dir(camp, base)
    e = entry_for(bk, B.KIND_CAMPAIGN, "CID3")

    rep = B.restore_backup(e, base / SAFE_SUB, backup_base=base)
    check("refuses a target inside backups/", not rep.ok and rep.errors)

    rep = B.restore_backup(e, bk, backup_base=base)
    check("refuses restoring onto itself", not rep.ok)

    rep = B.restore_backup(e, tmp, backup_base=base)
    check("refuses a target that contains backups/", not rep.ok)

    check("backup survived every refusal", (bk / "a.json").read_text() == "x")


SAFE_SUB = "save_data/CID3_x"


# ── 5. all four kinds actually restore ──────────────────────────────────

def test_all_kinds(tmp: Path):
    print("\n[every kind restores]")
    base = tmp / "backups"
    save_data = tmp / "sd"
    config = tmp / "cfg"
    camp = save_data / "CID4"

    cases = [
        (B.KIND_CAMPAIGN, camp, "char.json"),
        (B.KIND_DB, camp / "storytools", "terminology.json"),
        (B.KIND_SNAPSHOT, camp / "save_snapshots", "save001/snapshot_meta.json"),
        (B.KIND_CONFIG, config, "story_tools_settings.json"),
    ]
    for kind, target, rel in cases:
        write(target / rel, "recorded")
        sub = B._KIND_SUBDIR[kind]
        bk = base / sub / f"bk_{kind}"
        bk.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, bk, dirs_exist_ok=True)

        write(target / rel, "drifted")
        e = entry_for(bk, kind, None if kind == B.KIND_CONFIG else "CID4")
        rep = B.restore_backup(e, target, backup_base=base)
        check(f"{kind}: restored", rep.ok and (target / rel).read_text() == "recorded")


# ── 6. snapshot backup helper ───────────────────────────────────────────

def test_backup_snapshots(tmp: Path):
    print("\n[backup_snapshots skips nothing-to-do]")
    base = tmp / "backups"
    camp = tmp / "sd" / "CID5"
    camp.mkdir(parents=True)

    check("no save_snapshots → None", B.backup_snapshots(camp, base) is None)
    (camp / "save_snapshots").mkdir()
    check("empty save_snapshots → None", B.backup_snapshots(camp, base) is None)

    write(camp / "save_snapshots" / "save001" / "meta.json", "{}")
    out = B.backup_snapshots(camp, base)
    check("with content → a backup path", out is not None and Path(out).is_dir())
    check("content copied", (Path(out) / "save001" / "meta.json").is_file())
    check("listed as a snapshot backup",
          any(e.kind == B.KIND_SNAPSHOT and e.campaign_id == "CID5"
              for e in B.list_backups(base)))


# ── 7. planning against a missing / empty backup ────────────────────────

def test_plan_errors(tmp: Path):
    print("\n[planning refuses impossible restores]")
    base = tmp / "backups"
    ghost = base / "save_data" / "gone"
    try:
        B.plan_restore(entry_for(ghost, B.KIND_CAMPAIGN, "g"), tmp / "t")
        check("missing backup raises", False)
    except B.RestoreError:
        check("missing backup raises", True)

    empty = base / "save_data" / "empty_bk"
    empty.mkdir(parents=True)
    try:
        B.plan_restore(entry_for(empty, B.KIND_CAMPAIGN, "e"), tmp / "t")
        check("empty backup raises", False)
    except B.RestoreError:
        check("empty backup raises", True)


# ── 8. same-second backups must not merge ───────────────────────────────

def test_same_second_collision(tmp: Path):
    """Regression for a real bug: the timestamp has one-second resolution, so a
    restore and its immediate undo produced two safety backups with the same
    name. With ``dirs_exist_ok=True`` the second one merged the post-restore
    state into the folder the undo was reading from, destroying it."""
    print("\n[two backups in the same second stay separate]")
    base = tmp / "backups"
    camp = tmp / "sd" / "CID6"

    write(camp / "a.json", "first")
    b1 = B.backup_campaign_dir(camp, base)
    write(camp / "a.json", "second")
    b2 = B.backup_campaign_dir(camp, base)

    check("two distinct folders", Path(b1) != Path(b2))
    check("first keeps its own content", (Path(b1) / "a.json").read_text() == "first")
    check("second has the newer content", (Path(b2) / "a.json").read_text() == "second")

    c1 = B.backup_tool_config(camp, base)
    c2 = B.backup_tool_config(camp, base)
    check("config backups also stay separate", Path(c1) != Path(c2))


def main():
    with tempfile.TemporaryDirectory(prefix="sm_restore_") as td:
        tmp = Path(td)
        test_round_trip(tmp / "t1")
        test_safety_backup(tmp / "t2")
        test_target_resolution(tmp / "t3")
        test_backup_store_guard(tmp / "t4")
        test_all_kinds(tmp / "t5")
        test_backup_snapshots(tmp / "t6")
        test_plan_errors(tmp / "t7")
        test_same_second_collision(tmp / "t8")

    if FAILS:
        print(f"\n[FAIL] {len(FAILS)} check(s) failed:")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print("\n[PASS] backup restore check passed")


if __name__ == "__main__":
    main()
