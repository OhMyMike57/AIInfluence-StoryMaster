"""關於 tab — since the v1.1.0 transformation, two blocks:

① AI效應：故事大師 — what the *editor module* is, the core-module + editor
   dual nature, the module status check, and the mod-page links.
② 作者聲明 — author intro, developer's words, copyright notice, support links.

The module status check moved here from the settings tab: the editor no longer
installs the module (it ships as one bundle, installed through the normal
Modules workflow), so "is everything wired up" became an about-this-product
question rather than a setup task.
"""
from __future__ import annotations

import datetime
import webbrowser
import tkinter as tk
from tkinter import ttk

from i18n import tr
from services.app_paths import app_version
from ui.theme import labeled_frame, tcol

_NEXUS_MOD_URL = "https://www.nexusmods.com/mountandblade2bannerlord/mods/12048"
_MBCN_MOD_URL = "https://bbs.mountblade.com.cn/download_2541.html"

_STATUS_COLOURS = {
    "version_match":    "#1A7A3F",
    "version_mismatch": "#B5852E",
    "not_installed":    "#C0392B",
    "no_game":          "#C0392B",
}


def build_about_tab(app, notebook: ttk.Notebook) -> None:
    about_tab = ttk.Frame(notebook)
    notebook.add(about_tab, text=tr("ℹ️ 關於"))

    # A centred, narrowed column (~70% width) so the text no longer hugs the
    # left edge — the flanking weight-1 columns become the side margins.
    _W, _WRAP = 1000, 940
    _BODY = ("", 12)
    _TITLE = ("", 14, "bold")
    _LABEL = ("", 12, "bold")

    outer = ttk.Frame(about_tab)
    outer.pack(fill=tk.BOTH, expand=True)
    outer.columnconfigure(0, weight=1)
    outer.columnconfigure(1, weight=0, minsize=_W)
    outer.columnconfigure(2, weight=1)
    outer.rowconfigure(0, weight=1)
    about_root = ttk.Frame(outer)
    about_root.grid(row=0, column=1, sticky="new", pady=16)

    # ══ ① 故事大師 ═══════════════════════════════════════════════════════
    sm_frame = labeled_frame(about_root, text=tr("AI效應：故事大師"))
    sm_frame.pack(fill=tk.X, pady=(0, 16))

    title = tr("AI效應：故事大師（AI Influence: Story Master）") + "  v" + app_version()
    ttk.Label(sm_frame, text=title, font=_TITLE).pack(anchor="w", padx=14, pady=(10, 8))

    intro = tr(
        "這是專為《騎馬與砍殺2：霸主》的模組《AI效應》所打造的編輯器模組。\n"
        "即使不熟悉 JSON，也能直覺地管理整個戰役——角色資料、對話與記憶、世界訊息、"
        "動態事件與疾病，從宏觀到微觀掌控你的故事進程。"
    )
    ttk.Label(sm_frame, text=intro, justify="left", wraplength=_WRAP,
              font=_BODY).pack(anchor="w", padx=14, pady=(0, 8))

    duo = tr(
        "本模組由兩個部分組成，同版號、一體發佈：\n"
        "　• 模組核心 — 隨啟動器載入，於遊戲內匯出戰役資料庫、偵測遊戲狀態、同步百科描述。\n"
        "　• 編輯器 — 你正在使用的這個程式，位於模組資料夾的 Tool 子資料夾內，負責瀏覽與編輯戰役資料。\n"
        "更新模組時兩者會一起更新；編輯器的設定與備份存放於獨立的資料目錄，不會因更新而遺失。"
    )
    ttk.Label(sm_frame, text=duo, justify="left", wraplength=_WRAP, font=_BODY,
              foreground=tcol("#5A5A5A")).pack(anchor="w", padx=14, pady=(0, 10))

    # ── [模組狀態檢查]｜訪問模組頁面：[Nexus][騎砍中文站] ──────────────
    action_row = ttk.Frame(sm_frame)
    action_row.pack(anchor="w", padx=14, pady=(0, 4))
    status_var = tk.StringVar(value="")
    status_lbl = ttk.Label(sm_frame, textvariable=status_var, justify="left",
                           wraplength=_WRAP, font=_BODY)

    def _check_status() -> None:
        try:
            st = app._core_mod_status()
        except Exception as e:
            status_lbl.configure(foreground=tcol("#C0392B"))
            status_var.set(tr("狀態讀取失敗：{e}").format(e=e))
            return
        colour = _STATUS_COLOURS.get(st.state, "#666666")
        status_lbl.configure(foreground=tcol(colour))
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if st.state == "version_match":
            status_var.set(tr("✔ 核心模組運作正常（v{v}，與編輯器版本一致）　·　{ts} 已檢查")
                           .format(v=st.installed, ts=ts))
        elif st.state == "version_mismatch":
            status_var.set(tr("⚠ 核心模組 v{inst} 與編輯器 v{tool} 版本不一致 — 請以完整模組包一併更新")
                           .format(inst=st.installed or "?", tool=st.editor or "?"))
        elif st.state == "not_installed":
            status_var.set(tr("✘ 未在遊戲 Modules 中找到核心模組 — 請確認模組已解壓縮至 Modules 並於啟動器啟用"))
        else:  # no_game
            status_var.set(tr("✘ 尚未設定遊戲位置 — 請前往「設定 → 遊戲檔案位置」"))

    ttk.Button(action_row, text=tr("🔍 模組狀態檢查"), command=_check_status,
               style="info.TButton").pack(side=tk.LEFT)
    ttk.Label(action_row, text="｜").pack(side=tk.LEFT, padx=8)
    ttk.Label(action_row, text=tr("訪問模組頁面："), font=_BODY).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(action_row, text="Nexus",
               command=lambda: webbrowser.open(_NEXUS_MOD_URL),
               style="secondary.TButton").pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(action_row, text=tr("騎砍中文站"),
               command=lambda: webbrowser.open(_MBCN_MOD_URL),
               style="secondary.TButton").pack(side=tk.LEFT)

    status_lbl.pack(anchor="w", padx=14, pady=(2, 10))

    # ══ ② 作者聲明 ═══════════════════════════════════════════════════════
    au_frame = labeled_frame(about_root, text=tr("作者聲明"))
    au_frame.pack(fill=tk.X)

    author = tr(
        "開發者：筆者57（Cartoonist57）\n"
        "來自台灣的《騎馬與砍殺2》玩家與模組社群譯者，長期投入模組翻譯、維護更新與模組開發。"
    )
    ttk.Label(au_frame, text=author, justify="left", wraplength=_WRAP,
              font=_BODY).pack(anchor="w", padx=14, pady=(10, 10))

    # ── 開發者的話（座右銘，照原文；英文歌詞兩語系皆保留英文）──
    ttk.Label(au_frame, text=tr("開發者的話"), font=_LABEL).pack(anchor="w", padx=14, pady=(2, 4))
    dev_words = tr(
        "「想讓世界變美好，從自己開始做起」\n"
        "這句話來自 Michael Jackson 的歌曲《Man In The Mirror》，是我從小到大的人生座右銘，\n"
        "那也是我開始騎砍模組翻譯與模組開發的初衷，儘管這只是遊戲，但我喜歡這遊戲，\n"
        "我想讓更多人也能有美好的遊戲體驗，所以我開始了這一切，\n"
        "無論一件事有多大或多小，只要你開始做了，就能帶來改變！\n\n"
        "「If You Wanna Make The World A Better Place\n"
        "Take A Look At Yourself And Then Make A Change」"
    )
    ttk.Label(au_frame, text=dev_words, justify="left", wraplength=_WRAP - 30,
              font=("", 12, "italic"), foreground=tcol("#4A4A4A")).pack(
                  anchor="w", padx=(32, 14), pady=(0, 12))

    # ── 版權聲明（排版與開發者的話一致：粗體標題＋縮排本文）──
    ttk.Label(au_frame, text=tr("版權聲明"), font=_LABEL).pack(anchor="w", padx=14, pady=(2, 4))
    copyright_notice = tr(
        "本模組為玩家自製的非官方作品，與 TaleWorlds Entertainment 及"
        "《AI效應（AI Influence）》原作者均無隸屬或背書關係；相關名稱與商標歸各自所有者所有。\n"
        "本模組免費提供，歡迎自由使用；請勿未經作者同意重新散布、修改散布或作商業用途。"
    )
    ttk.Label(au_frame, text=copyright_notice, justify="left", wraplength=_WRAP - 30,
              font=_BODY, foreground=tcol("#777777")).pack(
                  anchor="w", padx=(32, 14), pady=(0, 12))

    support = tr(
        "若你喜歡這個模組，歡迎透過贊助（Patreon / Ganknow）或在 Nexus 留言/按讚支持作者。\n"
        "你的鼓勵能幫助作者持續帶來高品質翻譯與更多有趣的模組與工具（1~2 美金的咖啡支持就很有幫助！）。"
    )
    ttk.Label(au_frame, text=support, justify="left", wraplength=_WRAP,
              font=_BODY).pack(anchor="w", padx=14, pady=(0, 8))

    link_row = ttk.Frame(au_frame)
    link_row.pack(anchor="w", padx=14, pady=(0, 12))
    ttk.Button(
        link_row, text=tr("Nexus 作者頁面"),
        command=lambda: webbrowser.open("https://www.nexusmods.com/profile/Cartoonist57"),
    ).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(
        link_row, text=tr("Ganknow 贊助"),
        command=lambda: webbrowser.open("https://ganknow.com/cartoonist57"),
    ).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(
        link_row, text=tr("Patreon 贊助"),
        command=lambda: webbrowser.open("https://www.patreon.com/cw/Writer57"),
    ).pack(side=tk.LEFT)
