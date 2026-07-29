"""Regression: the module's own localisation is complete.

Every ``{=id}Fallback`` the C# source uses must exist in both language XMLs.
A missing id is silent at runtime — MCM just renders the English fallback — so
without this check a new setting reaches players untranslated.

Run: python scripts/mod_localization_check.py
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = ROOT / "mod" / "src"
LANGS = {
    "CNt": ROOT / "mod" / "ModuleData" / "Languages" / "CNt" / "strings_CNt.xml",
    "CNs": ROOT / "mod" / "ModuleData" / "Languages" / "CNs" / "strings_CNs.xml",
}

# Keys live inside C# string literals as "{=SomeId}fallback text".
STRING_RE = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
KEY_RE = re.compile(r"\{=([A-Za-z0-9_]+)\}")


def strip_comments(text):
    """Blank out C# comments, keeping string literals intact.

    Needed because the source documents the convention with a *quoted example*
    inside a doc comment — ``("{=id}English fallback")`` — which any literal scan
    on raw text happily reports as a real, untranslated key.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':                                  # string literal: copy whole
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                if text[j:j + 1] == "\n":
                    break
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
        elif c == "'":                                # char literal
            j = i + 1
            while j < n and text[j] != "'":
                j += 2 if text[j] == "\\" else 1
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


def keys_in(text):
    """Every {=id} appearing inside a string literal in real code."""
    out = []
    for lit in STRING_RE.finditer(strip_comments(text)):
        out.extend(KEY_RE.findall(lit.group(1)))
    return out

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    used = {}
    for cs in SRC.rglob("*.cs"):
        text = cs.read_text(encoding="utf-8", errors="replace")
        for key in keys_in(text):
            used.setdefault(key, set()).add(cs.name)
    print(f"keyed strings used in C#: {len(used)}")

    for name, path in LANGS.items():
        print(f"\n[{name}]")
        if not path.is_file():
            check(f"{name}: file exists", False)
            continue
        raw = path.read_text(encoding="utf-8")
        try:
            tree = ET.fromstring(raw)
        except ET.ParseError as exc:
            check(f"{name}: well-formed XML ({exc})", False)
            continue
        check(f"{name}: well-formed XML", True)

        ids = [e.get("id") for e in tree.iter("string")]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        check(f"{name}: no duplicate ids" + (f" — {dupes}" if dupes else ""), not dupes)

        have = set(ids)
        missing = sorted(k for k in used if k not in have)
        check(f"{name}: every C# key translated"
              + (f" — missing {len(missing)}: {missing[:6]}" if missing else ""),
              not missing)

        empty = sorted(e.get("id") for e in tree.iter("string")
                       if not (e.get("text") or "").strip())
        check(f"{name}: no empty text" + (f" — {empty}" if empty else ""), not empty)

        # A {COUNT} the code substitutes must survive translation, or the number
        # silently never appears in the message.
        for sid in sorted(used):
            if "{COUNT}" not in _fallback_for(sid):
                continue
            node = next((e for e in tree.iter("string") if e.get("id") == sid), None)
            if node is None:
                continue
            check(f"{name}: {sid} keeps {{COUNT}}",
                  "{COUNT}" in (node.get("text") or ""))

    unused = sorted(set().union(*[{e.get("id") for e in ET.fromstring(
        p.read_text(encoding='utf-8')).iter("string")}
        for p in LANGS.values() if p.is_file()]) - set(used))
    if unused:
        print(f"\nnote: {len(unused)} translated id(s) not referenced in C# "
              f"(harmless leftovers): {unused[:8]}")

    if FAILS:
        print(f"\n[FAIL] {len(FAILS)} check(s) failed")
        sys.exit(1)
    print("\n[PASS] module localisation check passed")


_FALLBACK_CACHE = {}


def _fallback_for(sid):
    """The English fallback written inline in the C# for *sid*."""
    if not _FALLBACK_CACHE:
        pat = re.compile(r"\{=([A-Za-z0-9_]+)\}(.*)", re.S)
        for cs in SRC.rglob("*.cs"):
            text = strip_comments(cs.read_text(encoding="utf-8", errors="replace"))
            for lit in STRING_RE.finditer(text):
                m = pat.match(lit.group(1))
                if m:
                    _FALLBACK_CACHE.setdefault(m.group(1), m.group(2))
    return _FALLBACK_CACHE.get(sid, "")


if __name__ == "__main__":
    main()
