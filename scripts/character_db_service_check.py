"""Regression check for services/character_db_service (資料庫 tab data layer).

Self-contained: builds synthetic export attrs + a temp campaign dir, then
exercises row building, the filename rule, file index, generate, delete,
backup and batch-generate with exclusions.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.character_db_service import (  # noqa: E402
    character_filename, build_file_index, build_database_rows,
    generate_character_file, delete_character_file, backup_character_file,
    batch_generate, count_generatable,
)

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("  FAIL:", msg)
    else:
        print("  ok  -", msg)


def _writer(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def main():
    print("character_db_service check")

    # Filename rule: space -> middle dot; single name unchanged.
    check(character_filename("張恩 霍恩巴", "lord_6_1") == "張恩·霍恩巴 (lord_6_1).json",
          "filename joins space with middle dot")
    check(character_filename("貝德格", "lord_5_21_1") == "貝德格 (lord_5_21_1).json",
          "single-name filename unchanged")

    hero_attrs = {
        "main_hero": {"name": "玩家", "clan": "player_faction", "is_player": True, "age": 23},
        "lord_a": {"name": "領主甲", "clan": "c_emp", "occupation": "Lord", "age": 40,
                   "is_lord": True, "is_clan_leader": True, "alive": True, "spouse": "lord_x",
                   "culture": "empire", "gender": "male"},
        "wand_b": {"name": "浪人乙", "clan": "c_minor", "occupation": "Wanderer", "age": 17,
                   "is_wanderer": True, "alive": True, "gender": "female"},
        "note_c": {"name": "顯要丙", "clan": None, "occupation": "GangLeader", "age": 55,
                   "is_notable": True, "alive": False, "gender": "male"},
        "tmpl_d": {"name": "盾女", "is_template": True, "age": 25},
    }
    clan_attrs = {"c_emp": {"name": "帝國氏族", "kingdom": "empire"},
                  "c_minor": {"name": "小氏族", "kingdom": None}}

    rows = build_database_rows(hero_attrs, clan_attrs,
                               kingdom_names={"empire": "北帝國"},
                               clan_names={"c_emp": "帝國氏族", "c_minor": "小氏族"},
                               culture_names={"empire": "帝國文化"},
                               file_index={}, exclude_templates=True)
    by = {r["StringId"]: r for r in rows}
    check("main_hero" not in by, "player excluded from rows")
    check("tmpl_d" not in by, "template hero excluded")
    check(len(rows) == 3, f"3 real-NPC rows (got {len(rows)})")
    check(by["lord_a"]["KingdomName"] == "北帝國", "kingdom resolved via clan's kingdom")
    check(by["lord_a"]["Married"] is True, "spouse -> married True")
    check(by["wand_b"]["IsChild"] is True, "age 17 -> child")
    check(by["note_c"]["Alive"] is False, "dead notable Alive False")
    check(by["note_c"]["KingdomName"] == "" and by["note_c"]["Kingdom"] is None, "clanless notable = 在野")

    with tempfile.TemporaryDirectory() as td:
        camp = Path(td)
        # Generate lord_a; file should appear with the right name and pristine shape.
        p = generate_character_file(camp, by["lord_a"], _writer)
        check(p is not None and p.exists(), "generate created a file")
        check(p.name == "領主甲 (lord_a).json", "generated filename matches convention")
        gd = json.loads(p.read_text(encoding="utf-8"))
        check(gd.get("StringId") == "lord_a" and gd.get("ConversationHistory") == []
              and gd.get("Name") == "領主甲", "generated JSON is pristine + identity carried")
        # Generating again must refuse (file exists).
        check(generate_character_file(camp, by["lord_a"], _writer) is None,
              "generate refuses when file exists")

        # File index picks up the new file by StringId.
        idx = build_file_index(camp, lambda f: json.loads(f.read_text(encoding="utf-8-sig")))
        check(idx.get("lord_a") == p, "file index maps StringId -> path")

        # Backup copies into character/<campaign>/.
        bdir = camp / "_bak"
        bpath = backup_character_file(p, bdir, "CAMP1")
        check(bpath is not None and bpath.exists() and bpath.parent == bdir / "character" / "CAMP1",
              "backup written under character/<campaign>/")

        # Batch generate: default excludes minor (wand_b age 17). lord_a already
        # has a file -> skipped_existing. note_c (adult, dead) generated unless
        # exclude_dead. With defaults: only note_c generated.
        rows2 = build_database_rows(hero_attrs, clan_attrs, file_index=idx, exclude_templates=True)
        n_default = count_generatable(rows2, exclude_minor=True)
        check(n_default == 1, f"count_generatable default excludes minor+existing (got {n_default})")
        res = batch_generate(camp, rows2, _writer, exclude_minor=True)
        check(res["created"] == 1 and res["skipped_existing"] == 1 and res["skipped_excluded"] == 1,
              f"batch_generate created=1 skip_exist=1 skip_excl=1 (got {res})")

        # exclude_dead drops note_c too -> nothing generatable.
        rows3 = build_database_rows(hero_attrs, clan_attrs,
                                    file_index=build_file_index(camp, lambda f: json.loads(f.read_text(encoding="utf-8-sig"))),
                                    exclude_templates=True)
        check(count_generatable(rows3, exclude_minor=True, exclude_dead=True) == 0,
              "exclude_dead removes the dead notable")

        check(delete_character_file(p) and not p.exists(), "delete removes the file")

    if FAILS:
        print(f"\n[FAIL] {len(FAILS)} assertion(s) failed")
        sys.exit(1)
    print("\n[PASS] character_db_service check passed")


if __name__ == "__main__":
    main()
