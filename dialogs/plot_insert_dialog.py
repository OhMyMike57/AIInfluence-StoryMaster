from __future__ import annotations

from i18n import tr

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox

from controllers.main_workspace_controller import normalize_plot_text
from services import speaker_format as SF
from services import terminology_service as TS
from widgets.speaker_field import SpeakerField
from ui.theme import tcol


def open_plot_insert_dialog(app, selected_paths):
    input_win = tk.Toplevel(app.root)
    input_win.title(tr("寫入劇情"))
    # Wide on purpose: the speaker row grows a second line (旁聽 day/distance, or
    # the 戰場 engagement pair) whose hints sit to the right, and English runs
    # noticeably longer than Chinese — a narrower window clips them.
    input_win.geometry("1180x680")
    app._center_window(input_win, 1180, 680)
    input_win.transient(app.root)

    # Speaker picker: reliable character search (name↔id autocomplete).
    dlg_row = ttk.Frame(input_win)
    dlg_row.pack(fill=tk.X, padx=10, pady=(10, 4))
    sp_line = ttk.Frame(dlg_row)
    sp_line.pack(fill=tk.X, anchor="w")
    ttk.Label(sp_line, text=tr("說話者:")).pack(side=tk.LEFT, padx=(0, 6), anchor="n")
    # Batch write: 「自己（I）」 has no meaning up front (the line goes to many
    # characters), so get_self stays empty.  Per-target rewriting happens at
    # write time — see speaker_format.resolve_for_target below.
    speaker_field = SpeakerField(
        sp_line, app, width=40,
        get_day=lambda: TS.campaign_day_now(getattr(app, "campaign_dir", None)))
    speaker_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(
        dlg_row,
        text=tr("打字可搜尋角色（名字或ID），或輸入 [劇情記憶]/(角色心聲) 等自訂標籤\n"
                "留空則寫入不帶入說話者的純文本（適合用於純提示詞）\n"
                "若說話者正是被寫入的角色，該角色檔案會自動套用「I(名字,`ID`)」的自述格式"),
        foreground=tcol("#6B5B3E"),
        justify="left",
    ).pack(anchor="w", pady=(6, 2))

    hint_lbl = ttk.Label(input_win, text=tr("請輸入劇情內容（會自動合併成單行）:"))
    hint_lbl.pack(pady=(2, 8), padx=10, anchor="w")

    text_widget = tk.Text(input_win, wrap="word", height=12)
    text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

    clean_last = tk.BooleanVar(value=False)
    ttk.Checkbutton(input_win, text=tr("同時清理 LastDynamicResponse / LastAIResponseJson"), variable=clean_last).pack(pady=5)

    def confirm_insert():
        raw_text = text_widget.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showwarning(tr("輸入"), tr("請輸入內容"))
            return

        plot_line = normalize_plot_text(raw_text)
        # An empty speaker is legitimate: the line is then written verbatim with
        # no "speaker:" prefix, which is how a pure prompt / narration line has
        # to look for the AI to read it as context rather than as someone's words.
        prefix = speaker_field.get_prefix()
        speaker = SF.parse(prefix) if prefix else None

        ok_count = 0
        for path in selected_paths:
            d = app._safe_load_json(path) or {}
            ch = d.get("ConversationHistory", [])
            if not isinstance(ch, list):
                ch = []

            # Per target: a line spoken BY the receiving character is recorded in
            # that character's own file as a self-line — the same speaker stays
            # third-person everywhere else.  One write, correct shape in each.
            if speaker is None:
                entry = plot_line
            else:
                target_id = str(d.get("StringId") or "")
                target_name = str(d.get("Name") or "")
                # compose() also applies the wrapper's text convention — a
                # battle shout is always stored quoted.
                entry = SF.compose(
                    SF.resolve_for_target(speaker, target_id, target_name),
                    plot_line)

            ch.append(entry)
            d["ConversationHistory"] = ch

            if clean_last.get():
                d["LastDynamicResponse"] = None
                d["LastAIResponseJson"] = None

            if app.safe_write_json_with_backup(path, d):
                ok_count += 1

        app.log(tr("已插入劇情到 {ok_count} 位角色").format(ok_count=ok_count), "SUCCESS")
        input_win.destroy()

    btn_frame = ttk.Frame(input_win)
    btn_frame.pack(fill=tk.X, pady=10)
    ttk.Button(btn_frame, text=tr("確認寫入"), command=confirm_insert, style="warning.TButton").pack(side=tk.RIGHT, padx=10)
    ttk.Button(btn_frame, text=tr("取消"), command=input_win.destroy, style="secondary.TButton").pack(side=tk.RIGHT)
