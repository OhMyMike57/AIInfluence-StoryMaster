"""載入群聊 dialog — detect group-chat participants, let the user curate the
list (exclude false positives / add missed ones), then replace + lock the
selection and optionally repair the two author-oversight fields.

Detection is the player-anchor heuristic (services.group_chat_service); it is a
*suggestion* — the popup exists precisely so the user can correct it before
anything is applied.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox

from i18n import tr
from services import group_chat_service as G
from services.time_format import format_game_time
from widgets.game_date_field import GameDateField
from widgets.name_id_combo import NameIdCombo
from widgets.window_center import center_window
from ui.theme import paint, tcol


def open_group_chat_dialog(app) -> None:
    # Build {display -> data} for the whole loaded roster.
    char_data = {}
    for display, path in getattr(app, "plain_to_path", {}).items():
        d = app._safe_load_json(path)
        if isinstance(d, dict):
            char_data[display] = d
    if not char_data:
        messagebox.showinfo(tr("載入群聊"), tr("尚未載入任何角色（請先載入戰役）。"), parent=app.root)
        return

    detected = G.detect_group(char_data)
    participants = list(detected["participants"])
    day0 = G.group_day(char_data, participants)
    if day0 <= 0:
        bundle = getattr(app, "diplomacy_bundle", None)
        if isinstance(bundle, dict):
            try:
                day0 = float(bundle.get("saved_campaign_days") or 0.0)
            except (TypeError, ValueError):
                day0 = 0.0

    win = tk.Toplevel(app.root)
    win.title(tr("載入群聊"))
    win.transient(app.root)
    win.grab_set()
    center_window(win, 620, 760)

    if participants:
        head = tr("偵測到 {n} 位可能的群聊參與者（可勾除誤判、手動補上漏抓者）：").format(n=len(participants))
    else:
        head = tr("未自動偵測到群聊參與者（可能已被記憶濃縮）。請手動勾選加入。")
    ttk.Label(win, text=head, wraplength=520, foreground=tcol("#5A5A5A"),
              justify="left").pack(anchor="w", padx=12, pady=(12, 4))

    # ── participant checklist (scrollable) ──
    listwrap = ttk.Frame(win)
    listwrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
    canvas = tk.Canvas(listwrap, highlightthickness=0)
    vsb = ttk.Scrollbar(listwrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    rows = ttk.Frame(canvas)
    win_id = canvas.create_window((0, 0), window=rows, anchor="nw")
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=canvas.winfo_width()))
    rows.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    vars_by_display: dict = {}

    def _add_row(display: str, checked: bool):
        if display in vars_by_display:
            vars_by_display[display].set(True)
            return
        v = tk.BooleanVar(value=checked)
        vars_by_display[display] = v
        name = app._get_character_name(app.plain_to_path[display]) if display in app.plain_to_path else display
        ttk.Checkbutton(rows, text=f"{name}", variable=v).pack(anchor="w", padx=6, pady=1)

    for disp in participants:
        _add_row(disp, True)

    # ── manual add (for members detection missed, e.g. consolidated ones) ──
    # Same character search as 寫入劇情's 說話者 field (NameIdCombo autocomplete).
    sid_to_display = {}
    for disp, d in char_data.items():
        sid = str(d.get("StringId", "") or "")
        if sid:
            sid_to_display[sid] = disp
    add_row = ttk.Frame(win)
    add_row.pack(fill=tk.X, padx=12, pady=(0, 4))
    ttk.Label(add_row, text=tr("加入角色：")).pack(side=tk.LEFT)
    add_combo = NameIdCombo(add_row, app, "characters", width=24,
                            allow_empty=False, autocomplete=True)
    add_combo.pack(side=tk.LEFT, padx=(4, 4))

    def _do_add():
        sid = add_combo.get_id().strip()
        disp = sid_to_display.get(sid)
        if disp:
            _add_row(disp, True)
        else:
            messagebox.showinfo(tr("加入角色"), tr("找不到該角色的存檔（可能尚未生成）。"), parent=win)
    ttk.Button(add_row, text=tr("加入"), command=_do_add, style="secondary.TButton").pack(side=tk.LEFT)

    ttk.Separator(win, orient="horizontal").pack(fill=tk.X, padx=12, pady=4)

    # ── how the mod actually syncs a group chat ──
    # Confirmed by capturing a campaign right after a group chat and again after
    # the next interaction: participants gain the others' lines only later, so
    # editing one in between works on an incomplete history.
    banner = paint(
        tk.Label(
            win,
            text=tr("⚠ AI效應的群聊不會在聊完當下同步：每位參與者要等到主角下次與他互動、"
                    "或系統重新整理該角色時，才會補齊群聊期間其他人的發言。這不影響遊戲中的實際互動，"
                    "但若要編輯剛參與過群聊的角色，建議先讓他完成同步再編輯，否則可能對著不完整的對話動手。"),
            font=("Microsoft JhengHei", 9, "bold"),
            wraplength=560, justify="left", padx=8, pady=6),
        bg=tcol("#E67E22"), fg=tcol("#FFFFFF"))
    banner.pack(fill=tk.X, padx=12, pady=(2, 6))

    # ── repair options (default OFF; opt-in temporary fix) ──
    rep = ttk.Labelframe(win, text=tr("同時修復（可選）"))
    rep.pack(fill=tk.X, padx=12, pady=(0, 4))
    ttk.Label(rep, text=tr("※ AI 效應 5.0.7 版目前存在「群聊參與者互動欄位未更新」的問題，故提供此臨時修復選項。"),
              foreground=tcol("#A15C00"), wraplength=500, justify="left").pack(anchor="w", padx=6, pady=(4, 0))
    day_row = ttk.Frame(rep)
    day_row.pack(fill=tk.X, padx=6, pady=(6, 2))
    ttk.Label(day_row, text=tr("群聊日期:")).pack(side=tk.LEFT, padx=(0, 6))
    date_field = GameDateField(day_row, initial_value=day0, show_raw=False)
    date_field.frame.pack(side=tk.LEFT)
    fix_last = tk.BooleanVar(value=False)
    fix_count = tk.BooleanVar(value=False)
    ttk.Checkbutton(rep, variable=fix_last,
                    text=tr("修復 最後互動時間（LastInteractionTimeDays 設為群聊日）")).pack(anchor="w", padx=6)
    ttk.Checkbutton(rep, variable=fix_count,
                    text=tr("修復 互動次數（參與者與玩家互動次數 +1）")).pack(anchor="w", padx=6, pady=(0, 6))

    # ── confirm / cancel ──
    def _confirm():
        chosen = [d for d, v in vars_by_display.items() if v.get()]
        if not chosen:
            messagebox.showwarning(tr("載入群聊"), tr("請至少勾選一位參與者。"), parent=win)
            return
        try:
            day = float(date_field.get())
        except (TypeError, ValueError):
            day = day0
        win.destroy()
        app._group_chat_commit(chosen, day, bool(fix_last.get()), bool(fix_count.get()))

    btns = ttk.Frame(win)
    btns.pack(fill=tk.X, padx=12, pady=(0, 10))
    ttk.Button(btns, text=tr("確認載入"), command=_confirm, style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(btns, text=tr("取消"), command=win.destroy, style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
