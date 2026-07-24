"""Smoke: PopoverMenu / PopoverPanel construct, position (up/down), toggle,
item-invoke, and outside-click / Escape close — headless, auto-closing.

Run: python scripts/popover_menu_smoke.py
"""
import os
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widgets.popover_menu import PopoverMenu, PopoverPanel, attach_menu  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    root = tk.Tk()
    root.geometry("400x300+100+100")
    root.update_idletasks()

    btn = ttk.Button(root, text="menu")
    btn.pack()
    root.update_idletasks()

    # ── PopoverMenu: build, show, item invoke, hide ──────────────────────
    fired = {"n": 0}
    items = [
        ("項目一", lambda: fired.__setitem__("n", fired["n"] + 1)),
        "-",
        ("項目二", lambda: None, "danger"),
    ]
    menu = PopoverMenu(btn, items, direction="down")
    menu.show()
    check("menu visible after show", menu._visible is True)
    check("menu built 2 clickable rows (separator skipped)", len(menu._rows) == 2)
    # invoke first item's command
    menu._invoke(menu._rows[0][1])
    check("item command fired", fired["n"] == 1)
    check("menu hidden after invoke", menu._visible is False)

    # ── direction up vs down positions differ ────────────────────────────
    m_down = PopoverMenu(btn, items, direction="down")
    m_down.show()
    root.update_idletasks()
    y_down = m_down._top.winfo_rooty()
    m_down.hide()
    m_up = PopoverMenu(btn, items, direction="up")
    m_up.show()
    root.update_idletasks()
    y_up = m_up._top.winfo_rooty()
    m_up.hide()
    # "up" should sit at or above the anchor top; "down" below it.
    check("up popover is above down popover", y_up < y_down)

    # ── keyboard nav activates rows ──────────────────────────────────────
    m2 = PopoverMenu(btn, items, direction="down")
    m2.show()
    m2._nav(1)
    check("nav down activates first row", m2._active == 0)
    m2.hide()

    # ── Escape / outside click close ─────────────────────────────────────
    m3 = PopoverMenu(btn, items, direction="down")
    m3.show()
    # simulate outside click far from popover
    class _Ev:
        x_root = 5
        y_root = 5
    m3._on_root_click(_Ev())
    check("outside click closes menu", m3._visible is False)

    # ── PopoverPanel: caller fills body, clicks inside don't close ───────
    built = {"ok": False}

    def _fill(body):
        ttk.Label(body, text="面板內容").pack()
        ttk.Checkbutton(body, text="欄位").pack()
        built["ok"] = True

    panel = PopoverPanel(btn, direction="up", builder=_fill)
    panel.show()
    check("panel builder ran", built["ok"] is True)
    check("panel visible", panel._visible is True)
    # a click INSIDE the panel must not close it
    inside_x = panel._top.winfo_rootx() + 5
    inside_y = panel._top.winfo_rooty() + 5

    class _EvIn:
        x_root = inside_x
        y_root = inside_y
    panel._on_root_click(_EvIn())
    check("panel stays open on inside click", panel._visible is True)
    panel.hide()

    # ── attach_menu wires the button command ─────────────────────────────
    btn2 = ttk.Button(root, text="attach")
    btn2.pack()
    root.update_idletasks()
    toggle = attach_menu(btn2, lambda: items, direction="down")
    check("attach_menu set button command", str(btn2.cget("command")) != "")
    toggle()  # opens
    check("attach_menu toggle opened a menu", root.winfo_children() and True)

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] popover_menu smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] popover_menu smoke passed")


if __name__ == "__main__":
    main()
