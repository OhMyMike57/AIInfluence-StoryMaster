"""管理自訂對話標籤 — add / remove / hide the speaker-position tags.

Reachable from the 說話者 field's 快速設定 → 自訂標籤 submenu and from
設定 → 偏好設定, because it is both a per-write convenience and a preference.

Built-ins are listed but not removable: they are the editor's own vocabulary and
are written in the running language, so "deleting" one would only mean the user
never wants to see it — which is what 隱藏 does.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from i18n import tr
from services import dialogue_tag_service as TAGS
from ui import msgbox as messagebox
from ui.theme import tcol
from widgets.window_center import center_window


def open_dialogue_tag_dialog(app, on_saved=None) -> None:
    win = tk.Toplevel(app.root)
    win.title(tr("管理自訂對話標籤"))
    win.transient(app.root)
    win.grab_set()
    center_window(win, 760, 560)

    ttk.Label(win, text=tr("對話標籤會寫在說話者的位置，讓 AI 把該行讀成情境而非某人說的話。"),
              wraplength=520, justify="left",
              foreground=tcol("#5A5A5A")).pack(anchor="w", padx=12, pady=(12, 2))
    ttk.Label(win, text=tr("內建標籤會隨編輯器語言顯示對應語言的文字，不可刪除，但可隱藏；"
                           "自訂標籤則原樣寫入。"),
              wraplength=520, justify="left",
              foreground=tcol("#9AA0A6")).pack(anchor="w", padx=12, pady=(0, 8))

    body = ttk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=12)
    cols = ("label", "kind", "shown")
    tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse")
    for c, txt, w in (("label", tr("標籤"), 240), ("kind", tr("類型"), 100),
                      ("shown", tr("顯示"), 80)):
        tree.heading(c, text=txt)
        tree.column(c, width=w, anchor="w")
    vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    state = {"cfg": TAGS.normalize(app.settings.get(TAGS.SETTINGS_KEY))}
    row_keys = {}

    def _reload():
        tree.delete(*tree.get_children())
        row_keys.clear()
        for entry in TAGS.all_entries(state["cfg"]):
            iid = f"tag::{entry['key']}"
            tree.insert("", "end", iid=iid, values=(
                entry["label"],
                tr("內建") if entry["builtin"] else tr("自訂"),
                tr("隱藏") if entry["hidden"] else tr("顯示中"),
            ))
            row_keys[iid] = entry
        _refresh_buttons()

    def _selected():
        sel = tree.selection()
        return row_keys.get(sel[0]) if sel else None

    # ── add ──
    add_row = ttk.Frame(win)
    add_row.pack(fill=tk.X, padx=12, pady=(8, 2))
    ttk.Label(add_row, text=tr("新增標籤:")).pack(side=tk.LEFT)
    new_var = tk.StringVar()
    ttk.Entry(add_row, textvariable=new_var, width=28).pack(side=tk.LEFT, padx=(4, 6))
    ttk.Label(add_row, text=tr("（例如 (戰場觀察) 或 [密探回報]）"),
              foreground=tcol("#9AA0A6")).pack(side=tk.LEFT)


    def _add():
        label = new_var.get().strip()
        if not label:
            return
        before = len(TAGS.normalize(state["cfg"])["custom"])
        state["cfg"] = TAGS.add_custom(state["cfg"], label)
        if len(state["cfg"]["custom"]) == before:
            messagebox.showinfo(tr("新增標籤"), tr("這個標籤已經存在。"), parent=win)
            return
        new_var.set("")
        _reload()

    # ── row actions — 新增 sits with the other two so all the buttons that
    # change the list live in one row ──
    act = ttk.Frame(win)
    act.pack(fill=tk.X, padx=12, pady=(6, 2))
    ttk.Button(act, text=tr("新增"), command=_add,
               style="success.TButton").pack(side=tk.LEFT)

    def _toggle_hidden():
        entry = _selected()
        if not entry:
            return
        state["cfg"] = TAGS.set_hidden(state["cfg"], entry["key"], not entry["hidden"])
        _reload()

    def _remove():
        entry = _selected()
        if not entry or entry["builtin"]:
            return
        if not messagebox.askyesno(
                tr("移除標籤"),
                tr("確定移除自訂標籤「{label}」嗎？").format(label=entry["label"]),
                parent=win):
            return
        state["cfg"] = TAGS.remove_custom(state["cfg"], entry["key"])
        _reload()

    hide_btn = ttk.Button(act, text=tr("隱藏／顯示"), command=_toggle_hidden,
                          style="secondary.TButton")
    hide_btn.pack(side=tk.LEFT, padx=(6, 0))
    del_btn = ttk.Button(act, text=tr("🗑 移除"), command=_remove, style="danger.TButton")
    del_btn.pack(side=tk.LEFT, padx=(6, 0))
    note = ttk.Label(act, text="", foreground=tcol("#9AA0A6"))
    note.pack(side=tk.LEFT, padx=(10, 0))

    def _refresh_buttons(*_a):
        entry = _selected()
        hide_btn.configure(state="normal" if entry else "disabled")
        del_btn.configure(state="normal" if (entry and not entry["builtin"]) else "disabled")
        note.configure(text=tr("內建標籤不可移除，可改為隱藏") if (entry and entry["builtin"]) else "")

    tree.bind("<<TreeviewSelect>>", _refresh_buttons)

    # ── save / cancel ──
    foot = ttk.Frame(win)
    foot.pack(fill=tk.X, padx=12, pady=(8, 12))

    def _save():
        app.settings[TAGS.SETTINGS_KEY] = TAGS.normalize(state["cfg"])
        try:
            app.save_settings()
        except Exception:
            pass
        win.destroy()
        if callable(on_saved):
            on_saved()

    ttk.Button(foot, text=tr("儲存"), command=_save,
               style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(foot, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)

    _reload()
