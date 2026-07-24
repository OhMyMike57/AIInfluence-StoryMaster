"""Dialog for selecting which fields to queue as staged changes."""
from __future__ import annotations

from i18n import tr

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Any, Dict, List


EDITABLE_TEXT_FIELDS = [
    "CharacterDescription",
    "AIGeneratedPersonality",
    "AIGeneratedBackstory",
    "AIGeneratedSpeechQuirks",
    "AIGeneratedCognitiveStyle",
]

ALL_STAGEABLE_FIELDS = EDITABLE_TEXT_FIELDS + ["KnownSecrets", "KnownInfo"]


def open_field_picker_dialog(app: Any, source_data: dict, targets: list) -> None:
    """Open a dialog to choose which fields to queue for staged changes."""
    pick_win = tk.Toplevel(app.root)
    pick_win.title(tr("加入暫存變更 - 選擇欄位"))
    pick_win.geometry("420x340")
    app._center_window(pick_win, 420, 340)
    pick_win.transient(app.root)

    vars_map: Dict[str, tk.BooleanVar] = {}
    for f in ALL_STAGEABLE_FIELDS:
        v = tk.BooleanVar(value=(f in EDITABLE_TEXT_FIELDS))
        vars_map[f] = v
        ttk.Checkbutton(pick_win, text=f, variable=v).pack(anchor="w", padx=12, pady=4)

    def confirm():
        selected_fields = [k for k, v in vars_map.items() if v.get()]
        if not selected_fields:
            messagebox.showwarning(tr("暫存變更"), tr("請至少選擇一個欄位"))
            return
        for t in targets:
            for field in selected_fields:
                if field in source_data:
                    app._queue_field_change(t, field, source_data.get(field))
        app.log(tr("已加入暫存變更：{v0} 角色 / {v1} 欄位").format(v0=len(targets), v1=len(selected_fields)), "SUCCESS")
        pick_win.destroy()

    ttk.Button(pick_win, text=tr("確認加入"), command=confirm, style="warning.TButton").pack(side=tk.RIGHT, padx=10, pady=10)
