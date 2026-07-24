"""Non-intrusive toast bubble (auto-dismissing notification).

A small borderless Toplevel that appears near a widget, shows a short message,
and disappears after a few seconds without stealing focus or blocking input.
Used for "copied to clipboard" / "exported" confirmations.
"""
from __future__ import annotations

import tkinter as tk
from ui.theme import paint, tcol


def show_toast(widget, text: str, ms: int = 2500) -> None:
    """Show *text* as a toast near *widget* for *ms* milliseconds."""
    try:
        top = tk.Toplevel(widget)
        top.wm_overrideredirect(True)
        try:
            top.wm_attributes("-topmost", True)
        except tk.TclError:
            pass

        frame = paint(tk.Frame(top, bd=0, highlightthickness=1),
                      bg=tcol("#2E2E2E"), highlightbackground=tcol("#111111"))
        frame.pack(fill="both", expand=True)
        paint(tk.Label(frame, text=text, font=("Microsoft JhengHei", 10),
                       padx=14, pady=8),
              bg=tcol("#2E2E2E"), fg=tcol("#FFFFFF")).pack()

        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        # Position: centered horizontally over the widget, near its bottom.
        try:
            wx = widget.winfo_rootx() + (widget.winfo_width() - w) // 2
            wy = widget.winfo_rooty() + widget.winfo_height() - h - 24
        except tk.TclError:
            wx = widget.winfo_pointerx() - w // 2
            wy = widget.winfo_pointery() + 16
        top.wm_geometry(f"{w}x{h}+{max(0, wx)}+{max(0, wy)}")

        top.after(ms, top.destroy)
    except Exception:
        pass  # a toast must never break the action it accompanies
