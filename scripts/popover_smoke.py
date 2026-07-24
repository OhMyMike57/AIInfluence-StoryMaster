"""Smoke: PopoverMenu / PopoverPanel open-close lifecycle (v0.37.0).

Covers the auto-close paths added in v0.37.0 — focus leaving the app
(Alt+Tab), focus moving to a sibling vs. an inner child, and the main window
being moved/resized — plus the descendant path-string check.  Headless
(withdrawn root, focus_get monkeypatched since real focus transitions can't be
driven without a visible window).

Run: python scripts/popover_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widgets.popover_menu import PopoverMenu, PopoverPanel  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    root = tk.Tk()
    root.withdraw()
    btn = tk.Button(root, text="x")
    btn.pack()
    root.update_idletasks()

    m = PopoverMenu(btn, [("A", lambda: None), None, ("B", lambda: None, "danger")])

    # Alt+Tab / another app takes focus → focus_get() is None → close.
    m.show()
    check("show binds a <Configure> watcher", m._visible and m._cfg_bind_id is not None)
    m._top.focus_get = lambda: None
    m._on_focus_out(None)
    check("focus leaving the app hides the popover", not m._visible)

    # Focus moves to a sibling widget in the same app → close.
    m.show()
    m._top.focus_get = lambda: btn
    m._on_focus_out(None)
    check("focus to a sibling widget hides the popover", not m._visible)

    # Focus moves to a widget inside the popover → stay open.
    m.show()
    child = tk.Frame(m._top)
    m._top.focus_get = lambda c=child: c
    m._on_focus_out(None)
    check("focus to an inner child keeps the popover open", m._visible)
    m.hide()

    # Main window move/resize closes; an inner widget's <Configure> does not.
    m.show()

    class _Child:
        widget = btn

    m._on_root_configure(_Child())
    check("inner-widget <Configure> does not hide", m._visible)

    class _Root:
        widget = root

    m._on_root_configure(_Root())
    check("root window move/resize hides", not m._visible)

    # Descendant path-string check (PopoverPanel keeps inner clicks open).
    p = PopoverPanel(btn, direction="up")
    p.build(lambda b: tk.Checkbutton(b).pack())
    p.show()
    inner = tk.Label(p._top)
    check("inner widget is a descendant", p._is_descendant(inner) is True)
    check("root is not a descendant", p._is_descendant(root) is False)
    p.hide()

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] popover smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] popover smoke passed")


if __name__ == "__main__":
    main()
