"""Reusable image picker — pick an image file from a campaign's image folders.

A single modal window with a folder tab per image type (記憶圖像 /
事件圖像 / 對話圖像; images are plain files with no type restriction, so any
folder can be used cross-region), a 全部 / 已使用 / 未使用 filter, a file list,
and a click-to-enlarge preview.  Returns the chosen ``Path`` or ``None``.

Usage::

    from widgets.image_picker import open_image_picker
    p = open_image_picker(parent, campaign_dir=cdir, title=tr("選擇圖像"),
                          used_by_folder={"memory_images": used_ids})
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Dict, List, Optional, Set

from i18n import tr
from widgets.image_view import ImageThumbnail
from widgets.window_center import center_window
from ui.theme import tcol

# Sentinel returned when the user chooses "remove image" (unlink from the item,
# distinct from cancelling — which returns None).
PICKER_REMOVE = object()

# (folder name on disk, localized label) — built at call time so the tr()
# literals are visible to the i18n coverage checker (no silent leaks).
def _folders():
    return (
        ("memory_images", tr("記憶圖像")),
        ("event_images", tr("事件圖像")),
        ("dialogue_images", tr("對話圖像")),
    )


class _FolderTab:
    def __init__(self, parent, folder: str, dir_path: Path, used: Set[str],
                 on_double):
        self.folder = folder
        self.dir = dir_path
        self.used = used or set()
        self.all_files: List[Path] = sorted(dir_path.glob("*.png"), key=lambda p: p.name) \
            if dir_path.exists() else []
        self.filtered: List[Path] = []

        self.frame = ttk.Frame(parent)
        self.frame.columnconfigure(0, weight=2, uniform="pick")
        self.frame.columnconfigure(1, weight=3, uniform="pick")
        self.frame.rowconfigure(0, weight=1)

        lf = ttk.Frame(self.frame)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.lb = tk.Listbox(lf, exportselection=False, font=("Microsoft JhengHei", 10))
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.lb.bind("<<ListboxSelect>>", lambda e: self._preview())
        self.lb.bind("<Double-Button-1>", lambda e: on_double())

        self.thumb = ImageThumbnail(self.frame, thumb_size=(360, 200))
        self.thumb.grid(row=0, column=1, sticky="nsew")

    def apply_filter(self, mode: str) -> None:
        top = self.lb.yview()[0]
        self.lb.delete(0, tk.END)
        self.filtered = []
        for p in self.all_files:
            if mode == "used" and p.stem not in self.used:
                continue
            if mode == "unused" and p.stem in self.used:
                continue
            self.filtered.append(p)
            mark = "● " if p.stem in self.used else "○ "
            self.lb.insert(tk.END, mark + p.name)
        self.lb.yview_moveto(top)
        self._preview()

    def selected(self) -> Optional[Path]:
        s = self.lb.curselection()
        return self.filtered[s[0]] if s and s[0] < len(self.filtered) else None

    def _preview(self) -> None:
        p = self.selected()
        self.thumb.load(p if p else None)


def open_image_picker(parent, *, campaign_dir, title: str,
                      select_label: Optional[str] = None,
                      used_by_folder: Optional[Dict[str, Set[str]]] = None,
                      initial_filter: str = "all",
                      allow_remove: bool = False,
                      ):
    """Return the chosen ``Path``, ``None`` (cancelled), or ``PICKER_REMOVE``
    (user chose 移除圖像; only offered when *allow_remove*)."""
    cdir = Path(campaign_dir) if campaign_dir else None
    used_by_folder = used_by_folder or {}
    if initial_filter not in ("all", "used", "unused"):
        initial_filter = "all"

    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent.winfo_toplevel())
    win.grab_set()
    W, H = 760, 520
    center_window(win, W, H)

    # ── Filter row (● 已使用 / ○ 未使用 markers explained inline) ──
    fbar = ttk.Frame(win)
    fbar.pack(fill=tk.X, padx=10, pady=(10, 4))
    ttk.Label(fbar, text=tr("篩選：")).pack(side=tk.LEFT)
    mode_var = tk.StringVar(value=initial_filter)
    for val, label in (("all", tr("全部")), ("used", tr("已使用")), ("unused", tr("未使用"))):
        ttk.Radiobutton(fbar, text=label, value=val, variable=mode_var).pack(side=tk.LEFT, padx=4)
    ttk.Label(fbar, text=tr("（● 已使用　○ 未使用）"), foreground=tcol("#888888")).pack(side=tk.LEFT, padx=(10, 0))

    result: Dict[str, Optional[Path]] = {"path": None}

    def _accept():
        tab = tabs[nb.index(nb.select())]
        p = tab.selected()
        if p is not None:
            result["path"] = p
            win.destroy()

    nb = ttk.Notebook(win)
    nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
    tabs: List[_FolderTab] = []
    for folder, label in _folders():
        dpath = (cdir / folder) if cdir else Path(folder)
        tab = _FolderTab(nb, folder, dpath, used_by_folder.get(folder, set()), _accept)
        nb.add(tab.frame, text=label)
        tabs.append(tab)

    def _refilter(*_):
        for t in tabs:
            t.apply_filter(mode_var.get())
    mode_var.trace_add("write", _refilter)
    _refilter()

    def _remove():
        result["path"] = PICKER_REMOVE
        win.destroy()

    btns = ttk.Frame(win)
    btns.pack(fill=tk.X, padx=10, pady=(0, 10))
    ttk.Button(btns, text=select_label or tr("選取"), command=_accept,
               style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(btns, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
    if allow_remove:
        ttk.Button(btns, text=tr("🚫 移除圖像（不使用）"), command=_remove,
                   style="danger.TButton").pack(side=tk.LEFT, padx=4)

    win.wait_window()
    return result["path"]
