"""Gatekeeper: no native tkinter messagebox / simpledialog anywhere but
``ui/msgbox.py`` (v0.40.0).

Since v0.40.0 every dialog goes through ``ui.msgbox`` (themed + localized
buttons).  ``ui/msgbox.py`` itself is the only place allowed to import the
native ``messagebox`` / ``simpledialog`` — as a last-resort fallback when no Tk
root exists yet.  ``filedialog`` is exempt (the OS file picker is correct UX).

Fails (non-zero) if any other in-scope file imports native messagebox or
simpledialog, so a future edit can't silently reintroduce an untranslated,
unthemed OS dialog.
"""
from __future__ import annotations

import ast
import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_TOP = {"i18n", "scripts", "build", "dist", "data_samples", "__pycache__",
               ".git", ".venv", "venv"}
INCLUDE_TOP = {"ui", "widgets", "dialogs", "controllers", "services"}
ENTRY_FILE = "StoryMaster.py"
ALLOWED = {"ui/msgbox.py"}          # the one sanctioned native fallback
BANNED = {"messagebox", "simpledialog"}


def _in_scope(rel: str) -> bool:
    return rel == ENTRY_FILE or rel.split("/", 1)[0] in INCLUDE_TOP


def scan(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "tkinter":
            for a in node.names:
                if a.name in BANNED:
                    hits.append(f"L{node.lineno}: from tkinter import {a.name}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name in {f"tkinter.{b}" for b in BANNED}:
                    hits.append(f"L{node.lineno}: import {a.name}")
    return hits


def main() -> int:
    findings = {}
    for f in glob.glob(str(ROOT / "**" / "*.py"), recursive=True):
        rel = Path(f).relative_to(ROOT).as_posix()
        if rel.split("/", 1)[0] in EXCLUDE_TOP or not _in_scope(rel) or rel in ALLOWED:
            continue
        hits = scan(Path(f))
        if hits:
            findings[rel] = hits
    total = sum(len(v) for v in findings.values())
    print(f"files with native messagebox/simpledialog : {len(findings)}")
    for rel in sorted(findings):
        for h in findings[rel]:
            print(f"  {rel}: {h}")
    if total:
        print(f"[FAIL] {total} native dialog import(s) — use `from ui import msgbox`")
        return 1
    print("[PASS] no native messagebox/simpledialog outside ui/msgbox.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
