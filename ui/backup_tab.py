"""Backup Center tab.

Lists every backup the tool knows about (campaign saves, cleared-database
snapshots, tool-config backups and the mod's save_snapshots) in one searchable
table, and lets the user open / rename / annotate / restore / delete each one.
All data logic lives in ``services.backup_service``; this module is the view +
interaction layer.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

from i18n import tr
from ui.theme import tcol
from ui import msgbox as messagebox
from services import backup_service as bks
from dialogs.restore_confirm_dialog import open_restore_confirm_dialog


# Type-filter dropdown: display label → kind ("" = all).
def _filter_options():
    return [(tr("全部類型"), ""), (tr("戰役備份"), bks.KIND_CAMPAIGN),
            (tr("資料庫備份"), bks.KIND_DB), (tr("工具設定"), bks.KIND_CONFIG),
            (tr("存檔備份"), bks.KIND_SNAPSHOT)]


def _kind_col_label(kind: str) -> str:
    return {bks.KIND_CAMPAIGN: tr("戰役"), bks.KIND_DB: tr("資料庫"),
            bks.KIND_CONFIG: tr("工具設定"),
            bks.KIND_SNAPSHOT: tr("存檔備份")}.get(kind, kind)


def _fmt_size(n: Optional[int]) -> str:
    if n is None:
        return "…"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def _dir_size(path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    return total


def build_backup_tab(app, notebook: ttk.Notebook) -> None:
    backup_tab = ttk.Frame(notebook)
    notebook.add(backup_tab, text=tr("🗂 備份"))

    # ── Toolbar row 1: filter + search + create/refresh actions ───────────
    bar = ttk.Frame(backup_tab)
    bar.pack(fill=tk.X, padx=8, pady=(8, 2))

    ttk.Label(bar, text=tr("類型")).pack(side=tk.LEFT)
    app._backup_filter_var = tk.StringVar(value=_filter_options()[0][0])
    ttk.Combobox(bar, textvariable=app._backup_filter_var, state="readonly", width=10,
                 values=[d for d, _ in _filter_options()]).pack(side=tk.LEFT, padx=(2, 8))
    _fc = bar.winfo_children()[-1]
    _fc.bind("<<ComboboxSelected>>", lambda e: refresh_backup_center(app))

    ttk.Label(bar, text="🔍").pack(side=tk.LEFT)
    app._backup_search_var = tk.StringVar(value="")
    search_entry = ttk.Entry(bar, textvariable=app._backup_search_var, width=22)
    search_entry.pack(side=tk.LEFT, padx=(2, 8))
    search_entry.bind("<KeyRelease>", lambda e: _debounce_refresh(app))

    ttk.Button(bar, text=tr("🔄 重新載入"), command=lambda: refresh_backup_center(app),
               style="info.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(bar, text=tr("💾 備份目前戰役"), command=app.backup_campaign,
               style="info.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(bar, text=tr("🧰 備份工具設定"), command=app.backup_tool_config_now,
               style="info.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(bar, text=tr("📂 開啟備份資料夾"), command=app.open_backup_dir,
               style="secondary.TButton").pack(side=tk.LEFT, padx=2)

    # ── Toolbar row 2: per-entry actions ──────────────────────────────────
    act = ttk.Frame(backup_tab)
    act.pack(fill=tk.X, padx=8, pady=(0, 2))
    ttk.Button(act, text=tr("📂 開啟"), command=lambda: _open(app),
               style="secondary.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(act, text=tr("✏ 重新命名"), command=lambda: _rename(app),
               style="secondary.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(act, text=tr("🏷 編輯備註"), command=lambda: _edit_note(app),
               style="secondary.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(act, text=tr("♻ 還原"), command=lambda: _restore(app),
               style="danger.TButton").pack(side=tk.LEFT, padx=(12, 2))
    ttk.Button(act, text=tr("🗑 刪除"), command=lambda: _delete(app),
               style="danger.TButton").pack(side=tk.LEFT, padx=2)

    # ── Table ─────────────────────────────────────────────────────────────
    body = ttk.Frame(backup_tab)
    body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
    cols = ("kind", "name", "campaign", "time", "size", "note")
    headings = {
        "kind": tr("類型"), "name": tr("資料夾名稱"), "campaign": tr("戰役名稱"),
        "time": tr("時間"), "size": tr("大小"), "note": tr("備註"),
    }
    widths = {"kind": 70, "name": 240, "campaign": 170, "time": 150, "size": 80, "note": 200}
    tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse")
    for c in cols:
        tree.heading(c, text=headings[c])
        tree.column(c, width=widths[c], anchor="w",
                    stretch=(c in ("name", "note")))
    vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    app._backup_tree = tree
    app._backup_row_map = {}
    app._backup_size_token = 0
    _make_backup_sortable(app, tree)   # click a header to sort (by real values)

    tree.bind("<Double-1>", lambda e: _open(app))

    # Right-click context menu (a UI convention widget, not a modal dialog).
    menu = tk.Menu(tree, tearoff=0)
    menu.add_command(label=tr("📂 開啟"), command=lambda: _open(app))
    menu.add_command(label=tr("✏ 重新命名"), command=lambda: _rename(app))
    menu.add_command(label=tr("🏷 編輯備註"), command=lambda: _edit_note(app))
    menu.add_separator()
    menu.add_command(label=tr("♻ 還原"), command=lambda: _restore(app),
                     foreground=tcol("#C0392B"))
    menu.add_command(label=tr("🗑 刪除"), command=lambda: _delete(app),
                     foreground=tcol("#C0392B"))
    app._backup_menu = menu

    def _popup(event):
        row = tree.identify_row(event.y)
        if row:
            tree.selection_set(row)
            tree.focus(row)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
    tree.bind("<Button-3>", _popup)

    ttk.Label(backup_tab, foreground=tcol("#999999"),
              text=tr("雙擊或按「開啟」可在檔案總管開啟該備份資料夾。")).pack(
        anchor="w", padx=10, pady=(0, 6))


def _make_backup_sortable(app, tree) -> None:
    """Click-to-sort on every column heading (toggles asc/desc), sorting by the
    backing BackupEntry's real values so size sorts by bytes and time by its
    timestamp — not by the formatted display string."""
    state = {"col": None, "rev": False}

    def _key(col, e):
        if col == "kind":
            return (e.kind or "")
        if col == "name":
            return (e.name or "").lower()
        if col == "campaign":
            return (app._campaign_display(e.campaign_id) if e.campaign_id else "").lower()
        if col == "time":
            return e.timestamp.timestamp() if e.timestamp else 0.0
        if col == "size":
            return e.size if e.size is not None else -1
        if col == "note":
            return (e.note or "").lower()
        return ""

    def sort_by(col):
        rev = (not state["rev"]) if state["col"] == col else False
        state.update(col=col, rev=rev)
        iids = [i for i in tree.get_children("") if i in app._backup_row_map]
        iids.sort(key=lambda i: _key(col, app._backup_row_map[i]), reverse=rev)
        for idx, iid in enumerate(iids):
            tree.move(iid, "", idx)

    for c in tree["columns"]:
        tree.heading(c, command=lambda col=c: sort_by(col))


def _debounce_refresh(app) -> None:
    after = getattr(app, "_backup_search_after", None)
    if after:
        try:
            app.root.after_cancel(after)
        except Exception:
            pass
    app._backup_search_after = app.root.after(300, lambda: refresh_backup_center(app))


def refresh_backup_center(app) -> None:
    """Migrate legacy layout, list all backups, apply filter/search, fill tree."""
    tree = getattr(app, "_backup_tree", None)
    if tree is None:
        return
    base = app.backup_dir_var.get()
    try:
        bks.migrate_legacy(base)
    except Exception:
        pass
    entries = bks.list_backups(base)

    kind_filter = dict(_filter_options()).get(app._backup_filter_var.get(), "")
    kw = app._backup_search_var.get().strip().lower()

    def _match(e) -> bool:
        if kind_filter and e.kind != kind_filter:
            return False
        if not kw:
            return True
        hay = " ".join([
            e.name or "",
            (app._campaign_display(e.campaign_id) if e.campaign_id else ""),
            e.note or "",
        ]).lower()
        return kw in hay

    shown = [e for e in entries if _match(e)]

    tree.delete(*tree.get_children())
    app._backup_row_map = {}
    for i, e in enumerate(shown):
        iid = f"e{i}"
        camp = app._campaign_display(e.campaign_id) if e.campaign_id else "—"
        tm = e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "—"
        tree.insert("", tk.END, iid=iid,
                    values=(_kind_col_label(e.kind), e.name, camp, tm,
                            _fmt_size(e.size), e.note or ""))
        app._backup_row_map[iid] = e

    _spawn_size_scan(app, shown)


def _spawn_size_scan(app, entries) -> None:
    """Compute folder sizes off-thread and write them back into the tree."""
    app._backup_size_token += 1
    token = app._backup_size_token
    pairs = [(f"e{i}", e) for i, e in enumerate(entries) if e.size is None]
    if not pairs:
        return

    def worker():
        for iid, e in pairs:
            if token != app._backup_size_token:
                return
            try:
                sz = _dir_size(e.path)
            except Exception:
                sz = None
            e.size = sz

            def _apply(iid=iid, sz=sz):
                if token != app._backup_size_token:
                    return
                try:
                    tree = getattr(app, "_backup_tree", None)
                    if tree is not None and tree.exists(iid):
                        tree.set(iid, "size", _fmt_size(sz))
                except Exception:
                    pass  # widget torn down between scan and apply
            try:
                app.root.after(0, _apply)
            except Exception:
                return

    threading.Thread(target=worker, daemon=True).start()


def _selected_entry(app):
    tree = getattr(app, "_backup_tree", None)
    if tree is None:
        return None
    sel = tree.selection()
    if not sel:
        messagebox.showinfo(tr("備份中心"), tr("請先選擇一筆備份"), parent=app.root)
        return None
    return app._backup_row_map.get(sel[0])


def _open(app) -> None:
    e = _selected_entry(app)
    if e is None:
        return
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(e.path))
        else:
            os.system(f'xdg-open "{e.path}" >/dev/null 2>&1 &')
    except Exception as exc:
        messagebox.showerror(tr("開啟錯誤"), str(exc), parent=app.root)


def _rename(app) -> None:
    e = _selected_entry(app)
    if e is None:
        return
    new = messagebox.askstring(
        tr("重新命名"),
        tr("為備份「{name}」輸入新名稱：").format(name=e.name),
        initialvalue=e.name, parent=app.root)
    if new is None:
        return
    if not bks.valid_backup_name(new):
        messagebox.showwarning(tr("重新命名"), tr("名稱不可為空或含特殊字元。"), parent=app.root)
        return
    ok, msg = bks.rename_backup(app.backup_dir_var.get(), e, new)
    if ok:
        app.log(tr("備份已重新命名"), "SUCCESS")
    elif msg == "exists":
        messagebox.showwarning(tr("重新命名"), tr("同名備份已存在。"), parent=app.root)
    else:
        messagebox.showerror(tr("重新命名"), msg, parent=app.root)
    refresh_backup_center(app)


def _edit_note(app) -> None:
    e = _selected_entry(app)
    if e is None:
        return
    note = messagebox.askstring(
        tr("編輯備註"),
        tr("為備份「{name}」輸入備註（留空清除）：").format(name=e.name),
        initialvalue=e.note, parent=app.root)
    if note is None:
        return
    bks.set_note(app.backup_dir_var.get(), e, note)
    app.log(tr("備註已更新"), "SUCCESS")
    refresh_backup_center(app)


def _restore(app) -> None:
    """Put a backup back over its live target, after showing exactly what changes.

    Ordering matters here: the game lock comes first (restoring under a loaded
    campaign would be overwritten by the mod anyway), then the plan, then the
    confirmation. Nothing is written until the user has seen the delete count.
    """
    e = _selected_entry(app)
    if e is None:
        return

    # AI Influence rewrites the whole campaign folder from memory while a
    # campaign is loaded, so a restore now would simply be undone on the next
    # autosave — and the user would think the backup was faulty.
    if app._confirm_if_game_running(tr("還原備份")):
        return

    try:
        target = bks.resolve_restore_target(
            e,
            save_data_dir=getattr(app, "save_data_dir", None),
            config_dir=getattr(app, "config_dir", None),
        )
    except bks.RestoreError as exc:
        messagebox.showwarning(tr("還原備份"), str(exc), parent=app.root)
        return

    try:
        plan = bks.plan_restore(e, target)
    except bks.RestoreError as exc:
        messagebox.showerror(tr("還原備份"), str(exc), parent=app.root)
        return

    if not plan.total_changes:
        messagebox.showinfo(
            tr("還原備份"),
            tr("目前的內容已經和這份備份相同，不需要還原。"), parent=app.root)
        return

    if not open_restore_confirm_dialog(app, plan):
        app.log(tr("已取消還原備份"), "INFO")
        return

    report = bks.restore_backup(e, target, backup_base=app.backup_dir_var.get(),
                                plan=plan)
    for err in report.errors:
        app.log(tr("還原備份：{v0}").format(v0=err), "ERROR")

    if not report.ok:
        messagebox.showerror(
            tr("還原備份"),
            tr("還原未完成，請查看日誌分頁。\n\n已寫入 {w} 個檔案、移除 {r} 個。")
            .format(w=report.written, r=report.removed), parent=app.root)
        refresh_backup_center(app)
        return

    app.log(tr("已從備份「{name}」還原：寫入 {w} 個檔案、移除 {r} 個")
            .format(name=e.name, w=report.written, r=report.removed), "SUCCESS")

    tail = ""
    if report.safety_backup:
        tail = tr("\n\n還原前的內容已備份為：\n{v0}").format(
            v0=Path(report.safety_backup).name)
    if e.kind == bks.KIND_CONFIG:
        tail += tr("\n\n工具設定已還原，請重新啟動編輯器讓設定生效。")
    else:
        tail += tr("\n\n請重新載入戰役以看到還原後的內容。")
    messagebox.showinfo(
        tr("還原完成"),
        tr("已還原 {w} 個檔案、移除 {r} 個。").format(w=report.written, r=report.removed) + tail,
        parent=app.root)

    refresh_backup_center(app)
    _reload_campaign_after_restore(app, e)


def _reload_campaign_after_restore(app, entry) -> None:
    """Reload the open campaign when a restore changed the data under it.

    Without this the roster, world data and open character panel keep showing
    the pre-restore state, which reads as "the restore did nothing".
    ``ask_dirty=False``: the restore already replaced what was on disk, so
    prompting to keep in-memory edits would offer to re-apply stale data.
    """
    if entry.kind == bks.KIND_CONFIG:
        return                          # needs a restart; nothing to reload live
    try:
        current = getattr(app, "campaign_dir", None)
        if current is not None and current.name == (entry.campaign_id or ""):
            app.refresh(ask_dirty=False)
    except Exception as exc:
        app.log(tr("還原後重新載入戰役失敗：{v0}").format(v0=str(exc)), "WARNING")


def _delete(app) -> None:
    e = _selected_entry(app)
    if e is None:
        return
    if not messagebox.askyesno(
            tr("刪除備份"),
            tr("確定刪除備份「{name}」嗎？\n\n此操作無法復原。").format(name=e.name),
            parent=app.root):
        return
    if bks.delete_backup(app.backup_dir_var.get(), e):
        app.log(tr("備份已刪除"), "SUCCESS")
    else:
        messagebox.showerror(tr("刪除備份"), tr("刪除失敗。"), parent=app.root)
    refresh_backup_center(app)
