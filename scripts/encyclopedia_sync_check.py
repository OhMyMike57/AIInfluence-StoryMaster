"""Regression: the encyclopedia toggle + restore rules (v1.2.1 A).

The module is C# and cannot run headless here, so this locks the parts that are
checkable from outside — the source contract and the field data — rather than
pretending to execute it:

  1. the five persona fields, their section titles and the MCM toggles line up
     one-to-one, in the same order (a mismatch would put the wrong heading on a
     section, or silently drop one);
  2. the defaults reproduce 1.2.0's three-section page, so upgrading changes
     nothing until the player opts in;
  3. the master switch is checked in *both* write paths (session sync and the
     Harmony postfix) — missing either leaves the feature half-on;
  4. the restore tiers are ordered exact → XML → regenerate, and the dead-hero
     guard sits before the regenerate tier (regenerating would erase an obituary);
  5. every persona field the layout reads exists in real 6.0 character files.

Run: python scripts/encyclopedia_sync_check.py
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYNC = ROOT / "mod" / "src" / "EncyclopediaSync.cs"
BRIDGE = ROOT / "mod" / "src" / "Settings" / "SettingsBridge.cs"
SETTINGS = ROOT / "mod" / "src" / "Settings" / "StoryMasterSettings.cs"
SAMPLE = Path(r"D:\Bannerlord Mods\B_Claude\AIInfluence_Research"
              r"\data_samples\AIInfluence 6.0.2\save_data")

FIELDS = ["CharacterDescription", "AIGeneratedBackstory", "AIGeneratedPersonality",
          "AIGeneratedCognitiveStyle", "AIGeneratedSpeechQuirks"]
TOGGLES = ["EncIncludeDescription", "EncIncludeBackstory", "EncIncludePersonality",
           "EncIncludeCognitiveStyle", "EncIncludeSpeechQuirks"]

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def section(name):
    print(f"\n[{name}]")


def arr(src, name):
    """Contents of a `private static readonly string[] Name = { ... };` block."""
    m = re.search(r"string\[\]\s+" + name + r"\s*=\s*\{(.*?)\};", src, re.S)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


def main():
    sync = SYNC.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    settings = SETTINGS.read_text(encoding="utf-8")

    # ── 1. fields / titles / toggles line up ────────────────────────────
    section("fields, titles and toggles are parallel")
    keys = arr(sync, "FieldKeys")
    titles = arr(sync, "FieldTitles")
    check(f"FieldKeys is the 5 persona fields (got {len(keys)})", keys == FIELDS)
    check(f"FieldTitles has one heading per field (got {len(titles)})",
          len(titles) == len(FIELDS))
    check("every heading is a localisation key",
          all(t.startswith("{=") for t in titles))

    # ApplyLayout's `want` array must list the toggles in field order.
    m = re.search(r"bool\[\]\s+want\s*=\s*\{(.*?)\};", sync, re.S)
    want = re.findall(r"cfg\.(\w+)", m.group(1)) if m else []
    check(f"ApplyLayout reads the toggles in field order (got {want})", want == TOGGLES)

    # ── 2. defaults reproduce 1.2.0 ─────────────────────────────────────
    section("defaults keep 1.2.0's page")
    defaults = re.search(r"Defaults\s*=>\s*new Cfg\s*\{(.*?)\};", bridge, re.S)
    dtxt = defaults.group(1) if defaults else ""
    want_default = {
        "EncyclopediaEnabled": "true",
        "EncIncludeDescription": "true",
        "EncIncludeBackstory": "true",
        "EncIncludePersonality": "true",
        "EncIncludeCognitiveStyle": "false",
        "EncIncludeSpeechQuirks": "false",
    }
    for k, v in want_default.items():
        found = re.search(rf"{k}\s*=\s*(\w+)", dtxt)
        check(f"bridge default {k} = {v}", found and found.group(1) == v)
        prop = re.search(rf"bool {k} \{{ get; set; \}} = (\w+);", settings)
        check(f"MCM default {k} = {v}", prop and prop.group(1) == v)

    # All five toggles must be exposed in MCM, or one can never be turned on.
    for t in TOGGLES + ["EncyclopediaEnabled"]:
        check(f"MCM exposes {t}", f"public bool {t}" in settings)

    # ── 3. the master switch gates both write paths ─────────────────────
    section("master switch gates every write path")
    for fn in ("Sync", "AfterModWrite"):
        body = _method_body(sync, fn)
        check(f"{fn} checks WritesEncyclopedia", "WritesEncyclopedia" in body)
        check(f"{fn} returns early when off",
              re.search(r"if\s*\(!\s*cfg\.WritesEncyclopedia\)\s*return", body) is not None)
    check("WritesEncyclopedia also requires a selected field",
          "EncIncludeDescription ||" in bridge or "EncIncludeDescription\n" in bridge)

    # ── 4. restore tier order and the dead-hero guard ───────────────────
    section("restore tiers are ordered, dead heroes guarded")
    body = _method_body(sync, "RestoreOriginals")
    i_exact = body.find("map.TryGetValue")
    i_xml = body.find("xml.TryGetValue")
    i_dead = body.find("hero.IsDead")
    i_regen = body.find("SetHeroEncyclopediaTextAndLinks")
    check("tier 1 (recorded original) comes first", 0 <= i_exact < i_xml)
    check("tier 2 (module XML) comes second", i_xml < i_regen)
    check("dead-hero guard precedes regeneration", 0 <= i_dead < i_regen)
    check("guard skips rather than writes",
          re.search(r"if\s*\(hero\.IsDead\)\s*\{\s*skipped\+\+;\s*continue;", body) is not None)
    check("restore clears the changed-since filter", "LastSync.Clear()" in body)
    check("capture stores only the first value per hero",
          "map.ContainsKey(id)" in _method_body(sync, "CaptureOriginal"))
    check("capture happens before the overwrite",
          _method_body(sync, "ApplyLayout").find("CaptureOriginal")
          < _method_body(sync, "ApplyLayout").find("hero.EncyclopediaText ="))

    # ── 5. the fields exist in real data ────────────────────────────────
    section("persona fields exist in real 6.0 saves")
    if not SAMPLE.is_dir():
        print("  (sample corpus not present — skipped)")
        return
    seen = {f: 0 for f in FIELDS}
    files = 0
    for camp in SAMPLE.iterdir():
        if not camp.is_dir():
            continue
        for p in camp.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(d, dict) or "StringId" not in d:
                continue
            files += 1
            for f in FIELDS:
                if isinstance(d.get(f), str) and d[f].strip():
                    seen[f] += 1
    check(f"corpus has character files ({files})", files > 0)
    for f in FIELDS:
        check(f"{f} present in real data ({seen[f]} files)", seen[f] > 0)


def _method_body(src, name):
    """Rough body of a C# method: from its signature to the next one at the same
    indent. Good enough to assert on ordering and presence."""
    m = re.search(r"\n        (?:public|private|internal)[^\n]*\b" + name + r"\s*\(", src)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r"\n        (?:public|private|internal)[^\n]*\w+\s*\(",
                    src[start + 10:])
    return src[start: start + 10 + nxt.start()] if nxt else src[start:]


if __name__ == "__main__":
    main()
    if FAILS:
        print(f"\n[FAIL] {len(FAILS)} check(s) failed:")
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print("\n[PASS] encyclopedia sync check passed")
