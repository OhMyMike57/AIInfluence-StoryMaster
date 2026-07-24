from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controllers.campaign_controller import choose_target_campaign


def expect(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def main():
    camps = ["A_Campaign", "B_Campaign"]

    t = choose_target_campaign(camps, "B_Campaign", "A_Campaign")
    expect(t == "B_Campaign", "preferred campaign should win when available")

    t = choose_target_campaign(camps, "X_NotExist", "A_Campaign")
    expect(t == "A_Campaign", "current campaign should be used when preferred not available")

    t = choose_target_campaign(camps, "", "")
    expect(t == "A_Campaign", "first sorted campaign should be fallback")

    t = choose_target_campaign([], "", "")
    expect(t == "", "empty campaign list should return empty target")

    print("[PASS] startup sanity check passed")


if __name__ == "__main__":
    main()
