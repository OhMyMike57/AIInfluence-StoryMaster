"""Dialog for directly editing a single text field of a character JSON."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Any

from i18n import tr
from services.json_utils import safe_load_json
from ui.theme import labeled_frame

EDITABLE_TEXT_FIELDS = [
    "CharacterDescription",
    "AIGeneratedPersonality",
    "AIGeneratedBackstory",
    "AIGeneratedSpeechQuirks",
    "AIGeneratedCognitiveStyle",
]


def open_field_editor_dialog(app: Any, path: Path) -> None:
    """Open an editor for a single editable text field of a character JSON."""
    win = tk.Toplevel(app.root)
    win.title(tr("角色編輯") + " - " + app._get_character_name(path))
    win.geometry("900x560")
    app._center_window(win, 900, 560)
    win.transient(app.root)

    top = ttk.Frame(win)
    top.pack(fill=tk.X, padx=10, pady=8)
    ttk.Label(top, text=tr("欄位:")).pack(side=tk.LEFT)
    field_var = tk.StringVar(value=EDITABLE_TEXT_FIELDS[0])
    combo = ttk.Combobox(top, textvariable=field_var, values=EDITABLE_TEXT_FIELDS, width=30, state="readonly")
    combo.pack(side=tk.LEFT, padx=6)
    combo.bind("<<ComboboxSelected>>", lambda e: load_field())

    body = ttk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
    left = labeled_frame(body, text=tr("目前值"))
    right = labeled_frame(body, text=tr("新值"))
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

    current_text = tk.Text(left, wrap="word")
    current_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
    current_text.configure(state="disabled")
    edit_text = tk.Text(right, wrap="word")
    edit_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    def load_field(*_):
        d = app._effective_data(path)
        v = d.get(field_var.get(), "") or ""
        if not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False, indent=2)
        current_text.configure(state="normal")
        current_text.delete("1.0", "end")
        current_text.insert("1.0", v)
        current_text.configure(state="disabled")
        edit_text.delete("1.0", "end")
        edit_text.insert("1.0", v)

    load_field()

    def save_change():
        value = edit_text.get("1.0", "end").rstrip("\n")
        d = safe_load_json(path) or {}
        if not isinstance(d, dict):
            d = {}
        d[field_var.get()] = value
        ok = 1 if app.safe_write_json_with_backup(path, d) else 0
        app.log(tr("已寫入 {v0}：{ok} 位角色").format(v0=field_var.get(), ok=ok), "SUCCESS")
        win.destroy()

    btn = ttk.Frame(win)
    btn.pack(fill=tk.X, padx=10, pady=8)
    ttk.Button(btn, text=tr("直接寫入"), command=save_change, style="warning.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn, text=tr("取消"), command=win.destroy, style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
