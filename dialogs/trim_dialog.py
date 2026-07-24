"""Dialog for trimming (deleting) conversation history entries."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from pathlib import Path
from typing import Any, List

from widgets.conversation_check_list import ConversationCheckList
from i18n import tr


def open_trim_dialog(app: Any, srcp: Path, ch: list) -> None:
    """Show scrollable conversation list with checkboxes for selecting entries to delete."""
    npc_name = app._get_character_name(srcp)

    trim_win = tk.Toplevel(app.root)
    trim_win.title(tr("對話刪減") + tr(" - 來源：{name}").format(name=npc_name))
    trim_win.geometry("1000x700")
    trim_win.minsize(950, 650)
    app._center_window(trim_win, 1000, 700)

    top_frame = ttk.Frame(trim_win)
    top_frame.pack(fill=tk.X, padx=15, pady=10)
    ttk.Label(top_frame, text=tr("操作對象：{name}").format(name=npc_name), font=("", 13, "bold")).pack(side=tk.LEFT)

    selected_count_var = tk.StringVar(value=tr("已勾選刪除行數：{checked} / {total}").format(checked=0, total=len(ch)))
    ttk.Label(top_frame, textvariable=selected_count_var).pack(side=tk.LEFT, padx=40)

    def on_count_change(checked: int, total: int):
        selected_count_var.set(tr("已勾選刪除行數：{checked} / {total}").format(checked=checked, total=total))

    quick_btn_frame = ttk.Frame(top_frame)
    quick_btn_frame.pack(side=tk.RIGHT)

    checklist = ConversationCheckList(
        trim_win, ch, npc_name,
        on_count_change=on_count_change,
    )
    checklist.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    ttk.Button(quick_btn_frame, text=tr("全選全部"), command=checklist.select_all, style="secondary.TButton").pack(side=tk.LEFT, padx=3)
    ttk.Button(quick_btn_frame, text=tr("清空選擇"), command=checklist.clear_all, style="secondary.TButton").pack(side=tk.LEFT, padx=3)

    def confirm_trim():
        selected_indices = checklist.checked_indices()
        if not selected_indices:
            messagebox.showwarning(tr("刪減"), tr("請至少勾選一行要刪除"))
            return
        count = len(selected_indices)
        if not messagebox.askyesno(
            tr("警告！"),
            tr("確定要從「{npc_name}」的對話歷史中\n永久刪除已勾選的 {count} 行嗎？\n此操作無法復原！").format(npc_name=npc_name, count=count)
        ):
            return
        d = app._safe_load_json(srcp) or {}
        new_ch = [ch[i] for i in range(len(ch)) if i not in selected_indices]
        d["ConversationHistory"] = new_ch
        if app.safe_write_json_with_backup(srcp, d):
            app.log(tr("已從 {npc_name} 刪除 {count} 行對話").format(npc_name=npc_name, count=count), "SUCCESS")
        else:
            app.log(tr("刪減失敗：{npc_name}").format(npc_name=npc_name), "ERROR")
        trim_win.destroy()

    btn_frame = ttk.Frame(trim_win)
    btn_frame.pack(fill=tk.X, pady=15, padx=20)
    ttk.Button(btn_frame, text=tr("確認刪除"), command=confirm_trim, style="danger.TButton").pack(side=tk.RIGHT, padx=10)
    ttk.Button(btn_frame, text=tr("取消"), command=trim_win.destroy, style="secondary.TButton").pack(side=tk.RIGHT, padx=10)
