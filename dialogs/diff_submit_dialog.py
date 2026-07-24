"""Dialog for reviewing and submitting staged field changes (diff view)."""
from __future__ import annotations

from i18n import tr

import json
import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services.json_utils import safe_load_json
from ui.theme import make_scrollable


def open_diff_submit_dialog(app: Any, items: list) -> None:
    """Open a scrollable diff view for reviewing and submitting staged changes."""
    win = tk.Toplevel(app.root)
    win.title(tr("Diff 提交"))
    win.geometry("1080x680")
    app._center_window(win, 1080, 680)
    win.transient(app.root)

    scroll_outer, scroll_inner = make_scrollable(win)
    scroll_outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    row_vars: List[Tuple[tk.BooleanVar, Dict[str, Any]]] = []
    for item in items:
        var = tk.BooleanVar(value=True)
        row_vars.append((var, item))
        row = ttk.Frame(scroll_inner)
        row.pack(fill=tk.X, padx=8, pady=3)
        ttk.Checkbutton(row, variable=var).pack(side=tk.LEFT)
        old_s = json.dumps(item["old"], ensure_ascii=False) if not isinstance(item["old"], str) else item["old"]
        new_s = json.dumps(item["new"], ensure_ascii=False) if not isinstance(item["new"], str) else item["new"]
        txt = f"[{item['name']}] {item['field']} | {old_s[:80]} -> {new_s[:80]}"
        ttk.Label(row, text=txt).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def submit_selected():
        selected = [item for var, item in row_vars if var.get()]
        if not selected:
            messagebox.showwarning(tr("Diff 提交"), tr("請至少選擇一筆變更"))
            return

        by_path: Dict[Path, Dict[str, Any]] = {}
        for item in selected:
            by_path.setdefault(item["path"], {})[item["field"]] = item["new"]

        snapshot: Dict[Path, Dict[str, Any]] = {}
        ok = 0
        for path, fields in by_path.items():
            original = safe_load_json(path) or {}
            if not isinstance(original, dict):
                continue
            snapshot[path] = dict(original)
            updated = dict(original)
            updated.update(fields)
            if app.safe_write_json_with_backup(path, updated):
                ok += 1
                if path in app.pending_changes:
                    for f in list(fields.keys()):
                        app.pending_changes[path].pop(f, None)
                    if not app.pending_changes[path]:
                        app.pending_changes.pop(path, None)
        if snapshot:
            app.undo_stack.append(snapshot)
            if len(app.undo_stack) > 10:
                app.undo_stack.pop(0)
        app.log(tr("Diff 提交完成：{ok} 個角色").format(ok=ok), "SUCCESS")
        win.destroy()

    btn = ttk.Frame(win)
    btn.pack(fill=tk.X, padx=10, pady=8)
    ttk.Button(btn, text=tr("全選"), command=lambda: [v.set(True) for v, _ in row_vars], style="secondary.TButton").pack(side=tk.LEFT, padx=3)
    ttk.Button(btn, text=tr("全不選"), command=lambda: [v.set(False) for v, _ in row_vars], style="secondary.TButton").pack(side=tk.LEFT, padx=3)
    ttk.Button(btn, text=tr("提交選取項目"), command=submit_selected, style="warning.TButton").pack(side=tk.RIGHT, padx=3)
