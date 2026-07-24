"""Regression: 自訂對話標籤 (services.dialogue_tag_service).

Built-ins are the editor's own vocabulary: localised, un-deletable, hideable.
Custom tags are the player's words: stored verbatim, never translated, since the
tag is data the AI reads out of the save.

Run: python scripts/dialogue_tag_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from i18n import set_lang  # noqa: E402
from services import dialogue_tag_service as TAGS  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main() -> int:
    print("defaults:")
    cfg = TAGS.normalize(None)
    check("empty settings normalise", cfg == {"custom": [], "hidden": []})
    check("three built-ins are offered", len(TAGS.visible_tags(cfg)) == 3)
    check("built-ins are the tag text, parens included",
          all(t.startswith("(") and t.endswith(")") for t in TAGS.visible_tags(cfg)))

    print("\nlocalisation:")
    set_lang("zh_TW")
    zh = TAGS.builtin_label("scene")
    set_lang("en")
    en = TAGS.builtin_label("scene")
    set_lang("zh_TW")
    check("built-in label follows the editor language", zh != en and bool(zh) and bool(en))
    check("unknown id yields nothing", TAGS.builtin_label("nope") == "")

    print("\ncustom tags:")
    cfg = TAGS.add_custom(cfg, "(戰場觀察)")
    check("custom tag added", "(戰場觀察)" in TAGS.visible_tags(cfg))
    cfg = TAGS.add_custom(cfg, "(戰場觀察)")
    check("adding the same tag twice is a no-op", cfg["custom"].count("(戰場觀察)") == 1)
    cfg = TAGS.add_custom(cfg, "   ")
    check("blank tag rejected", cfg["custom"] == ["(戰場觀察)"])
    cfg = TAGS.add_custom(cfg, TAGS.builtin_label("scene"))
    check("a built-in cannot be re-added as custom", cfg["custom"] == ["(戰場觀察)"])

    print("\nhiding:")
    cfg = TAGS.set_hidden(cfg, "scene", True)
    check("hidden built-in drops out of the menu",
          TAGS.builtin_label("scene") not in TAGS.visible_tags(cfg))
    check("…but is still listed for management",
          any(e["key"] == "scene" and e["hidden"] for e in TAGS.all_entries(cfg)))
    cfg = TAGS.set_hidden(cfg, "scene", False)
    check("unhide restores it", TAGS.builtin_label("scene") in TAGS.visible_tags(cfg))

    print("\nremoval:")
    before = TAGS.remove_custom(cfg, "scene")
    check("removing a built-in leaves it in place",
          TAGS.builtin_label("scene") in TAGS.visible_tags(before))
    cfg = TAGS.remove_custom(cfg, "(戰場觀察)")
    check("custom tag removed", "(戰場觀察)" not in TAGS.visible_tags(cfg))

    print("\nmanagement listing:")
    cfg = TAGS.add_custom(TAGS.normalize(None), "[密探回報]")
    entries = TAGS.all_entries(cfg)
    check("built-ins listed first", [e["builtin"] for e in entries] == [True, True, True, False])
    check("custom entry keyed by its own text", entries[-1]["key"] == "[密探回報]")
    check("built-ins keyed by id, not label",
          [e["key"] for e in entries[:3]] == list(TAGS.BUILTIN_IDS))

    print()
    if FAILS:
        print(f"[FAIL] dialogue tag check: {len(FAILS)} failing")
        return 1
    print("[PASS] dialogue tag check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
