"""Regression for services.companion_mod_service (v1.1.0 module-primary model).

Since the transformation the editor no longer installs the module — the service
is a pure status check: is the core module present in the game's Modules folder,
and does its version match this (same-version-bundled) editor?

Covers:
  1. parse_version / compare_versions — numeric ordering, 'v' prefix, None.
  2. module_status — every state (no_game / not_installed / version_match /
     version_mismatch), including the ``ok`` convenience property.

All in a temp sandbox; touches no real game install.  Exit 0 + [PASS] on success.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import services.companion_mod_service as cm

errors: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "  FAIL") + " - " + label)
    if not cond:
        errors.append(label)


# ── 1. version helpers ───────────────────────────────────────────────────────
print("version helpers:")
check(cm.parse_version("v1.2.3") == (1, 2, 3), "parse with v prefix")
check(cm.parse_version("1.10") == (1, 10), "parse two-part")
check(cm.parse_version(None) == (0,), "parse None")
check(cm.compare_versions("1.1.0", "1.1.0") == 0, "equal")
check(cm.compare_versions("1.2", "1.1.9") > 0, "1.2 > 1.1.9")
check(cm.compare_versions("v1.1", "1.1.0") == 0, "v1.1 == 1.1.0 (padded)")
check(cm.compare_versions(None, "1.0") < 0, "None < 1.0")

# ── 2. module_status ─────────────────────────────────────────────────────────
print("\nmodule_status:")
st = cm.module_status(None, "1.1.0")
check(st.state == "no_game" and not st.ok, "no game dir")

with tempfile.TemporaryDirectory() as td:
    game = Path(td)
    (game / "Modules").mkdir()

    st = cm.module_status(game, "1.1.0")
    check(st.state == "not_installed" and not st.ok, "module folder absent")
    check(st.module_dir == game / "Modules" / cm.MOD_ID, "target dir resolved")
    check(st.editor == "1.1.0", "editor version carried")

    mod_dir = game / "Modules" / cm.MOD_ID
    mod_dir.mkdir()
    (mod_dir / cm.VERSION_FILE).write_text("1.1.0\n", encoding="utf-8")
    st = cm.module_status(game, "1.1.0")
    check(st.state == "version_match" and st.ok, "same version matches")
    check(st.installed == "1.1.0", "installed version read")

    (mod_dir / cm.VERSION_FILE).write_text("1.0.0\n", encoding="utf-8")
    st = cm.module_status(game, "1.1.0")
    check(st.state == "version_mismatch" and not st.ok, "older module mismatches")

    (mod_dir / cm.VERSION_FILE).write_text("v1.1.0\n", encoding="utf-8")
    st = cm.module_status(game, "1.1.0")
    check(st.state == "version_match", "v-prefixed version still matches")

    (mod_dir / cm.VERSION_FILE).unlink()
    st = cm.module_status(game, "1.1.0")
    check(st.state == "not_installed", "folder without version file = not installed")

print()
if errors:
    print(f"[FAIL] companion_mod_service check: {len(errors)} failing")
    sys.exit(1)
print("[PASS] companion_mod_service check passed")
