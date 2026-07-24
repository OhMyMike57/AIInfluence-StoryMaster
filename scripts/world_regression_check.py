from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.world_owner_service import remove_owners, clear_owners, clone_payload, apply_clone
from services.world_service import dump_world_items
from controllers.world_save_controller import world_files_changed, world_save_log_message


def expect(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def main():
    info_map = {"Bloodraven_Creed": ["A", "B", "C"]}
    secret_map = {"Player_Plan": ["X"]}

    # remove selected owners
    _, removed = remove_owners(info_map, "Bloodraven_Creed", ["A", "C"])
    expect(removed == 2, "remove_owners should remove 2 entries")
    expect(info_map["Bloodraven_Creed"] == ["B"], "remaining info owners should be ['B']")

    # clear owners
    _, cleared = clear_owners(info_map, "Bloodraven_Creed")
    expect(cleared == 1, "clear_owners should clear 1 entry")
    expect("Bloodraven_Creed" not in info_map, "item should be removed after clear")

    # clone/apply cross-kind should write to target map only
    src_payload = clone_payload("info", "Bloodraven_Creed", "公開訊息", ["Lord_1", "Lord_2"])
    _, n = apply_clone(secret_map, "Player_Plan", src_payload)
    expect(n == 2, "apply_clone count mismatch")
    expect(secret_map["Player_Plan"] == ["Lord_1", "Lord_2"], "secret target list should be replaced")


    # world format: simple array should be inline in world files
    out = ROOT / "scripts" / "_tmp_world_format_test.json"
    dump_world_items(out, [{
        "id": "example1",
        "description": "example11",
        "usageChance": 8,
        "applicableNPCs": ["lords", "companions", "village_notables"],
        "category": "world"
    }])
    txt = out.read_text(encoding="utf-8")
    expect('"applicableNPCs": ["lords", "companions", "village_notables"]' in txt, "world array should be inline")
    out.unlink(missing_ok=True)

    info_changed, sec_changed = world_files_changed([{"id": "1"}], [{"id": "1"}], [{"id": "A"}], [{"id": "B"}])
    expect(info_changed is False and sec_changed is True, "world_files_changed should detect per-file changes")
    expect(world_save_log_message(False, False, True) == "僅擁有者變更已儲存（world 檔未重寫）", "world_save_log_message owner-only mismatch")
    expect(world_save_log_message(True, False, False) == "僅訊息與秘密條目變更已儲存", "world-only log mismatch")

    print("[PASS] world regression check passed")


if __name__ == "__main__":
    main()
