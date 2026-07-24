"""Regression for save_data campaign-folder identity (6.0 適配 P0-1/P1-4).

Covers the reserved-name / content rules shared by the campaign list, the
heartbeat reader and the connector's C# ``FileContract`` scan.  Runs against
synthetic folders plus, when available, the real AI Influence 6.0.2 sample.

Run: python scripts/campaign_identity_check.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.campaign_controller import list_campaigns  # noqa: E402
from services.game_status_service import _clean_campaign_id  # noqa: E402
from services.path_service import (  # noqa: E402
    is_campaign_folder_name,
    looks_like_campaign_dir,
)

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} - {label}")
    if not ok:
        print(f"        got : {got}\n        want: {want}")
        FAILS.append(label)


# ── Name rules ────────────────────────────────────────────────────────────────
print("name rules:")
check("real campaign id accepted", is_campaign_folder_name("aYqt3pB1kbNn"), True)
check("second real id accepted", is_campaign_folder_name("hfOSV7HS5Nbj"), True)
check("storytools rejected", is_campaign_folder_name("storytools"), False)
check("StoryTools rejected (case)", is_campaign_folder_name("StoryTools"), False)
check("_portrait_tmp rejected", is_campaign_folder_name("_portrait_tmp"), False)
check("unknown _-prefixed rejected", is_campaign_folder_name("_future_tmp"), False)
check("empty rejected", is_campaign_folder_name(""), False)

# ── Heartbeat sanitising (the 6.0 connector bug) ──────────────────────────────
print("\nheartbeat campaign id:")
check("valid id passes", _clean_campaign_id("aYqt3pB1kbNn"), "aYqt3pB1kbNn")
check("_portrait_tmp → None", _clean_campaign_id("_portrait_tmp"), None)
check("storytools → None", _clean_campaign_id("storytools"), None)
check("None → None", _clean_campaign_id(None), None)
check("empty → None", _clean_campaign_id(""), None)
check("whitespace trimmed", _clean_campaign_id("  aYqt3pB1kbNn "), "aYqt3pB1kbNn")

# ── Content rules + listing on a synthetic tree ───────────────────────────────
print("\nsynthetic save_data tree:")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    # A campaign carrying the diplomacy bundle only.
    (root / "camp0001AAAA").mkdir()
    (root / "camp0001AAAA" / "aiinfluence_campaign_diplomacy.json").write_text("{}", encoding="utf-8")
    # A campaign carrying the prompts tree only (fresh campaign).
    (root / "camp0002BBBB" / "prompts").mkdir(parents=True)
    # Reserved folders that also carry plausible-looking content.
    (root / "storytools").mkdir()
    (root / "_portrait_tmp").mkdir()
    # A stray folder with no campaign markers.
    (root / "randomfolder").mkdir()

    check("bundle-only dir validates", looks_like_campaign_dir(root / "camp0001AAAA"), True)
    check("prompts-only dir validates", looks_like_campaign_dir(root / "camp0002BBBB"), True)
    check("empty dir rejected", looks_like_campaign_dir(root / "randomfolder"), False)
    check("missing dir rejected", looks_like_campaign_dir(root / "nope"), False)
    check(
        "list_campaigns keeps only real campaigns",
        list_campaigns(root),
        ["camp0001AAAA", "camp0002BBBB"],
    )

with tempfile.TemporaryDirectory() as td:
    # Nothing passes the content check → fall back to the name-filtered list
    # rather than telling the player they have no campaigns at all.
    root = Path(td)
    (root / "camp0003CCCC").mkdir()
    (root / "storytools").mkdir()
    check(
        "content filter falls back when it would empty the list",
        list_campaigns(root),
        ["camp0003CCCC"],
    )

# ── Real 6.0.2 sample (skipped when the research share isn't mounted) ─────────
print("\nreal 6.0.2 sample:")
SAMPLE = Path(
    r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research\data_samples"
    r"\AIInfluence 6.0.2\save_data"
)
if not SAMPLE.is_dir():
    print("  skip - sample not available")
else:
    names = sorted(p.name for p in SAMPLE.iterdir() if p.is_dir())
    check("sample really contains _portrait_tmp", "_portrait_tmp" in names, True)
    check("sample really contains storytools", "storytools" in names, True)
    # Assert the *rule*, not an exact list: the research share accumulates dated
    # capture folders over time, and those are genuine campaign folders by
    # content — pinning the list here just breaks whenever a save is captured.
    found = list_campaigns(SAMPLE)
    check("the live campaign is listed", "aYqt3pB1kbNn" in found, True)
    check("reserved folders are never listed",
          [n for n in ("_portrait_tmp", "storytools") if n in found], [])
    check("everything listed passes the content check",
          [n for n in found if not looks_like_campaign_dir(SAMPLE / n)], [])
    check("a folder of loose character files is not a campaign",
          [n for n in names
           if n.endswith("群聊後自動同步前") and n in found], [])
    check(
        "campaign dir validates by content",
        looks_like_campaign_dir(SAMPLE / "aYqt3pB1kbNn"),
        True,
    )
    check(
        "_portrait_tmp fails content check too",
        looks_like_campaign_dir(SAMPLE / "_portrait_tmp"),
        False,
    )
    check(
        "storytools fails content check too",
        looks_like_campaign_dir(SAMPLE / "storytools"),
        False,
    )

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("ALL CHECKS PASSED")
