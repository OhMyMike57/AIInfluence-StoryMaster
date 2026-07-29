from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog

from services import snapshot_service as svc_snapshot
from services.settings_service import (
    AVAILABLE_LANGUAGES, AVAILABLE_THEMES, normalize_default_sort,
    sort_display_options, sort_label,
)
from ui.theme import labeled_frame
from dialogs.dialogue_tag_dialog import open_dialogue_tag_dialog
from dialogs.preview_font_dialog import open_preview_font_dialog
from i18n import tr
from ui.theme import tcol
from widgets.window_center import center_window


def _open_snapshot_help(app) -> None:
    """Explain what 「存檔備份」 means here — the MOD's snapshot, not ours.

    Players already know this tool has its own 備份中心, so the wording has to
    make the distinction unmissable; body text is hard-coded zh-Hant like the
    other in-app help windows (see 動態事件 使用說明) to avoid bloating i18n.
    """
    win = tk.Toplevel(app.root)
    win.title(tr("存檔備份處理 — 說明"))
    win.transient(app.root)
    win.grab_set()
    center_window(win, 660, 470)

    t = tk.Text(win, wrap="word", font=("Microsoft JhengHei", 10),
                relief="flat", padx=16, pady=14, cursor="arrow")
    t.pack(fill=tk.BOTH, expand=True)
    t.tag_configure("h", font=("Microsoft JhengHei", 11, "bold"),
                    foreground=tcol("#2471A3"), spacing1=10, spacing3=4)
    t.tag_configure("body", spacing3=4)
    t.tag_configure("warn", foreground=tcol("#C0392B"), font=("Microsoft JhengHei", 10, "bold"))
    t.tag_configure("ok", foreground=tcol("#1A8A4A"))

    t.insert("end", tr("這裡的「存檔備份」是誰的備份？"), "h")
    t.insert("end", "\n", "body")
    t.insert("end", tr("是《AI效應》模組自己的備份，不是本工具的備份中心。"), "warn")
    t.insert("end", "\n", "body")
    t.insert("end", tr("AI效應 6.0 起，每次你在遊戲中存檔時，模組都會把整個戰役資料夾"
                       "複製一份到 save_snapshots 資料夾（依存檔槽分開存放）。"), "body")

    t.insert("end", "\n" + tr("為什麼需要處理它？"), "h")
    t.insert("end", "\n", "body")
    t.insert("end", tr("因為載入存檔時，模組會用那份備份「覆蓋」整個戰役資料夾——先清空、再整包拷回。"
                       "也就是說：你在主選單用本工具做的編輯，會在下次載入遊戲時被還原掉，"
                       "就像沒改過一樣；新增的角色檔也會被一併刪除。"), "body")

    t.insert("end", "\n" + tr("「自動清除存檔備份」做了什麼？"), "h")
    t.insert("end", "\n", "body")
    t.insert("end", tr("本工具每次寫入戰役資料後，會刪掉該戰役 save_snapshots 內的備份。"
                       "模組載入時找不到備份，就會直接使用你編輯後的資料。"), "body")
    t.insert("end", "\n", "body")
    t.insert("end", tr("這是安全的：那份備份本來就是「用過即丟」——模組還原後也會自己把它刪掉。"), "ok")

    t.insert("end", "\n" + tr("會有什麼影響？"), "h")
    t.insert("end", "\n", "body")
    t.insert("end", tr("唯一的差別是：當你去載入「更舊的存檔槽」時，模組不會再把它的資料一起回捲，"
                       "行為會回到 AI效應 5.x 的樣子。對絕大多數玩家沒有影響。"), "body")
    t.insert("end", "\n", "body")
    t.insert("end", tr("你自己的遊戲存檔（Bannerlord 的 .sav）完全不受影響，"
                       "本工具備份中心裡的備份也完全不受影響。"), "ok")

    t.configure(state="disabled")
    ttk.Button(win, text=tr("關閉"), command=win.destroy,
               style="secondary.TButton").pack(pady=(0, 12))


