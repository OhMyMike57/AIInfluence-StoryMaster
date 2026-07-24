"""Gate: no colour options in raw ``tk`` widget constructors.

Under ``ttkbootstrap.Window`` the theme re-applies its own widget defaults while
a tk widget is being instantiated, so colours passed to the *constructor* are
silently discarded::

    tk.Frame(parent, bg="#B8B8B8").cget("bg")   # -> "#ffffff"  (!)
    f = tk.Frame(parent); f.configure(bg="#B8B8B8")   # -> "#B8B8B8"

Nothing errors — the widget simply renders in the surrounding surface colour.
That is how popover-menu separators, the persona editor's drag handles, the
orange pending badges, the toast pill and the "danger" red on menu rows all
ended up invisible or plain, one silent regression at a time.

Rule: build the tk widget, then colour it via ``ui.theme.paint()``.
ttk widgets are exempt — they colour through styles, not the option database.

Run: python scripts/tk_colour_gate.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Widget classes whose constructor colours get eaten.
TK_WIDGETS = {
    "Frame", "Label", "Canvas", "Listbox", "Text", "Checkbutton",
    "Button", "Entry", "Radiobutton", "Toplevel", "Menu", "Scale",
    "Spinbox", "LabelFrame", "Message", "Scrollbar",
}
COLOUR_OPTS = {
    "bg", "fg", "background", "foreground",
    "activebackground", "activeforeground",
    "selectbackground", "selectforeground", "insertbackground",
    "highlightbackground", "highlightcolor", "disabledforeground",
    "readonlybackground", "troughcolor",
}
SKIP_DIRS = {"backups", "build", "dist", "__pycache__", ".git", "venv", ".venv"}


def main() -> int:
    offences: list[str] = []
    scanned = 0
    for path in sorted(ROOT.rglob("*.py")):
        if SKIP_DIRS & set(path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        scanned += 1
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr in TK_WIDGETS):
                continue
            if not (isinstance(fn.value, ast.Name) and fn.value.id == "tk"):
                continue
            bad = sorted({k.arg for k in node.keywords if k.arg in COLOUR_OPTS})
            if bad:
                rel = path.relative_to(ROOT).as_posix()
                offences.append(f"  {rel}:{node.lineno}  tk.{fn.attr}(… {', '.join(bad)}=…)")

    print(f"files scanned            : {scanned}")
    print(f"tk constructor colours   : {len(offences)}")
    if offences:
        print("\nColours passed to a tk widget constructor are dropped under")
        print("ttkbootstrap. Build the widget, then use ui.theme.paint():\n")
        for o in offences:
            print(o)
        print("\n[FAIL] tk colour gate")
        return 1
    print("[PASS] tk colour gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
