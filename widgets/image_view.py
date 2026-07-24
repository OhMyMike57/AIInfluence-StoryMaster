"""Pillow-backed image thumbnail with click-to-enlarge and graceful fallbacks.

Shows a scaled thumbnail of an image file; clicking it opens a larger view in a
Toplevel.  Missing files show a placeholder, and if Pillow is unavailable the
widget degrades to a text note instead of crashing.  PhotoImage references are
kept alive on the instance (Tk would otherwise garbage-collect them and show
blank images).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional, Tuple

from i18n import tr
from widgets.window_center import center_window
from ui.theme import tcol

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except Exception:  # pragma: no cover - environment without Pillow
    _PIL_OK = False


def pillow_available() -> bool:
    return _PIL_OK


class ImageThumbnail(ttk.Frame):
    """A clickable image thumbnail (click → enlarged Toplevel)."""

    def __init__(self, parent, *, thumb_size: Tuple[int, int] = (240, 135),
                 max_view: Tuple[int, int] = (1100, 760),
                 placeholder: Optional[str] = None, **kw):
        super().__init__(parent, **kw)
        self._thumb_size = thumb_size
        self._max_view = max_view
        self._placeholder = placeholder or tr("（無圖像）")
        self._path: Optional[Path] = None
        self._img = None  # keep a reference so Tk doesn't GC it

        self._label = ttk.Label(self, anchor="center", cursor="hand2",
                                foreground=tcol("#999999"), justify="center")
        self._label.pack(fill=tk.BOTH, expand=True)
        self._label.bind("<Button-1>", lambda e: self._enlarge())
        self.clear()

    # ── public API ────────────────────────────────────────────────────
    def load(self, path) -> None:
        self._path = Path(path) if path else None
        self._render()

    def clear(self) -> None:
        self._path = None
        self._img = None
        self._label.configure(image="", text=self._placeholder, foreground=tcol("#999999"))

    def has_image(self) -> bool:
        return self._path is not None and self._path.exists() and _PIL_OK

    # ── internals ─────────────────────────────────────────────────────
    def _note(self, text: str, color: str = tcol("#999999")) -> None:
        self._img = None
        self._label.configure(image="", text=text, foreground=color)

    def _render(self) -> None:
        if self._path is None:
            self._note(self._placeholder)
            return
        if not _PIL_OK:
            self._note(tr("（需安裝 Pillow 才能顯示圖像）"))
            return
        if not self._path.exists():
            self._note(self._placeholder)
            return
        try:
            im = Image.open(self._path)
            im.thumbnail(self._thumb_size)
            self._img = ImageTk.PhotoImage(im)
            self._label.configure(image=self._img, text="")
        except Exception:
            self._note(tr("（圖像讀取失敗）"), color=tcol("#C0392B"))

    def _enlarge(self) -> None:
        if not self.has_image():
            return
        try:
            im = Image.open(self._path)
            im.thumbnail(self._max_view)
            ph = ImageTk.PhotoImage(im)
        except Exception:
            return
        top = tk.Toplevel(self)
        top.title(self._path.name)
        top.transient(self.winfo_toplevel())
        lbl = ttk.Label(top, image=ph, cursor="hand2")
        lbl.image = ph  # keep ref on the toplevel's label
        lbl.pack()
        ttk.Label(top, text=tr("點擊圖片或按 Esc 關閉"),
                  foreground=tcol("#888888")).pack(pady=(2, 6))
        top.bind("<Escape>", lambda e: top.destroy())
        lbl.bind("<Button-1>", lambda e: top.destroy())
        center_window(top, ph.width() + 20, ph.height() + 40)
