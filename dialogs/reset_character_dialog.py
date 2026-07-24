"""Dialog: 重置角色 — reset selected character JSONs to a pristine state.

Inverse of the old "清理 JSON" tool: instead of choosing fields to CLEAR, you
choose fields to PRESERVE; everything else is rebuilt from the fresh default
template.  Because the output is built from the template (not the input), this
doubles as a character-inheritance / format-upgrade tool:

  • Upgrade an old 4.1.0 character JSON into clean current-format.
  • Carry a character's core save (description / personality / knowledge /
    conversation) from an old campaign into a new one, clearing campaign state.

The template's field set was diffed against real 6.0.2 save data (see
``scripts/reset_character_check``): every key the template writes exists in 6.0
saves and 6.0 adds none, so the reset output loads cleanly in AI Influence 6.0.
The wording therefore says "current version" rather than pinning a number.

Identity / creation-intrinsic fields (Name / StringId / Gender /
InformationAccessLevel / player_bind_string_id) are always carried.
"""
from __future__ import annotations

from i18n import tr

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Any

from services.json_utils import safe_load_json
from services.character_service import (
    RESET_PRESERVABLE_FIELDS,
    RESET_ALWAYS_KEEP,
    reset_character_json,
)
from ui.theme import tcol


def open_reset_character_dialog(app: Any, paths: list) -> None:
    """Open the batch character-reset dialog for the given character JSON *paths*."""
    win = tk.Toplevel(app.root)
    win.title(tr("重置角色"))
    W, H = 580, 730
    win.geometry(f"{W}x{H}")
    app._center_window(win, W, H)
    win.transient(app.root)

    # ── Header explainer ──────────────────────────────────────────────────
    head = ttk.Frame(win)
    head.pack(fill=tk.X, padx=12, pady=(12, 4))
    ttk.Label(head, text=tr("♻ 重置角色"), font=("", 13, "bold")).pack(anchor="w")
    ttk.Label(
        head,
        text=tr("將選取的 {n} 位角色重建為純淨的初始狀態（相容 AI效應 6.0）。").format(n=len(paths)),
        justify="left", foreground=tcol("#5A5A5A"), wraplength=W - 40,
    ).pack(anchor="w", pady=(4, 0))

    # Semantics callout — the most-confused part, given its own emphasised line.
    sem = ttk.Frame(head)
    sem.pack(fill=tk.X, pady=(6, 2))
    ttk.Label(sem, text=tr("⚠ 勾選＝保留該欄位；未勾選的欄位才會被清空。"),
              justify="left", foreground=tcol("#A15C00"), font=("", 10, "bold"),
              wraplength=W - 40).pack(anchor="w")
    ttk.Label(sem, text=tr("　• 想完全清空角色 → 按下方「全部清除（僅留身分）」"),
              justify="left", foreground=tcol("#5A5A5A"), wraplength=W - 40).pack(anchor="w")
    ttk.Label(sem, text=tr("　• 想保留人格／對話 → 保持預設勾選即可"),
              justify="left", foreground=tcol("#5A5A5A"), wraplength=W - 40).pack(anchor="w")

    # Common uses.
    uses = ttk.Frame(head)
    uses.pack(fill=tk.X, pady=(6, 2))
    ttk.Label(uses, text=tr("常見用途："), justify="left",
              foreground=tcol("#3A3A3A"), font=("", 10, "bold")).pack(anchor="w")
    for _u in (tr("把舊版角色升級為新版格式"),
               tr("把角色核心存檔帶到新戰役（保留人格／對話）"),
               tr("手動保養角色資料（清掉戰役雜訊欄位、修復異常存檔）")):
        ttk.Label(uses, text="　• " + _u, justify="left",
                  foreground=tcol("#5A5A5A"), wraplength=W - 40).pack(anchor="w")

    ttk.Label(
        head,
        text=tr("固定保留：") + " / ".join(RESET_ALWAYS_KEEP),
        justify="left", foreground=tcol("#7B5010"), wraplength=W - 40, font=("", 9),
    ).pack(anchor="w", pady=(6, 0))

    # ── Scrollable checkbox area ──────────────────────────────────────────
    body = ttk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
    canvas = tk.Canvas(body, highlightthickness=0)
    sb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)

    # Mouse-wheel scrolling, bound only while the cursor is over the canvas.
    def _wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    vars_dict: dict[str, tk.BooleanVar] = {}
    last_group = None
    for key, label_zh, default_on, group in RESET_PRESERVABLE_FIELDS:
        if group != last_group:
            ttk.Label(inner, text=tr(group), font=("", 10, "bold"),
                      foreground=tcol("#1A3A5C")).pack(anchor="w", padx=4, pady=(10, 2))
            last_group = group
        v = tk.BooleanVar(value=default_on)
        vars_dict[key] = v
        ttk.Checkbutton(inner, variable=v,
                        text=f"{key} — {tr(label_zh)}").pack(anchor="w", padx=16, pady=1)

    # ── Bulk toggles ──────────────────────────────────────────────────────
    tog = ttk.Frame(win)
    tog.pack(fill=tk.X, padx=12, pady=(0, 2))

    def set_all(val: bool) -> None:
        for v in vars_dict.values():
            v.set(val)

    def set_defaults() -> None:
        for key, _l, d, _g in RESET_PRESERVABLE_FIELDS:
            vars_dict[key].set(d)

    ttk.Button(tog, text=tr("全部保留"), command=lambda: set_all(True), style="secondary.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(tog, text=tr("全部清除（僅留身分）"), command=lambda: set_all(False), style="secondary.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(tog, text=tr("恢復建議勾選"), command=set_defaults, style="secondary.TButton").pack(side=tk.LEFT, padx=2)

    # ── Action buttons ────────────────────────────────────────────────────
    def confirm() -> None:
        preserve = {k for k, v in vars_dict.items() if v.get()}
        n = len(paths)
        kept = "、".join(k for k, _l, _d, _g in RESET_PRESERVABLE_FIELDS if k in preserve) \
            or tr("（無，僅保留固定欄位）")
        if not messagebox.askyesno(
            tr("重置角色"),
            tr("確定要將 {n} 位角色重建為初始狀態（相容 AI效應 6.0）嗎？\n\n保留欄位：\n{kept}\n\n其餘欄位將清空為預設；舊版專屬欄位會被移除。\n此動作會覆寫角色 JSON（會自動備份）。").format(n=n, kept=kept),
        ):
            return
        ok = 0
        for path in paths:
            d = safe_load_json(path) or {}
            new_d = reset_character_json(d, preserve)
            if app.safe_write_json_with_backup(path, new_d):
                ok += 1
        app.log(tr("已重置 {ok}/{n} 位角色為初始狀態（保留 {v0} 個可選欄位）").format(ok=ok, n=n, v0=len(preserve)), "SUCCESS")
        win.destroy()
        # Refresh the character list so the UI reflects the rewritten files.
        if hasattr(app, "_load_characters_in_thread"):
            try:
                app._load_characters_in_thread()
            except Exception:
                pass

    bar = ttk.Frame(win)
    bar.pack(fill=tk.X, pady=10, padx=12)
    ttk.Button(bar, text=tr("確認重置"), command=confirm, style="warning.TButton").pack(side=tk.RIGHT, padx=6)
    ttk.Button(bar, text=tr("取消"), command=win.destroy, style="secondary.TButton").pack(side=tk.RIGHT)
