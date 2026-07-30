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
  4. the restore tiers are ordered exact → XML → clear, the dead-hero guard sits
     before the clear (clearing would erase an obituary), and no tier ever
     persists the game's own template (its variables resolve against globals that
     are gone by render time — the "is a member of the , ." bug);
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
        # Any return form is fine — a bare `return;`, `return 0;`, or a block that
        # logs first — as long as nothing is written on that path.
        after = body[body.find("!cfg.WritesEncyclopedia"):]
        m_ret = re.search(r"\breturn\b[^;]*;", after)
        gate = after[:m_ret.end()] if m_ret else ""
        check(f"{fn} returns on that path", bool(gate))
        check(f"{fn} writes nothing before returning",
              "ApplyLayout" not in gate and "EncyclopediaText =" not in gate)
    check("WritesEncyclopedia also requires a selected field",
          "EncIncludeDescription ||" in bridge or "EncIncludeDescription\n" in bridge)

    # ── 4. restore tier order and the dead-hero guard ───────────────────
    section("restore tiers are ordered, dead heroes guarded")
    body = _method_body(sync, "RestoreOriginals")
    i_exact = body.find("map.TryGetValue")
    i_xml = body.find("xml.TryGetValue")
    i_dead = body.find("hero.IsDead")
    # "cleared++" rather than TextObject.GetEmpty(): tier 1 also writes an empty
    # TextObject (for a recorded original that was itself empty), so the bare call
    # is not a marker for tier 3.
    i_clear = body.find("cleared++")
    check("tier 1 (recorded original) comes first", 0 <= i_exact < i_xml)
    check("tier 2 (module XML) comes second", 0 <= i_xml < i_clear)
    check("dead-hero guard precedes the clear", 0 <= i_dead < i_clear)
    check("guard skips rather than writes",
          re.search(r"if\s*\(hero\.IsDead\)\s*\{\s*skipped\+\+;\s*continue;", body) is not None)

    # Tier 3 must CLEAR the field, never store the game's template. That template
    # resolves {LORD.FIRSTNAME} / {CLAN_NAME} / {REPUTATION} against *global* text
    # variables set moments earlier, so persisting it renders as
    # "is a member of the , . … is a person." — the reported bug. The game itself
    # calls the generator and discards the result.
    check("tier 3 clears the field", i_clear > 0)
    check("tier 3 never persists the game's template",
          "SetHeroEncyclopediaTextAndLinks" not in _strip_cs_comments(sync))
    check("restore clears the changed-since filter", "LastSync.Clear()" in body)
    check("capture stores only the first value per hero",
          "map.ContainsKey(id)" in _method_body(sync, "CaptureOriginal"))
    check("capture happens before the overwrite",
          _method_body(sync, "ApplyLayout").find("CaptureOriginal")
          < _method_body(sync, "ApplyLayout").find("hero.EncyclopediaText ="))

    # ── 4b. our own layout is never treated as an original ──────────────
    section("our own layout is never mistaken for an original")
    cap = _method_body(sync, "CaptureOriginal")
    check("capture rejects our own layout", "IsOurLayout(text)" in cap)
    check("capture returns instead of storing it",
          re.search(r"if\s*\(IsOurLayout\(text\)\)\s*return;", cap) is not None)

    body = _method_body(sync, "RestoreOriginals")
    check("restore discards a record that is our layout",
          "IsOurLayout(original)" in body)
    # The poisoned record must be removed AT THE POINT OF DISCOVERY, not collected
    # for a pass after the loop: the tier that then handles the hero calls
    # Remember(), and a deferred removal deletes the correct value it just wrote —
    # leaving the hero with no record, which is what lets a later sync capture
    # someone else's text as "the original".
    i_disc = body.find("IsOurLayout(original)")
    disc = body[i_disc: i_disc + 700]
    check("poisoned record removed inside the loop", "map.Remove(kv.Key)" in disc)
    check("no deferred removal pass", "foreach (string id in stale)" not in body)
    check("the map is persisted", "FlushOriginals()" in body)

    # A restore must never leave a hero *without* a record. Deleting the record
    # after applying it looked reasonable ("a spent undo token is worthless") and
    # created a self-renewing loop: with no record, the next sync captured whatever
    # was on the page — including a page an earlier build had mangled — and wrote
    # it back in as "the original". Tiers 2 and 3 therefore record what they just
    # wrote, which is both truthful and enough to block re-capture.
    check("tier 2 records the XML text it applied",
          "Remember(map, kv.Key, fromFile)" in body)
    check("tier 3 records the cleared state",
          'Remember(map, kv.Key, "")' in body)
    check("a record is never dropped just because it was used",
          "stale" not in body)
    rem = _method_body(sync, "Remember")
    check("Remember only marks dirty on a real change", "existing == text" in rem)

    # With the layout off the postfix must say so once, so a report of "the mod's
    # persona does not show" can be attributed without guessing.
    off = _method_body(sync, "AfterModWrite")
    check("the postfix logs once when it stands down",
          "_standDownLogged" in off and "FileContract.Log" in off)
    # Both write paths must persist what they captured; the postfix fires
    # mid-session and Sync may never run again before the player quits.
    for fn in ("Sync", "AfterModWrite"):
        check(f"{fn} flushes captured originals",
              "FlushOriginals()" in _method_body(sync, fn))

    det = _method_body(sync, "IsOurLayout")
    check("detection resolves the localised headings", "FieldTitles" in det)
    check("detection also matches the heading shape (— … —)",
          "'—'" in det or "—" in det)

    # Mirror the C# rule in Python and try it on the shapes that matter — the C#
    # cannot run here, but the *rule* is what regressed and it is checkable.
    def is_our_layout(text, headings):
        if not text or not text.strip():
            return False
        for h in headings:
            if h and h in text:
                return True
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            return len(line) > 2 and line[0] == "—" and line[-1] == "—"
        return False

    zh = ["— 描述 —", "— 背景 —", "— 性格 —", "— 認知風格 —", "— 語言癖好 —"]
    cases = [
        # (text, expected, why)
        ("— 背景 —\n伊倫出生在…\n\n— 性格 —\n矛盾的巴坦尼亞女性…", True,
         "the exact page the bug produced"),
        ("— Backstory —\nBorn in Marunath…", True, "our layout in another language"),
        ("Ilyn is a member of the Bloodravens, a mercenary company.", False,
         "the game's generated sentence"),
        ("Lahar is a sea captain and former corsair.", False, "authored XML text"),
        ("", False, "an empty page"),
        ("   \n  ", False, "whitespace only"),
        ("—", False, "a lone dash is not a heading"),
    ]
    for text, want, why in cases:
        check(f"{'detects' if want else 'allows'}: {why}",
              is_our_layout(text, zh) is want)

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


def _strip_cs_comments(text):
    """Blank out C# comments, keeping string literals intact.

    Needed for "this symbol is not used" assertions: the docstrings explain *why*
    a call was removed, and naming it there must not read as still calling it.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                if text[j:j + 1] == "\n":
                    break
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


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
