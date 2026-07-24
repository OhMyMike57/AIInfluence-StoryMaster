"""Reusable "pick fields to clear" checklist dialog.

A small modal used by the 摘要 tab's 快速清空 menu (清空屬性 / 清空狀態).  Shows
one checkbox per option (all **unchecked** by default), a 全選 master toggle at
the top, and 取消 / 清空 buttons.  On 清空 it calls ``on_confirm(chosen_keys)``
with the set of selected option keys.

Usage::

    open_clear_checklist(
        app.root, tr("清空屬性"),
        [("romance", tr("浪漫")),
         ("relation", tr("關係"), tr("遊戲將以真實關係值回寫")), ...],
        on_confirm=lambda keys: app._summary_quick_clear("attrs", keys),
    )
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Callable, List, Sequence, Set, Tuple, Union

from i18n import tr
from widgets.window_center import center_window
from ui.theme import tcol

# option = (key, label) or (key, label, hint)
Option = Union[Tuple[str, str], Tuple[str, str, str]]


def open_clear_checklist(parent, title: str, options: Sequence[Option],
                         on_confirm: Callable[[Set[str]], None]) -> None:
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    # Height scales with the option count (each row ~34px + hints).
    hint_rows = sum(1 for o in options if len(o) > 2)
    h = 150 + len(options) * 30 + hint_rows * 16
    center_window(win, 340, min(h, 520))

    ttk.Label(win, text=tr("勾選要清空的欄位（預設全不選）："),
              wraplength=300).pack(anchor="w", padx=12, pady=(12, 4))

    vars_by_key: dict = {}
    all_var = tk.BooleanVar(value=False)

    def _toggle_all():
        for v in vars_by_key.values():
            v.set(all_var.get())

    def _sync_all():
        all_var.set(bool(vars_by_key) and all(v.get() for v in vars_by_key.values()))

    ttk.Checkbutton(win, text=tr("全選"), variable=all_var,
                    command=_toggle_all).pack(anchor="w", padx=14)
    ttk.Separator(win, orient="horizontal").pack(fill="x", padx=12, pady=3)

    for opt in options:
        key, label = opt[0], opt[1]
        hint = opt[2] if len(opt) > 2 else None
        v = tk.BooleanVar(value=False)
        vars_by_key[key] = v
        ttk.Checkbutton(win, text=label, variable=v,
                        command=_sync_all).pack(anchor="w", padx=18)
        if hint:
            ttk.Label(win, text=f"　{hint}", foreground=tcol("#A15C00"),
                      font=("Microsoft JhengHei", 9)).pack(anchor="w", padx=18)

    def _do():
        chosen = {k for k, v in vars_by_key.items() if v.get()}
        if not chosen:
            messagebox.showwarning(title, tr("請至少勾選一個欄位。"), parent=win)
            return
        win.destroy()
        on_confirm(chosen)

    btns = ttk.Frame(win)
    btns.pack(fill=tk.X, padx=12, pady=(10, 10), side=tk.BOTTOM)
    ttk.Button(btns, text=tr("清空"), command=_do,
               style="danger.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(btns, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
