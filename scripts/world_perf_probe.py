from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Simple world/campaign perf probe")
    ap.add_argument("campaign_dir", type=Path)
    args = ap.parse_args()
    c = args.campaign_dir

    t0 = time.perf_counter()
    npc_files = list(c.glob("*.json"))
    t1 = time.perf_counter()

    parsed = 0
    for p in npc_files:
        if p.name in {"world_info.json", "world_secrets.json"}:
            continue
        try:
            load_json(p)
            parsed += 1
        except Exception:
            pass
    t2 = time.perf_counter()

    wi = c / "world_info.json"
    ws = c / "world_secrets.json"
    wi_len = len(load_json(wi)) if wi.exists() else -1
    ws_len = len(load_json(ws)) if ws.exists() else -1
    t3 = time.perf_counter()

    print(f"scan_files_ms={(t1-t0)*1000:.2f}")
    print(f"parse_npc_ms={(t2-t1)*1000:.2f}")
    print(f"parse_world_ms={(t3-t2)*1000:.2f}")
    print(f"npc_files={parsed}, world_info_items={wi_len}, world_secrets_items={ws_len}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
