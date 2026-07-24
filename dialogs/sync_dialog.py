"""Sync dialog: copy conversation history entries from source to target characters."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from pathlib import Path
from typing import Any, List

from widgets.conversation_check_list import ConversationCheckList
from i18n import tr
from ui.theme import tcol


def open_sync_dialog(app: Any, srcp: Path, targets: List[Path], ch: list) -> None:
    """Show mode-selection dialog, then launch quick or precise sync."""
    npc_name = app._get_character_name(srcp)
    n_targets = sum(1 for t in targets if t != srcp)

    select_win = tk.Toplevel(app.root)
    select_win.title(tr("選擇同步模式"))
    W, H = 460, 250
    select_win.geometry(f"{W}x{H}")
    select_win.resizable(False, False)
    app._center_window(select_win, W, H)
    select_win.transient(app.root)
    select_win.grab_set()

    ttk.Label(select_win, text=tr("請選擇同步模式"), font=("", 13, "bold")).pack(pady=(16, 4))

    # Source-character hint — previously absent, so users couldn't tell whose
    # dialogue was about to be copied.
    info = ttk.Frame(select_win)
    info.pack(pady=(0, 2))
    ttk.Label(info, text=tr("來源角色："), foreground=tcol("#5A5A5A")).pack(side=tk.LEFT)
    ttk.Label(info, text=npc_name, foreground=tcol("#7B5010"), font=("", 11, "bold")).pack(side=tk.LEFT)
    ttk.Label(
        select_win,
        text=tr("將把此來源角色的對話同步到已選的 {n} 位目標角色。").format(n=n_targets),
        foreground=tcol("#888888"), wraplength=W - 56, justify="center",
    ).pack(padx=28, pady=(0, 6))

    btn_frame = ttk.Frame(select_win)
    btn_frame.pack(pady=(2, 10), fill=tk.X, padx=40)

    def quick_mode():
        select_win.destroy()
        _open_quick_sync(app, srcp, targets, ch)

    def precise_mode():
        select_win.destroy()
        _open_precise_sync(app, srcp, targets, ch)

    ttk.Button(btn_frame, text=tr("快速同步（預設2行）"), command=quick_mode, style="warning.TButton").pack(pady=6, fill=tk.X)
    ttk.Button(btn_frame, text=tr("精準選擇同步（手動勾選）"), command=precise_mode, style="secondary.TButton").pack(pady=6, fill=tk.X)


def _open_quick_sync(app: Any, srcp: Path, targets: List[Path], ch: list) -> None:
    """Ask how many lines to sync, then confirm and execute."""
    ask_win = tk.Toplevel(app.root)
    ask_win.title(tr("快速同步"))
    ask_win.geometry("320x160")
    ask_win.resizable(False, False)
    app._center_window(ask_win, 320, 160)
    ask_win.transient(app.root)
    ask_win.grab_set()

    ttk.Label(ask_win, text=tr("輸入要同步的最近行數")).pack(pady=8)

    num_var = tk.IntVar(value=2)
    entry = ttk.Entry(ask_win, textvariable=num_var, width=12, justify="center")
    entry.pack(pady=5)
    entry.focus_set()

    def confirm():
        try:
            lines = num_var.get()
        except (ValueError, tk.TclError):
            messagebox.showwarning(tr("錯誤"), tr("請輸入有效數字"))
            return
        if lines < 1 or lines > len(ch):
            messagebox.showwarning(tr("錯誤"), tr("行數必須介於 1～{v0}").format(v0=len(ch)))
            return
        ask_win.destroy()
        _do_quick_sync(app, srcp, targets, ch, lines)

    ttk.Button(ask_win, text=tr("確認同步"), command=confirm, style="warning.TButton").pack(pady=10)


def _do_quick_sync(app: Any, srcp: Path, targets: List[Path], ch: list, lines: int) -> None:
    """Execute quick sync after user confirmation."""
    source_plain = app.manual_source.get()
    target_names = [app.path_to_plain.get(t, t.stem) for t in targets if t != srcp]
    if not messagebox.askyesno(
        tr("同步確認"),
        tr("來源：{source_plain}\n將同步 {lines} 行到以下 {v0} 位角色：\n{v1}...").format(source_plain=source_plain, lines=lines, v0=len(target_names), v1=', '.join(target_names)[:250])
    ):
        return
    entries = ch[-lines:]
    ok = sum(1 for t in targets if t != srcp and app._append_to_file(t, entries))
    app.log(tr("已快速同步 {lines} 行對話到 {ok} 位角色").format(lines=lines, ok=ok), "SUCCESS")


def _open_precise_sync(app: Any, srcp: Path, targets: List[Path], ch: list) -> None:
    """Show scrollable conversation list with checkboxes for precise selection."""
    npc_name = app._get_character_name(srcp)

    precise_win = tk.Toplevel(app.root)
    precise_win.title(tr("精準選擇同步（手動勾選）") + tr(" - 來源：{name}").format(name=npc_name))
    precise_win.geometry("1000x700")
    precise_win.minsize(950, 650)
    app._center_window(precise_win, 1000, 700)

    top_frame = ttk.Frame(precise_win)
    top_frame.pack(fill=tk.X, padx=15, pady=10)
    ttk.Label(top_frame, text=tr("操作對象：{name}").format(name=npc_name), font=("", 13, "bold")).pack(side=tk.LEFT)
    ttk.Label(top_frame, text=tr("（將操作對象的對話同步至已選角色）")).pack(side=tk.LEFT, padx=10)

    selected_count_var = tk.StringVar(value=tr("已勾選行數：{checked} / {total}").format(checked=0, total=len(ch)))
    ttk.Label(top_frame, textvariable=selected_count_var).pack(side=tk.LEFT, padx=40)

    def on_count_change(checked: int, total: int):
        selected_count_var.set(tr("已勾選行數：{checked} / {total}").format(checked=checked, total=total))

    quick_btn_frame = ttk.Frame(top_frame)
    quick_btn_frame.pack(side=tk.RIGHT)

    # Default: last 2 entries checked
    default_checked = set(range(max(0, len(ch) - 2), len(ch)))
    checklist = ConversationCheckList(
        precise_win, ch, npc_name,
        default_checked=default_checked,
        on_count_change=on_count_change,
    )
    checklist.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    on_count_change(checklist.checked_count(), checklist.total)

    ttk.Button(quick_btn_frame, text=tr("全選最後10行"), command=lambda: checklist.select_last_n(10), style="secondary.TButton").pack(side=tk.LEFT, padx=3)
    ttk.Button(quick_btn_frame, text=tr("全選最後20行"), command=lambda: checklist.select_last_n(20), style="secondary.TButton").pack(side=tk.LEFT, padx=3)
    ttk.Button(quick_btn_frame, text=tr("全選全部"), command=checklist.select_all, style="secondary.TButton").pack(side=tk.LEFT, padx=3)
    ttk.Button(quick_btn_frame, text=tr("清空選擇"), command=checklist.clear_all, style="secondary.TButton").pack(side=tk.LEFT, padx=3)

    def confirm_precise():
        selected = checklist.checked_entries()
        if not selected:
            messagebox.showwarning(tr("同步"), tr("請至少勾選一行"))
            return
        source_plain = app.manual_source.get()
        target_names = [app.path_to_plain.get(t, t.stem) for t in targets if t != srcp]
        if not messagebox.askyesno(
            tr("最終確認"),
            tr("來源：{source_plain}\n已勾選 {v0} 行\n將同步到以下 {v1} 位角色：\n{v2}...").format(source_plain=source_plain, v0=len(selected), v1=len(target_names), v2=', '.join(target_names)[:200])
        ):
            return
        ok = sum(1 for t in targets if t != srcp and app._append_to_file(t, selected))
        app.log(tr("已精準同步 {v0} 行到 {ok} 位角色").format(v0=len(selected), ok=ok), "SUCCESS")
        precise_win.destroy()

    btn_frame = ttk.Frame(precise_win)
    btn_frame.pack(fill=tk.X, pady=15, padx=20)
    ttk.Button(btn_frame, text=tr("確認同步"), command=confirm_precise, style="warning.TButton").pack(side=tk.RIGHT, padx=10)
    ttk.Button(btn_frame, text=tr("取消"), command=precise_win.destroy, style="secondary.TButton").pack(side=tk.RIGHT, padx=10)