def build_settings_tab(app, notebook: ttk.Notebook) -> None:
    settings_tab = ttk.Frame(notebook)
    notebook.add(settings_tab, text=tr("⚙️ 設定"))

    # ── Scrollable container (inner frame tracks the canvas width so the two
    #    columns below can share the full width) ───────────────────────────
    canvas = tk.Canvas(settings_tab, highlightthickness=0)
    scrollbar = ttk.Scrollbar(settings_tab, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)
    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    _win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(_win, width=e.width))
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # Two columns; the right column is free since v1.1.0 (the core module
    # installs through the normal Modules workflow — status moved to 關於).
    cols = ttk.Frame(scroll_frame)
    cols.pack(fill=tk.BOTH, expand=True)
    cols.columnconfigure(0, weight=3, uniform="c")
    cols.columnconfigure(1, weight=2, uniform="c")
    left = ttk.Frame(cols)
    left.grid(row=0, column=0, sticky="nsew")
    right = ttk.Frame(cols)
    right.grid(row=0, column=1, sticky="nsew")

    def _open_dir(path_str: str):
        import os as _os
        p = (path_str or "").strip()
        if p and _os.path.isdir(p):
            try:
                _os.startfile(p)
            except Exception:
                pass

    def _path_row(parent, label_text, var, browse_cmd, hint="", open_dir=False):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=10, pady=(4, 2))
        ttk.Label(row, text=label_text, width=10).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var, width=40).pack(side=tk.LEFT, padx=(6, 6), fill=tk.X, expand=True)
        ttk.Button(row, text=tr("瀏覽..."), command=browse_cmd, style="secondary.TButton").pack(side=tk.LEFT, padx=(0, 4))
        if open_dir:
            ttk.Button(row, text=tr("📂 開啟"), command=lambda: _open_dir(var.get()),
                       style="secondary.TButton").pack(side=tk.LEFT)
        if hint:
            ttk.Label(parent, text=hint, foreground=tcol("#888888")).pack(anchor="w", padx=(80, 10), pady=(0, 4))

    # ════════════════════════════════════════════════════════════════════
    # ── 遊戲檔案位置 (game / campaign paths) ─────────────────────────────
    # ════════════════════════════════════════════════════════════════════
    files_frame = labeled_frame(left, text=tr("遊戲檔案位置"))
    files_frame.pack(fill=tk.X, padx=20, pady=(20, 12))

    _path_row(files_frame, tr("遊戲位置:"), app.game_dir_var, app.choose_game_dir,
              hint=tr("Bannerlord 主目錄；留空則自動偵測"), open_dir=True)
    _path_row(files_frame, tr("戰役位置:"), app.save_data_var, app.choose_save_data_dir,
              hint=tr("AIInfluence/save_data 路徑；留空則由遊戲位置推導"), open_dir=True)

    auto_row = ttk.Frame(files_frame)
    auto_row.pack(fill=tk.X, padx=10, pady=(4, 4))
    ttk.Button(auto_row, text=tr("🔍 自動偵測路徑"), command=app.auto_detect_paths,
               style="info.TButton").pack(side=tk.LEFT)

    # Save/cancel bar — shown only when the paths differ from what's saved.
    _games_base = {"g": (app.settings.get("game_dir") or "").strip(),
                   "s": (app.settings.get("save_data_dir") or "").strip()}
    games_bar = ttk.Frame(files_frame)

    def _games_changed():
        return (app.game_dir_var.get().strip() != _games_base["g"]
                or app.save_data_var.get().strip() != _games_base["s"])

    def _refresh_games_bar(*_a):
        if _games_changed():
            games_bar.pack(fill=tk.X, padx=10, pady=(2, 8))
        else:
            games_bar.pack_forget()

    def _games_save():
        app.save_preferences()
        _games_base["g"] = app.game_dir_var.get().strip()
        _games_base["s"] = app.save_data_var.get().strip()
        _refresh_games_bar()

    def _games_cancel():
        app.game_dir_var.set(_games_base["g"])
        app.save_data_var.set(_games_base["s"])
        _refresh_games_bar()

    ttk.Button(games_bar, text=tr("儲存"), command=_games_save, style="success.TButton").pack(side=tk.RIGHT, padx=(4, 0))
    ttk.Button(games_bar, text=tr("取消"), command=_games_cancel, style="secondary.TButton").pack(side=tk.RIGHT)
    for _v in (app.game_dir_var, app.save_data_var):
        _v.trace_add("write", _refresh_games_bar)
    _refresh_games_bar()

    # ════════════════════════════════════════════════════════════════════
    # ── 工具檔案位置 (writable data dir: config / cache / backups) ──────
    # ════════════════════════════════════════════════════════════════════
    tool_frame = labeled_frame(left, text=tr("工具檔案位置"))
    tool_frame.pack(fill=tk.X, padx=20, pady=(0, 12))

    ttk.Label(tool_frame, foreground=tcol("#5A5A5A"), justify="left", wraplength=560,
              text=tr("工具自己的檔案（偏好設定、資料庫快取、各種備份）統一存放在這個「資料目錄」，"
                      "與遊戲存檔無關。預設位於 %APPDATA%\\AIInfluenceStoryTools。")).pack(
        anchor="w", padx=10, pady=(4, 4))

    app.data_dir_var = tk.StringVar(value=str(getattr(app, "data_dir", "")))
    _data_base = {"d": app.data_dir_var.get().strip()}
    drow = ttk.Frame(tool_frame)
    drow.pack(fill=tk.X, padx=10, pady=(2, 2))
    ttk.Label(drow, text=tr("資料目錄:"), width=10).pack(side=tk.LEFT)
    ttk.Entry(drow, textvariable=app.data_dir_var, width=40).pack(side=tk.LEFT, padx=(6, 6), fill=tk.X, expand=True)

    def _browse_data_dir():
        p = filedialog.askdirectory(title=tr("選擇資料目錄"),
                                    initialdir=str(getattr(app, "data_dir", "")) or None, parent=app.root)
        if p:
            app.data_dir_var.set(p)

    ttk.Button(drow, text=tr("瀏覽..."), command=_browse_data_dir, style="secondary.TButton").pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(drow, text=tr("📂 開啟"), command=lambda: _open_dir(str(getattr(app, "data_dir", ""))),
               style="secondary.TButton").pack(side=tk.LEFT)

    def _apply_data_dir():
        from ui import msgbox as _mb
        import services.app_paths as _ap
        new = app.data_dir_var.get().strip()
        cur = str(getattr(app, "data_dir", ""))
        if new and new == cur:
            _mb.showinfo(tr("資料目錄"), tr("已是目前的資料目錄。"), parent=app.root)
            return
        dest = new or str(_ap.default_data_dir())
        if not _mb.askyesno(
                tr("資料遷移"),
                tr("將把目前資料（偏好設定／資料庫快取／備份）搬移到：") + f"\n{dest}\n\n"
                + tr("既有檔案不會被覆蓋，舊資料會保留。重啟工具後生效。要繼續嗎？"),
                parent=app.root):
            return
        ok, msg = _ap.set_data_dir(new or None)
        if ok:
            _data_base["d"] = new
            _refresh_data_bar()
        (_mb.showinfo if ok else _mb.showerror)(tr("資料目錄"), tr(msg), parent=app.root)

    # 套用 button is hidden until the data dir is actually changed.
    data_bar = ttk.Frame(tool_frame)
    data_bar.pack(fill=tk.X, padx=10, pady=(2, 2))
    _apply_data_btn = ttk.Button(data_bar, text=tr("套用並搬移至新位置"),
                                 command=_apply_data_dir, style="warning.TButton")

    def _refresh_data_bar(*_a):
        if app.data_dir_var.get().strip() != _data_base["d"]:
            _apply_data_btn.pack(side=tk.LEFT)
        else:
            _apply_data_btn.pack_forget()

    ttk.Label(tool_frame, foreground=tcol("#5B7FA6"), justify="left", wraplength=560,
              text=tr("更換位置：① 按「瀏覽」選擇新資料夾（可在對話框中新建）→ "
                      "② 出現的「套用並搬移至新位置」按下後，工具會自動把現有資料搬到新位置 → "
                      "③ 重啟工具後生效。")).pack(anchor="w", padx=10, pady=(2, 8))
    app.data_dir_var.trace_add("write", _refresh_data_bar)
    _refresh_data_bar()

    # ════════════════════════════════════════════════════════════════════
    # ── 偏好設定 (preferences) ──────────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════
    pref_frame = labeled_frame(left, text=tr("偏好設定"))
    pref_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

    sort_row = ttk.Frame(pref_frame)
    sort_row.pack(fill=tk.X, padx=10, pady=(4, 3))
    ttk.Label(sort_row, text=tr("預設排序方式:"), width=14).pack(side=tk.LEFT)
    app.default_sort_var = tk.StringVar(value=sort_label(normalize_default_sort(str(app.settings.get("default_sort", "收藏")))))  # noqa: cjk (sort key)
    ttk.Combobox(sort_row, textvariable=app.default_sort_var, values=sort_display_options(),
                 state="readonly", width=14).pack(side=tk.LEFT)

    tag_row = ttk.Frame(pref_frame)
    tag_row.pack(fill=tk.X, padx=10, pady=3)
    ttk.Label(tag_row, text=tr("對話標籤:"), width=14).pack(side=tk.LEFT)
    ttk.Button(tag_row, text=tr("管理自訂對話標籤…"),
               command=lambda: open_dialogue_tag_dialog(app),
               style="secondary.TButton").pack(side=tk.LEFT)
    ttk.Label(tag_row, text=tr("　寫在說話者位置的情境標籤，例如 (劇情描述)"),
              foreground=tcol("#9AA0A6")).pack(side=tk.LEFT)

    font_row = ttk.Frame(pref_frame)
    font_row.pack(fill=tk.X, padx=10, pady=3)
    ttk.Label(font_row, text=tr("預覽字體:"), width=14).pack(side=tk.LEFT)
    ttk.Button(font_row, text=tr("預覽字體設定…"),
               command=lambda: open_preview_font_dialog(app),
               style="secondary.TButton").pack(side=tk.LEFT)
    ttk.Label(font_row, text=tr("　調整各處預覽區的文字大小（清單與表單不受影響）"),
              foreground=tcol("#9AA0A6")).pack(side=tk.LEFT)

    camp_pref_row = ttk.Frame(pref_frame)
    camp_pref_row.pack(fill=tk.X, padx=10, pady=3)
    ttk.Label(camp_pref_row, text=tr("預設載入戰役:"), width=14).pack(side=tk.LEFT)
    app.default_campaign_combo = ttk.Combobox(camp_pref_row, textvariable=app.default_campaign_var,
                                              width=32, state="readonly")
    app.default_campaign_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    lang_row = ttk.Frame(pref_frame)
    lang_row.pack(fill=tk.X, padx=10, pady=3)
    ttk.Label(lang_row, text=tr("語言:"), width=14).pack(side=tk.LEFT)
    lang_display_names = [display for _, display in AVAILABLE_LANGUAGES]
    current_code = app.language_var.get()
    current_display = next((d for c, d in AVAILABLE_LANGUAGES if c == current_code), lang_display_names[0])
    app.language_display_var = tk.StringVar(value=current_display)
    ttk.Combobox(lang_row, textvariable=app.language_display_var, values=lang_display_names,
                 state="readonly", width=16).pack(side=tk.LEFT)
    ttk.Label(lang_row, text=tr("(重啟後生效 / Restart to apply)")).pack(side=tk.LEFT, padx=8)

    # AI Influence 6.0+ restores its own per-slot snapshot over the campaign
    # folder on load.  "存檔備份" here means *the mod's* backup, never this
    # tool's — hence the explicit 說明 button next to it.
    snap_row = ttk.Frame(pref_frame)
    snap_row.pack(fill=tk.X, padx=10, pady=3)
    ttk.Label(snap_row, text=tr("存檔備份處理:"), width=14).pack(side=tk.LEFT)
    app.snapshot_policy_display_var = tk.StringVar(
        value=svc_snapshot.policy_label(app.settings.get("snapshot_policy")))
    snap_combo = ttk.Combobox(snap_row, textvariable=app.snapshot_policy_display_var,
                              values=svc_snapshot.policy_display_options(),
                              state="readonly", width=24)
    snap_combo.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(snap_row, text=tr("ⓘ 說明"),
               command=lambda: _open_snapshot_help(app),
               style="secondary.TButton").pack(side=tk.LEFT)

    # One-line consequence of the selected policy, refreshed on change: the three
    # options differ in whether edits stick and whether the mod's rollback
    # survives, which the labels alone cannot convey.
    snap_hint = ttk.Label(pref_frame, foreground=tcol("#6B5B3E"), justify="left",
                          wraplength=560)
    snap_hint.pack(fill=tk.X, padx=(122, 10), pady=(0, 4), anchor="w")

    def _sync_snap_hint(*_a) -> None:
        pid = svc_snapshot.policy_from_label(app.snapshot_policy_display_var.get())
        snap_hint.config(text=svc_snapshot.policy_hint(pid))

    snap_combo.bind("<<ComboboxSelected>>", _sync_snap_hint)
    _sync_snap_hint()

    # Theme has its own immediate-apply button and is intentionally NOT part of
    # the preference save/cancel change-tracking.
    theme_row = ttk.Frame(pref_frame)
    theme_row.pack(fill=tk.X, padx=10, pady=3)
    ttk.Label(theme_row, text=tr("介面主題:"), width=14).pack(side=tk.LEFT)
    theme_display_names = [tr(display) for _, display in AVAILABLE_THEMES]
    current_theme = app.settings.get("theme", "sandstone")
    current_theme_display = next((tr(d) for t, d in AVAILABLE_THEMES if t == current_theme), theme_display_names[0])
    app.theme_display_var = tk.StringVar(value=current_theme_display)
    ttk.Combobox(theme_row, textvariable=app.theme_display_var, values=theme_display_names,
                 state="readonly", width=16).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(theme_row, text=tr("立即套用"), command=app.apply_theme_from_settings,
               style="warning.TButton").pack(side=tk.LEFT)

    # Save/cancel bar — shown only when a (non-theme) preference changed.
    _pref_base = {"sort": app.default_sort_var.get(), "camp": app.default_campaign_var.get(),
                  "lang": app.language_display_var.get(),
                  "snap": app.snapshot_policy_display_var.get()}
    pref_bar = ttk.Frame(pref_frame)

    def _pref_changed():
        return (app.default_sort_var.get() != _pref_base["sort"]
                or app.default_campaign_var.get() != _pref_base["camp"]
                or app.language_display_var.get() != _pref_base["lang"]
                or app.snapshot_policy_display_var.get() != _pref_base["snap"])

    def _refresh_pref_bar(*_a):
        if _pref_changed():
            pref_bar.pack(fill=tk.X, padx=10, pady=(4, 10))
        else:
            pref_bar.pack_forget()

    def _pref_save():
        app.save_preferences()
        _pref_base.update(sort=app.default_sort_var.get(), camp=app.default_campaign_var.get(),
                          lang=app.language_display_var.get(),
                          snap=app.snapshot_policy_display_var.get())
        _refresh_pref_bar()

    def _pref_cancel():
        app.default_sort_var.set(_pref_base["sort"])
        app.default_campaign_var.set(_pref_base["camp"])
        app.language_display_var.set(_pref_base["lang"])
        app.snapshot_policy_display_var.set(_pref_base["snap"])
        _refresh_pref_bar()

    ttk.Button(pref_bar, text=tr("儲存"), command=_pref_save, style="success.TButton").pack(side=tk.RIGHT, padx=(4, 0))
    ttk.Button(pref_bar, text=tr("取消"), command=_pref_cancel, style="secondary.TButton").pack(side=tk.RIGHT)
    for _v in (app.default_sort_var, app.default_campaign_var, app.language_display_var,
               app.snapshot_policy_display_var):
        _v.trace_add("write", _refresh_pref_bar)
    _refresh_pref_bar()
