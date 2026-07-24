"""Headless smoke for ui/msgbox — verifies the tkinter-compatible return-value
contract, Esc/cancel semantics, the long-text mode, and dark-mode icon colour,
all without entering the event loop (via msgbox._test_hook)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter as tk
from ui import msgbox
from ui import theme


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _find(widget, cls):
    if isinstance(widget, cls):
        return widget
    for ch in widget.winfo_children():
        got = _find(ch, cls)
        if got is not None:
            return got
    return None


def main():
    root = tk.Tk()
    root.withdraw()

    # ── return-value contract: confirm button ─────────────────────────────
    msgbox._test_hook = lambda d: d._confirm_btn.invoke()
    expect(msgbox.showinfo("t", "m", parent=root) == "ok", "showinfo -> ok")
    expect(msgbox.showwarning("t", "m", parent=root) == "ok", "showwarning -> ok")
    expect(msgbox.showerror("t", "m", parent=root) == "ok", "showerror -> ok")
    expect(msgbox.askyesno("t", "m", parent=root) is True, "askyesno confirm -> True")
    expect(msgbox.askokcancel("t", "m", parent=root) is True, "askokcancel confirm -> True")

    # ── contract: Esc / ✕ (default result) ────────────────────────────────
    msgbox._test_hook = lambda d: d._on_escape()
    expect(msgbox.showinfo("t", "m", parent=root) == "ok", "showinfo esc -> ok")
    expect(msgbox.askyesno("t", "m", parent=root) is False, "askyesno esc -> False")
    expect(msgbox.askokcancel("t", "m", parent=root) is False, "askokcancel esc -> False")
    expect(msgbox.askstring("t", "p", parent=root) is None, "askstring esc -> None")

    # ── askstring: confirm returns entry text ─────────────────────────────
    def _type_confirm(d):
        d._entry_widget.insert(0, "Hello")
        d._confirm_btn.invoke()
    msgbox._test_hook = _type_confirm
    expect(msgbox.askstring("t", "p", parent=root) == "Hello", "askstring confirm -> entry text")

    # ── askstring: initialvalue preserved on confirm ──────────────────────
    msgbox._test_hook = lambda d: d._confirm_btn.invoke()
    expect(msgbox.askstring("t", "p", parent=root, initialvalue="Pre") == "Pre",
           "askstring initialvalue -> returned")

    msgbox._test_hook = None

    # ── structure: long text switches to a scrolling Text ─────────────────
    expect(msgbox._long("x" * 1300) is True, "long by chars")
    expect(msgbox._long("\n".join("l" for _ in range(20))) is True, "long by lines")
    expect(msgbox._long("short") is False, "short stays Label")
    d = msgbox._MessageDialog(root, "info", "t", "L\n" * 30,
                              [("確定", "ok", True)], "ok")
    expect(_find(d.win, tk.Text) is not None, "long message uses a Text widget")
    d.win.destroy()

    # ── short message uses a Label, focus on confirm ──────────────────────
    d = msgbox._MessageDialog(root, "info", "t", "hi", [("確定", "ok", True)], "ok")
    expect(_find(d.win, tk.Text) is None, "short message has no Text")
    d.win.destroy()

    # ── dark-mode icon colour goes through tcol ───────────────────────────
    theme.set_mode("dark")
    d = msgbox._MessageDialog(root, "warning", "t", "m", [("確定", "ok", True)], "ok")
    lbl = None
    for ch in _iter(d.win):
        if isinstance(ch, __import__("tkinter").ttk.Label) and str(ch.cget("text")) == "⚠":
            lbl = ch
            break
    expect(lbl is not None, "warning icon label found")
    expect(str(lbl.cget("foreground")) == theme.tcol("#B5852E"),
           "dark icon colour mapped via tcol (%s)" % lbl.cget("foreground"))
    d.win.destroy()
    theme.set_mode("light")

    root.destroy()
    print("[PASS] msgbox smoke passed")


def _iter(widget):
    yield widget
    for ch in widget.winfo_children():
        yield from _iter(ch)


if __name__ == "__main__":
    main()
