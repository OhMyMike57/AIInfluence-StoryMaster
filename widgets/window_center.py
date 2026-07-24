"""Center a Toplevel on screen.

Shared helper so every dialog centers consistently (a recurring miss when
dialogs are created with a bare ``geometry("WxH")`` and no offset — they land
at the top-left).  Mirrors ``StoryMaster._center_window`` so widgets
that don't hold an ``app`` reference can still center themselves.
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
