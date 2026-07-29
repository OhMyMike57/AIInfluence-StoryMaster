"""Center a Toplevel.

Shared helper so every dialog centers consistently (a recurring miss when
dialogs are created with a bare ``geometry("WxH")`` and no offset — they land
at the top-left).

Two variants:

* :func:`center_over_parent` — centers on the *main window*. Prefer this.
  ``winfo_screenwidth()`` reports the whole virtual desktop on a multi-monitor
  setup, so screen-centring can drop a dialog on a monitor edge (or between two
  screens). The app window is always on the monitor the user is looking at.
* :func:`center_window` — screen-centring. Mirrors ``StoryMaster._center_window``;
  kept for the dialogs already using it and for callers with no parent handy.
"""
from __future__ import annotations

import tkinter as tk


def center_window(win: tk.Misc, width: int = None, height: int = None) -> None:
    win.update_idletasks()
    if width is None:
        width = win.winfo_width()
    if height is None:
        height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2) - 30
    win.geometry(f"{width}x{height}+{x}+{y}")


def center_over_parent(win: tk.Misc, parent: tk.Misc,
                       width: int = None, height: int = None) -> None:
    """Center *win* over *parent*, clamped to fit on screen."""
    win.update_idletasks()
    if width is None:
        width = win.winfo_width()
    if height is None:
        height = win.winfo_height()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        if pw <= 1:                     # not mapped yet — fall back to the screen
            raise tk.TclError
    except tk.TclError:
        px = py = 0
        pw, ph = win.winfo_screenwidth(), win.winfo_screenheight()
    width = min(width, win.winfo_screenwidth() - 40)
    height = min(height, win.winfo_screenheight() - 80)
    x = max(0, px + (pw - width) // 2)
    y = max(0, py + (ph - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")
