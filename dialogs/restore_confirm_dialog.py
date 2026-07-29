"""Restore-confirmation dialog for the Backup Center.

Restoring mirrors a backup over live data — files the backup does not have are
removed — so this is the one place in the tool where a confirmation has to be
more than a yes/no. It shows the *plan* (:func:`services.backup_service.plan_restore`):
what would be added, overwritten and deleted, with example paths, before
anything is written.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from i18n import tr
from services import backup_service as bks
from ui.theme import tcol
from widgets.window_center import center_over_parent

_W, _H = 720, 620


def _kind_label(kind: str) -> str:
    """Localised name of a backup kind (literal ``tr()`` calls — no tr(variable))."""
    if kind == bks.KIND_CAMPAIGN:
        return tr("戰役備份")
    if kind == bks.KIND_DB:
        return tr("資料庫備份")
    if kind == bks.KIND_CONFIG:
        return tr("工具設定備份")
    if kind == bks.KIND_SNAPSHOT:
        return tr("存檔備份（save_snapshots）")
    return kind


def open_restore_confirm_dialog(app, plan: "bks.RestorePlan") -> bool:
    """Show *plan* and return True when the user confirms the restore."""
    win = tk.Toplevel(app.root)
    win.title(tr("還原備份"))
    win.geometry(f"{_W}x{_H}")
    win.transient(app.root)
    center_over_parent(win, app.root, _W, _H)

    result = {"ok": False}

    # ── Header: what, from where, to where ───────────────────────────────
    head = ttk.Frame(win)
    head.pack(fill=tk.X, padx=14, pady=(14, 6))
    ttk.Label(head, text=tr("即將把這份備份還原回原本的位置："),
              font=("", 11, "bold")).pack(anchor="w")

    grid = ttk.Frame(win)
    grid.pack(fill=tk.X, padx=14, pady=(2, 8))
    grid.columnconfigure(1, weight=1)
    when = plan.entry.timestamp.strftime("%Y-%m-%d %H:%M:%S") if plan.entry.timestamp else "—"
    rows = [
        (tr("備份名稱"), plan.entry.name),
        (tr("類型"), _kind_label(plan.entry.kind)),
        (tr("備份時間"), when),
        (tr("還原目標"), str(plan.target)),
    ]
    for r, (k, v) in enumerate(rows):
        ttk.Label(grid, text=k + "：").grid(row=r, column=0, sticky="w", pady=1)
        ttk.Label(grid, text=v, wraplength=_W - 160, justify="left").grid(
            row=r, column=1, sticky="w", pady=1)

    # ── The plan ─────────────────────────────────────────────────────────
    ttk.Separator(win, orient="horizontal").pack(fill=tk.X, padx=14, pady=6)

    counts = ttk.Frame(win)
    counts.pack(fill=tk.X, padx=14)
    ttk.Label(counts, text=tr("這次還原會："), font=("", 10, "bold")).pack(anchor="w")

    def _count_row(text: str, colour: str) -> None:
        lbl = ttk.Label(counts, text=text)
        lbl.pack(anchor="w", padx=(12, 0))
        lbl.configure(foreground=tcol(colour))

    _count_row(tr("新增 {n} 個檔案").format(n=len(plan.added)), "#1A7A3F")
    _count_row(tr("覆寫 {n} 個檔案").format(n=len(plan.overwritten)), "#B5852E")
    _count_row(tr("刪除 {n} 個檔案（備份中沒有的檔案會被移除）").format(n=len(plan.deleted)),
               "#C0392B")
    _count_row(tr("保持不變 {n} 個檔案").format(n=len(plan.unchanged)), "#7A7A7A")

    if not plan.target_exists:
        note = ttk.Label(win, wraplength=_W - 40, justify="left",
                         text=tr("還原目標目前不存在，將會重新建立。"))
        note.pack(anchor="w", padx=14, pady=(6, 0))
        note.configure(foreground=tcol("#1A6FA0"))

    # ── Sample paths ─────────────────────────────────────────────────────
    body = ttk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 4))
    txt = tk.Text(body, wrap="none", height=10)
    vsb = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=vsb.set)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    txt.tag_configure("h", font=("", 10, "bold"))
    txt.tag_configure("add", foreground=tcol("#1A7A3F"))
    txt.tag_configure("mod", foreground=tcol("#B5852E"))
    txt.tag_configure("del", foreground=tcol("#C0392B"))
    txt.tag_configure("more", foreground=tcol("#7A7A7A"))

    def _section(title: str, bucket, tag: str) -> None:
        if not bucket:
            return
        txt.insert("end", title + "\n", "h")
        for rel in plan.sample(bucket):
            txt.insert("end", f"    {rel}\n", tag)
        extra = len(bucket) - len(plan.sample(bucket))
        if extra > 0:
            txt.insert("end", tr("    …另外還有 {n} 個\n").format(n=extra), "more")
        txt.insert("end", "\n")

    _section(tr("將刪除："), plan.deleted, "del")
    _section(tr("將覆寫："), plan.overwritten, "mod")
    _section(tr("將新增："), plan.added, "add")
    txt.configure(state="disabled")

    # ── Safety note ──────────────────────────────────────────────────────
    safe = ttk.Label(
        win, wraplength=_W - 40, justify="left",
        text=tr("還原前會自動把目前的內容備份一份到備份中心，"
                "所以這次還原本身也可以再還原回來。"))
    safe.pack(anchor="w", padx=14, pady=(0, 6))
    safe.configure(foreground=tcol("#1A6FA0"))

    # ── Buttons (取消左・確認右, per the tool's convention) ───────────────
    bar = ttk.Frame(win)
    bar.pack(fill=tk.X, padx=14, pady=(0, 12))

    def _confirm() -> None:
        result["ok"] = True
        win.destroy()

    ttk.Button(bar, text=tr("確認還原"), command=_confirm,
               style="danger.TButton").pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(bar, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT)

    win.grab_set()
    app.root.wait_window(win)
    return result["ok"]
