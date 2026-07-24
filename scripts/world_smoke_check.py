from __future__ import annotations

import argparse
import json
from pathlib import Path


def check_world_file(path: Path, expect_list: bool = True) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return [f"{path.name}: 檔案不存在"]
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        return [f"{path.name}: JSON 解析失敗 ({e})"]

    if expect_list and not isinstance(parsed, list):
        errs.append(f"{path.name}: 根節點須為陣列")
    if isinstance(parsed, list):
        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                errs.append(f"{path.name}[{i}]: 條目須為物件")
    return errs


def resolve_world_dirs(root: Path) -> list[Path]:
    """Return the directories that should hold world_info/world_secrets.

    Layout-aware (AI Influence 5.0.0 moved these files):
      • 5.0.x — per-campaign ``prompts/world_data/``. We glob for any such dir
        under *root*, so passing either a campaign folder or a parent like
        ``data_samples`` works.
      • 4.1.0 — files at the mod root (or the dir itself). When no
        ``prompts/world_data`` is found we fall back to *root* itself.
    """
    found = [p for p in sorted(root.glob("**/prompts/world_data")) if p.is_dir()]
    return found if found else [root]


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke check for world_info/world_secrets JSON")
    ap.add_argument("campaign_dir", type=Path, help="campaign folder, mod root, or data_samples")
    args = ap.parse_args()

    world_dirs = resolve_world_dirs(args.campaign_dir)

    errors: list[str] = []
    checked = 0
    for wd in world_dirs:
        wi, ws = wd / "world_info.json", wd / "world_secrets.json"
        # Skip dirs that have neither file (e.g. a parent dir with only one
        # campaign carrying world data) so a stray empty match isn't fatal.
        if not wi.exists() and not ws.exists() and len(world_dirs) > 1:
            continue
        checked += 1
        errors.extend(check_world_file(wi))
        errors.extend(check_world_file(ws))

    if checked == 0:
        errors.append(f"{args.campaign_dir}: 找不到 world_info/world_secrets（新版於 prompts/world_data/）")

    if errors:
        print("[FAIL] world smoke check failed:")
        for e in errors:
            print(" -", e)
        return 1

    print(f"[PASS] world smoke check passed（檢查 {checked} 處 world_data）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
