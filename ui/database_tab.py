"""資料庫 tab — full game-character roster + per-character file management.

Unlike the main-workspace list (only interacted characters), this tab lists
*every* real-NPC hero the Story Master companion mod exported, joined with
whether a save JSON exists, with strong filtering and JSON file operations
(reset / generate / delete / backup, plus batch-generate per faction).

The tab is disabled (placeholder shown) when no companion-mod data is loaded.
All data + file operations live on the app (``_db_*`` / ``_refresh_database``);
this module is presentation + wiring only.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Any, Dict, List

from ui.theme import labeled_frame
from ui.tree_helpers import make_sortable
from services import character_db_service as _svc_chardb
from services.time_format import format_export_time
from i18n import tr
from ui.theme import tcol

# Occupation StringId (from the export) → display label.
# Note: GangLeader (gang boss notable) and Gangster (gang member) are two
# distinct TaleWorlds occupations — both are mapped so neither shows raw.
# zh-TW values follow the OFFICIAL game localization (v0.38.0, verified against
# the official language pack): 頭人 not 村莊頭人, 鄉間要人 not 鄉村顯要, 罪犯 not
# 盜匪.  Translated via tr() at use (_occ_label); Special/Gangster have no
# official string (not surfaced in game UI) — kept as reasonable terms.
def _occ_labels() -> dict:
    # occupation token → localized label; built at call time so the tr()
    # literals are visible to the i18n coverage checker (no silent leaks).
    return {
        "Lord": tr("貴族"), "Wanderer": tr("浪人"), "GangLeader": tr("幫派頭目"),
        "Gangster": tr("幫派份子"), "Merchant": tr("商人"), "Artisan": tr("工匠"),
        "RuralNotable": tr("鄉間要人"), "Headman": tr("頭人"), "Preacher": tr("傳教士"),
        "Mercenary": tr("傭兵"), "Special": tr("特殊"), "Outlaw": tr("罪犯"), "Villager": tr("村民"),
    }


def _occ_label(o: Any) -> str:
    o = str(o or "")
    return _occ_labels().get(o, o)


def _gender_label(g: Any) -> str:
    return tr("女") if str(g) == "female" else (tr("男") if str(g) == "male" else "")


def _yn(b: Any) -> str:
    return tr("是") if b else tr("否")


def _make_sortable(tree: ttk.Treeview, numeric_cols=()) -> None:
    """Click-to-sort on every column heading (shared with the 疾病 tab)."""
    make_sortable(tree, numeric_cols)


def _bind_copy(app, tree: ttk.Treeview, id_col: str = "id") -> None:
    """Double-click an ID cell copies the StringId; elsewhere copies the name."""
    def on_double(ev):
        iid = tree.identify_row(ev.y)
        if not iid:
            return
        col = tree.identify_column(ev.x)  # '#0' or '#N'
        copy_id = False
        if col != "#0":
            try:
                copy_id = tree["columns"][int(col[1:]) - 1] == id_col
            except (ValueError, IndexError):
                copy_id = False
        text = tree.set(iid, id_col) if copy_id else tree.item(iid, "text")
        if not text:
            return
        try:
            app.root.clipboard_clear()
            app.root.clipboard_append(str(text))
        except Exception:
            return
        label = tr("ID") if copy_id else tr("名稱")
        if hasattr(app, "log"):
            app.log(tr("已複製{label}：{text}").format(label=label, text=text), "INFO")
    tree.bind("<Double-Button-1>", on_double)


# ── Tab construction ─────────────────────────────────────────────────────────

def build_database_tab(app, notebook: ttk.Notebook) -> None:
    outer = ttk.Frame(notebook)
    notebook.add(outer, text=tr("📇 資料庫"))
    app._db_outer = outer

    # Placeholder shown when no companion-mod data is available.
    ph = ttk.Frame(outer)
    app._db_placeholder = ph
    ttk.Label(ph, text=tr("資料庫尚未可用"), font=("", 14, "bold")).pack(pady=(48, 8))
    ttk.Label(
        ph, foreground=tcol("#888888"), justify="center", wraplength=560,
        text=tr("請確認核心模組已於啟動器啟用，並在遊戲內載入一次戰役以更新資料庫；"
                "編輯器開啟該戰役時會自動讀取。"),
    ).pack()
    # Manual reload so the user can re-read the export after clearing the DB or
    # after the connector re-exports in-game (the toolbar 更新資料庫 button lives
    # inside the content pane, which is hidden while this placeholder shows).
    ttk.Button(ph, text=tr("🔄 重新載入"), style="info.TButton",
               command=lambda: app._db_update_database()).pack(pady=(16, 0))

    content = ttk.Frame(outer)
    app._db_content = content

    # Top toolbar: status + update/clear the whole database.
    toolbar = ttk.Frame(content)
    toolbar.pack(fill=tk.X, padx=6, pady=(6, 0))
    app._db_status_var = tk.StringVar(value="")
    ttk.Label(toolbar, textvariable=app._db_status_var, foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)
    ttk.Button(toolbar, text=tr("🗑 清除資料庫"), style="danger.TButton",
               command=app._db_clear_database).pack(side=tk.RIGHT, padx=2)
    ttk.Button(toolbar, text=tr("🔄 更新資料庫"), style="info.TButton",
               command=app._db_update_database).pack(side=tk.RIGHT, padx=2)

    sub = ttk.Notebook(content)
    sub.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    app._db_subnb = sub

    _build_char_subtab(app, sub)
    _build_entity_subtab(app, sub, "kingdom", tr("👑 王國"))
    _build_entity_subtab(app, sub, "clan", tr("🛡 氏族"))
    _build_entity_subtab(app, sub, "culture", tr("🎭 文化"))
    _build_viewer_subtab(app, sub, "troops", tr("⚔ 單位"))
    _build_viewer_subtab(app, sub, "items", tr("🎒 物品"))
    _build_viewer_subtab(app, sub, "settlements", tr("🏰 定居點"))

    app._db_refresh_ui = lambda: refresh_database_tab(app)
    refresh_database_tab(app)


def refresh_database_tab(app) -> None:
    """Show placeholder or content, then repopulate the active data."""
    if not hasattr(app, "_db_content"):
        return
    avail = app._database_available()
    # Only re-pack when the shown panel actually changes — re-packing the whole
    # content on every refresh caused a visible white flash after each action.
    want = "content" if avail else "placeholder"
    if getattr(app, "_db_shown", None) != want:
        app._db_placeholder.pack_forget()
        app._db_content.pack_forget()
        (app._db_content if avail else app._db_placeholder).pack(fill=tk.BOTH, expand=True)
        app._db_shown = want
    if not avail:
        return
    _refresh_status(app)
    _refresh_char_filter_options(app)
    _refresh_char_tree(app)
    _refresh_entity_lists(app)
    _refresh_viewers(app)


def _refresh_status(app) -> None:
    if not hasattr(app, "_db_status_var"):
        return
    term = app.terminology_campaign if isinstance(app.terminology_campaign, dict) else {}
    cid = app._current_campaign_id() if hasattr(app, "_current_campaign_id") else ""
    ts = format_export_time(term.get("imported_at") or "")
    n_heroes = len(app.db_rows)
    n_files = sum(1 for r in app.db_rows if r.get("HasFile"))
    parts = [f"{tr('戰役')}: {cid}" if cid else "", f"{tr('角色')} {n_heroes}",
             f"{tr('有檔')} {n_files}"]
    if ts:
        parts.append(f"{tr('更新時間')} {ts}")
    app._db_status_var.set("  ·  ".join(p for p in parts if p))


# ── 角色 sub-tab ─────────────────────────────────────────────────────────────

_CHAR_COLS = ("id", "faction", "clan", "culture", "occ", "age", "gender", "married", "alive", "file")
def _char_heads() -> dict:
    # column key → localized heading; tr() literals visible to the checker.
    return {
        "id": "ID", "faction": tr("陣營"), "clan": tr("氏族"), "culture": tr("文化"),
        "occ": tr("職業"), "age": tr("年齡"), "gender": tr("性別"), "married": tr("婚姻"),
        "alive": tr("存活"), "file": tr("檔案"),
    }
_CHAR_WIDTHS = {
    "id": 195, "faction": 120, "clan": 144, "culture": 105, "occ": 100,
    "age": 55, "gender": 62, "married": 62, "alive": 62, "file": 62,
}


def _build_char_subtab(app, sub: ttk.Notebook) -> None:
    frame = ttk.Frame(sub)
    sub.add(frame, text=tr("👤 角色"))

    # Filter vars.
    app._db_search_var = tk.StringVar()
    app._db_faction_var = tk.StringVar(value=tr("全部陣營"))
    app._db_clan_var = tk.StringVar(value=tr("全部氏族"))
    app._db_culture_var = tk.StringVar(value=tr("全部文化"))
    app._db_occ_var = tk.StringVar(value=tr("全部職業"))
    app._db_file_var = tk.StringVar(value=tr("檔案：全部"))
    app._db_type_lord_var = tk.BooleanVar(value=True)
    app._db_type_wanderer_var = tk.BooleanVar(value=True)
    app._db_type_notable_var = tk.BooleanVar(value=True)
    app._db_type_leader_var = tk.BooleanVar(value=True)

    # Row 1: search + faction/clan/culture/occupation.
    r1 = ttk.Frame(frame)
    r1.pack(fill=tk.X, padx=6, pady=(6, 2))
    ttk.Label(r1, text="🔍").pack(side=tk.LEFT)
    e = ttk.Entry(r1, textvariable=app._db_search_var, width=18)
    e.pack(side=tk.LEFT, padx=(2, 8))
    e.bind("<KeyRelease>", lambda ev: _debounce_char_tree(app))
    app._db_faction_combo = _filter_combo(app, r1, app._db_faction_var, [tr("全部陣營")])
    app._db_clan_combo = _filter_combo(app, r1, app._db_clan_var, [tr("全部氏族")])
    app._db_culture_combo = _filter_combo(app, r1, app._db_culture_var, [tr("全部文化")])
    app._db_occ_combo = _filter_combo(app, r1, app._db_occ_var, [tr("全部職業")])
    # Faction change re-scopes the clan list.
    app._db_faction_combo.bind("<<ComboboxSelected>>",
                               lambda ev: (_refresh_char_clan_options(app), _refresh_char_tree(app)))

    # Row 2: type toggles + file-status + exclude-template + count.
    r2 = ttk.Frame(frame)
    r2.pack(fill=tk.X, padx=6, pady=(0, 2))
    ttk.Label(r2, text=tr("顯示:"), foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)
    for _t, _v in ((tr("貴族"), app._db_type_lord_var), (tr("浪人"), app._db_type_wanderer_var),
                   (tr("顯要"), app._db_type_notable_var), (tr("領袖"), app._db_type_leader_var)):
        ttk.Checkbutton(r2, text=_t, variable=_v,
                        command=lambda: _refresh_char_tree(app)).pack(side=tk.LEFT, padx=(0, 2))
    app._db_file_combo = ttk.Combobox(
        r2, textvariable=app._db_file_var, state="readonly", width=10,
        values=[tr("檔案：全部"), tr("僅有檔"), tr("僅無檔")])
    app._db_file_combo.pack(side=tk.LEFT, padx=(8, 4))
    app._db_file_combo.bind("<<ComboboxSelected>>", lambda ev: _refresh_char_tree(app))
    app._db_exclude_template_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(r2, text=tr("排除模板"), variable=app._db_exclude_template_var,
                    command=lambda: app._refresh_database()).pack(side=tk.LEFT, padx=(4, 0))
    app._db_count_var = tk.StringVar(value="")
    ttk.Label(r2, textvariable=app._db_count_var, foreground=tcol("#888888")).pack(side=tk.RIGHT)

    # Tree.
    tree_wrap = ttk.Frame(frame)
    tree_wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 2))
    tree = ttk.Treeview(tree_wrap, columns=_CHAR_COLS, show="tree headings",
                        selectmode="extended")
    tree.heading("#0", text=tr("名稱"))
    tree.column("#0", width=160, stretch=False)
    for c in _CHAR_COLS:
        tree.heading(c, text=_char_heads()[c])
        tree.column(c, width=_CHAR_WIDTHS[c], anchor="center", stretch=False)
    vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    tree_wrap.rowconfigure(0, weight=1)
    tree_wrap.columnconfigure(0, weight=1)
    tree.bind("<<TreeviewSelect>>", lambda ev: _sync_char_actions(app))
    _make_sortable(tree, numeric_cols={"age"})
    _bind_copy(app, tree, id_col="id")
    app._db_char_tree = tree

    # Action bar — order: 生成 / 編輯 / 重置 / 刪除 / 備份.
    bar = ttk.Frame(frame)
    bar.pack(fill=tk.X, padx=6, pady=(0, 6))
    ttk.Label(bar, text=tr("選取角色："), foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)
    app._db_gen_btn = ttk.Button(bar, text=tr("➕ 生成"), style="success.TButton",
                                 command=lambda: app._db_generate_rows(_selected_rows(app)))
    app._db_edit_btn = ttk.Button(bar, text=tr("✏ 編輯"), style="info.TButton",
                                  command=lambda: app._db_edit_rows(_selected_rows(app)))
    app._db_reset_btn = ttk.Button(bar, text=tr("♻ 重置"), style="warning.TButton",
                                   command=lambda: app._db_reset_rows(_selected_rows(app)))
    app._db_del_btn = ttk.Button(bar, text=tr("🗑 刪除"), style="danger.TButton",
                                 command=lambda: app._db_delete_rows(_selected_rows(app)))
    app._db_bak_btn = ttk.Button(bar, text=tr("📁 備份"), style="secondary.TButton",
                                 command=lambda: app._db_backup_rows(_selected_rows(app)))
    for b in (app._db_gen_btn, app._db_edit_btn, app._db_reset_btn, app._db_del_btn, app._db_bak_btn):
        b.pack(side=tk.LEFT, padx=2)
    app._db_action_hint_var = tk.StringVar(value=tr("雙擊 ID／名稱可複製；點欄位標題可排序"))
    ttk.Label(bar, textvariable=app._db_action_hint_var,
              foreground=tcol("#999999")).pack(side=tk.LEFT, padx=(8, 0))
    _sync_char_actions(app)


def _filter_combo(app, parent, var, values):
    cb = ttk.Combobox(parent, textvariable=var, state="readonly", width=11, values=values)
    cb.pack(side=tk.LEFT, padx=(0, 4))
    cb.bind("<<ComboboxSelected>>", lambda ev: _refresh_char_tree(app))
    return cb


def _debounce_char_tree(app):
    aid = getattr(app, "_db_filter_after", None)
    if aid:
        app.root.after_cancel(aid)
    app._db_filter_after = app.root.after(250, lambda: _refresh_char_tree(app))


def _refresh_char_filter_options(app) -> None:
    """Rebuild faction/culture/occupation dropdowns from the current rows."""
    rows = app.db_rows
    term = app.terminology_campaign if isinstance(app.terminology_campaign, dict) else {}
    kdom_names = term.get("kingdoms") or {}
    cult_names = term.get("cultures") or {}

    # Factions present.
    kingdoms, has_minor = set(), False
    cultures, occs = set(), set()
    for r in rows:
        if r.get("Kingdom"):
            kingdoms.add(r["Kingdom"])
        else:
            has_minor = True
        if r.get("Culture"):
            cultures.add(r["Culture"])
        if r.get("Occupation"):
            occs.add(r["Occupation"])

    app._db_faction_map = {tr("全部陣營"): None}
    fopts = [tr("全部陣營")]
    for kid in sorted(kingdoms, key=lambda x: str(kdom_names.get(x, x))):
        lbl = str(kdom_names.get(kid, kid))
        disp = lbl if lbl not in app._db_faction_map else f"{lbl} [{kid}]"
        app._db_faction_map[disp] = kid
        fopts.append(disp)
    if has_minor:
        app._db_faction_map[tr("無陣營")] = "__minor__"
        fopts.append(tr("無陣營"))
    app._db_faction_combo.configure(values=fopts)
    if app._db_faction_var.get() not in app._db_faction_map:
        app._db_faction_var.set(tr("全部陣營"))

    app._db_culture_map = {tr("全部文化"): None}
    copts = [tr("全部文化")]
    for cid in sorted(cultures, key=lambda x: str(cult_names.get(x, x))):
        lbl = str(cult_names.get(cid, cid))
        app._db_culture_map[lbl] = cid
        copts.append(lbl)
    app._db_culture_combo.configure(values=copts)
    if app._db_culture_var.get() not in app._db_culture_map:
        app._db_culture_var.set(tr("全部文化"))

    app._db_occ_map = {tr("全部職業"): None}
    oopts = [tr("全部職業")]
    for o in sorted(occs, key=lambda x: _occ_label(x)):
        app._db_occ_map[_occ_label(o)] = o
        oopts.append(_occ_label(o))
    app._db_occ_combo.configure(values=oopts)
    if app._db_occ_var.get() not in app._db_occ_map:
        app._db_occ_var.set(tr("全部職業"))

    _refresh_char_clan_options(app)


def _refresh_char_clan_options(app) -> None:
    term = app.terminology_campaign if isinstance(app.terminology_campaign, dict) else {}
    clan_names = term.get("clans") or {}
    fid = (getattr(app, "_db_faction_map", {}) or {}).get(app._db_faction_var.get())
    clans = set()
    for r in app.db_rows:
        cl = r.get("Clan")
        if not cl:
            continue
        k = r.get("Kingdom")
        if fid == "__minor__":
            if k:
                continue
        elif fid is not None and k != fid:
            continue
        clans.add(cl)
    app._db_clan_map = {tr("全部氏族"): None}
    opts = [tr("全部氏族")]
    for cid in sorted(clans, key=lambda x: str(clan_names.get(x, x))):
        lbl = str(clan_names.get(cid, cid))
        disp = lbl if lbl not in app._db_clan_map else f"{lbl} [{cid}]"
        app._db_clan_map[disp] = cid
        opts.append(disp)
    app._db_clan_combo.configure(values=opts)
    if app._db_clan_var.get() not in app._db_clan_map:
        app._db_clan_var.set(tr("全部氏族"))


def _db_filtered_rows(app) -> List[Dict[str, Any]]:
    rows = app.db_rows
    term_l = app._db_search_var.get().strip().lower()
    fid = (getattr(app, "_db_faction_map", {}) or {}).get(app._db_faction_var.get())
    cid = (getattr(app, "_db_clan_map", {}) or {}).get(app._db_clan_var.get())
    cult = (getattr(app, "_db_culture_map", {}) or {}).get(app._db_culture_var.get())
    occ = (getattr(app, "_db_occ_map", {}) or {}).get(app._db_occ_var.get())
    fstate = app._db_file_var.get()
    t_lord = app._db_type_lord_var.get()
    t_wand = app._db_type_wanderer_var.get()
    t_note = app._db_type_notable_var.get()
    t_lead = app._db_type_leader_var.get()

    out = []
    for r in rows:
        if not t_lord and r.get("IsLord"):
            continue
        if not t_wand and r.get("IsWanderer"):
            continue
        if not t_note and r.get("IsNotable"):
            continue
        if not t_lead and r.get("IsClanLeader"):
            continue
        if fid == "__minor__":
            if r.get("Kingdom"):
                continue
        elif fid is not None and r.get("Kingdom") != fid:
            continue
        if cid is not None and r.get("Clan") != cid:
            continue
        if cult is not None and r.get("Culture") != cult:
            continue
        if occ is not None and r.get("Occupation") != occ:
            continue
        if fstate == tr("僅有檔") and not r.get("HasFile"):
            continue
        if fstate == tr("僅無檔") and r.get("HasFile"):
            continue
        if term_l:
            hay = (str(r.get("Name", "")).lower() + " " + str(r.get("StringId", "")).lower())
            if term_l not in hay:
                continue
        out.append(r)
    return out


def _refresh_char_tree(app) -> None:
    tree = getattr(app, "_db_char_tree", None)
    if tree is None:
        return
    # Preserve selection + scroll across the rebuild so an action (generate /
    # delete / backup …) doesn't drop the user's place.  iids are StringIds, so
    # rows that still exist (delete only flips HasFile) stay selected.
    prev_sel = list(tree.selection())
    prev_top = tree.yview()[0]
    rows = _db_filtered_rows(app)
    rows.sort(key=lambda r: (str(r.get("Name") or "").lower(), str(r.get("StringId"))))
    tree.delete(*tree.get_children())
    app._db_row_by_id = {}
    # Cap rendering for responsiveness; the count label shows the true total.
    shown = rows[:2000]
    for r in shown:
        sid = r["StringId"]
        app._db_row_by_id[sid] = r
        tree.insert(
            "", "end", iid=sid, text=str(r.get("Name") or sid),
            values=(
                sid,
                r.get("KingdomName") or (tr("無陣營") if r.get("HasAttrs", True) and not r.get("Kingdom") else ""),
                r.get("ClanName") or "",
                r.get("CultureName") or "",
                _occ_label(r.get("Occupation")),
                "" if r.get("Age") is None else r.get("Age"),
                _gender_label(r.get("Gender")),
                _yn(r.get("Married")),
                _yn(r.get("Alive")),
                "✓" if r.get("HasFile") else "✗",
            ),
        )
    # Restore prior selection + scroll for rows that still exist.
    keep = [s for s in prev_sel if s in app._db_row_by_id]
    if keep:
        tree.selection_set(keep)
        tree.focus(keep[0])
    tree.yview_moveto(prev_top)

    total = len(rows)
    have = sum(1 for r in rows if r.get("HasFile"))
    extra = tr("（僅顯示前 2000）") if total > len(shown) else ""
    app._db_count_var.set(tr("符合 {n} 筆 · 有檔 {h}").format(n=total, h=have) + extra)
    _sync_char_actions(app)


def _selected_rows(app) -> List[Dict[str, Any]]:
    tree = getattr(app, "_db_char_tree", None)
    if tree is None:
        return []
    by = getattr(app, "_db_row_by_id", {}) or {}
    return [by[i] for i in tree.selection() if i in by]


def _sync_char_actions(app) -> None:
    rows = _selected_rows(app)
    any_file = any(r.get("HasFile") for r in rows)
    any_nofile = any(not r.get("HasFile") for r in rows)
    app._db_reset_btn.configure(state="normal" if any_file else "disabled")
    app._db_del_btn.configure(state="normal" if any_file else "disabled")
    app._db_bak_btn.configure(state="normal" if any_file else "disabled")
    app._db_edit_btn.configure(state="normal" if any_file else "disabled")
    app._db_gen_btn.configure(state="normal" if any_nofile else "disabled")
    # Soft, non-blocking note when the game is running (generation may rarely be
    # overwritten on load — see the reverse-engineered cache behaviour).
    if hasattr(app, "_db_action_hint_var"):
        gs = getattr(app, "_game_status", None)
        running = bool(gs is not None and getattr(gs, "running", False))
        app._db_action_hint_var.set(
            tr("⚠ 遊戲執行中生成的角色檔，少數情況下載入時可能被沖掉；建議在主選單／載入戰役前生成")
            if running else tr("雙擊 ID／名稱可複製；點欄位標題可排序"))


# ── 王國 / 氏族 / 文化 sub-tabs (list + batch generate) ──────────────────────

def _build_entity_subtab(app, sub: ttk.Notebook, kind: str, title: str) -> None:
    frame = ttk.Frame(sub)
    sub.add(frame, text=title)
    store = getattr(app, "_db_entity_widgets", None)
    if store is None:
        store = app._db_entity_widgets = {}

    top = ttk.Frame(frame)
    top.pack(fill=tk.X, padx=6, pady=(6, 2))
    ttk.Label(top, foreground=tcol("#6B5B3E"),
              text=tr("選一項後可批量生成其角色資料（自動跳過已有檔）。")).pack(side=tk.LEFT)
    gen_btn = ttk.Button(top, text=tr("📦 批量生成角色資料"), style="success.TButton",
                         command=lambda: _open_batch_dialog(app, kind))
    gen_btn.pack(side=tk.RIGHT)

    wrap = ttk.Frame(frame)
    wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
    tree = ttk.Treeview(wrap, columns=("id", "total", "have"), show="tree headings",
                        selectmode="browse")
    tree.heading("#0", text=tr("名稱"))
    tree.heading("id", text="ID")
    tree.heading("total", text=tr("角色數"))
    tree.heading("have", text=tr("有檔"))
    tree.column("#0", width=200, stretch=False)
    tree.column("id", width=160, stretch=False)
    tree.column("total", width=70, anchor="center", stretch=False)
    tree.column("have", width=70, anchor="center", stretch=False)
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.bind("<<TreeviewSelect>>", lambda ev: _sync_entity_btn(app, kind))
    _make_sortable(tree, numeric_cols={"total", "have"})
    _bind_copy(app, tree, id_col="id")
    store[kind] = {"tree": tree, "gen_btn": gen_btn}
    _sync_entity_btn(app, kind)


def _entity_rows_for(app, kind: str, entity_id: str) -> List[Dict[str, Any]]:
    """All character rows belonging to a kingdom/clan/culture id."""
    key = {"kingdom": "Kingdom", "clan": "Clan", "culture": "Culture"}[kind]
    if kind == "kingdom" and entity_id == "__minor__":
        return [r for r in app.db_rows if not r.get("Kingdom")]
    return [r for r in app.db_rows if r.get(key) == entity_id]


def _refresh_entity_lists(app) -> None:
    store = getattr(app, "_db_entity_widgets", {}) or {}
    term = app.terminology_campaign if isinstance(app.terminology_campaign, dict) else {}
    name_maps = {"kingdom": term.get("kingdoms") or {},
                 "clan": term.get("clans") or {},
                 "culture": term.get("cultures") or {}}
    key_of = {"kingdom": "Kingdom", "clan": "Clan", "culture": "Culture"}
    for kind, w in store.items():
        tree = w["tree"]
        tree.delete(*tree.get_children())
        names = name_maps[kind]
        key = key_of[kind]
        present: Dict[str, Dict[str, int]] = {}
        minor = {"total": 0, "have": 0}
        for r in app.db_rows:
            eid = r.get(key)
            if kind == "kingdom" and not eid:
                minor["total"] += 1
                minor["have"] += 1 if r.get("HasFile") else 0
                continue
            if not eid:
                continue
            slot = present.setdefault(eid, {"total": 0, "have": 0})
            slot["total"] += 1
            slot["have"] += 1 if r.get("HasFile") else 0
        for eid in sorted(present, key=lambda x: str(names.get(x, x))):
            s = present[eid]
            tree.insert("", "end", iid=eid, text=str(names.get(eid, eid)),
                        values=(eid, s["total"], s["have"]))
        if kind == "kingdom" and minor["total"]:
            tree.insert("", "end", iid="__minor__", text=tr("無陣營"),
                        values=("__minor__", minor["total"], minor["have"]))
        _sync_entity_btn(app, kind)


def _sync_entity_btn(app, kind: str) -> None:
    store = getattr(app, "_db_entity_widgets", {}) or {}
    w = store.get(kind)
    if not w:
        return
    w["gen_btn"].configure(state="normal" if w["tree"].selection() else "disabled")


def _open_batch_dialog(app, kind: str) -> None:
    store = getattr(app, "_db_entity_widgets", {}) or {}
    w = store.get(kind)
    if not w or not w["tree"].selection():
        return
    eid = w["tree"].selection()[0]
    entity_name = w["tree"].item(eid, "text")
    rows = _entity_rows_for(app, kind, eid)

    win = tk.Toplevel(app.root)
    win.title(tr("批量生成角色資料"))
    W, H = 460, 340
    win.transient(app.root)
    try:
        app._center_window(win, W, H)
    except Exception:
        win.geometry(f"{W}x{H}")
    win.grab_set()

    ttk.Label(win, text=tr("批量生成：{name}").format(name=entity_name),
              font=("", 13, "bold")).pack(anchor="w", padx=14, pady=(14, 2))
    ttk.Label(win, foreground=tcol("#888888"), wraplength=W - 28, justify="left",
              text=tr("為此範圍內「尚無存檔」的角色生成空白角色檔（完全重置後的乾淨狀態），"
                      "已有檔者一律跳過、不覆蓋。")).pack(anchor="w", padx=14)
    ttk.Label(win, foreground=tcol("#A15C00"), wraplength=W - 28, justify="left",
              text=tr("提示：若在戰役載入中生成，少數情況下可能被遊戲沖掉；"
                      "建議在主選單／載入戰役前生成。")).pack(anchor="w", padx=14, pady=(2, 0))

    ex_minor = tk.BooleanVar(value=True)
    ex_dead = tk.BooleanVar(value=False)
    ex_note = tk.BooleanVar(value=False)
    ex_wand = tk.BooleanVar(value=False)
    box = ttk.LabelFrame(win, text=tr("排除選項"))
    box.pack(fill=tk.X, padx=14, pady=(10, 6))
    count_var = tk.StringVar()

    def _excl() -> Dict[str, bool]:
        return dict(exclude_minor=ex_minor.get(), exclude_dead=ex_dead.get(),
                    exclude_notable=ex_note.get(), exclude_wanderer=ex_wand.get())

    def _update_count(*_a):
        n = _svc_chardb.count_generatable(rows, **_excl())
        count_var.set(tr("將生成 {n} 個角色檔").format(n=n))

    for _t, _v in ((tr("排除未成年（<18）"), ex_minor), (tr("排除已歿"), ex_dead),
                   (tr("排除顯要"), ex_note), (tr("排除浪人"), ex_wand)):
        ttk.Checkbutton(box, text=_t, variable=_v, command=_update_count).pack(anchor="w", padx=10, pady=1)

    ttk.Label(win, textvariable=count_var, foreground=tcol("#1A6FA0"),
              font=("", 11, "bold")).pack(anchor="w", padx=14, pady=(2, 6))
    _update_count()

    bar = ttk.Frame(win)
    bar.pack(fill=tk.X, padx=14, pady=(4, 12))

    def _go():
        win.destroy()
        app._db_batch_generate(rows, _excl())

    ttk.Button(bar, text=tr("開始生成"), command=_go, style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(bar, text=tr("取消"), command=win.destroy, style="secondary.TButton").pack(side=tk.RIGHT)


# ── 兵種 / 物品 / 定居點 viewers ─────────────────────────────────────────────

def _build_viewer_subtab(app, sub: ttk.Notebook, kind: str, title: str) -> None:
    frame = ttk.Frame(sub)
    sub.add(frame, text=title)
    store = getattr(app, "_db_viewer_widgets", None)
    if store is None:
        store = app._db_viewer_widgets = {}

    top = ttk.Frame(frame)
    top.pack(fill=tk.X, padx=6, pady=(6, 2))
    ttk.Label(top, text="🔍").pack(side=tk.LEFT)
    var = tk.StringVar()
    ent = ttk.Entry(top, textvariable=var, width=20)
    ent.pack(side=tk.LEFT, padx=(2, 8))
    cnt = tk.StringVar()
    ttk.Label(top, textvariable=cnt, foreground=tcol("#888888")).pack(side=tk.RIGHT)

    wrap = ttk.Frame(frame)
    wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
    cols = ("id", "extra")
    tree = ttk.Treeview(wrap, columns=cols, show="tree headings", selectmode="browse")
    tree.heading("#0", text=tr("名稱"))
    tree.heading("id", text="ID")
    extra_head = {"troops": tr("階級"), "items": tr("文化"), "settlements": tr("類型")}[kind]
    tree.heading("extra", text=extra_head)
    tree.column("#0", width=220, stretch=False)
    tree.column("id", width=200, stretch=False)
    tree.column("extra", width=90, anchor="center", stretch=False)
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    _make_sortable(tree, numeric_cols={"extra"} if kind == "troops" else ())
    _bind_copy(app, tree, id_col="id")
    store[kind] = {"tree": tree, "search": var, "count": cnt}
    ent.bind("<KeyRelease>", lambda ev: _refresh_one_viewer(app, kind))


def _settle_type() -> dict:
    return {"town": tr("城鎮"), "castle": tr("城堡"), "village": tr("村莊"), "other": tr("其他")}


def _refresh_viewers(app) -> None:
    for kind in (getattr(app, "_db_viewer_widgets", {}) or {}):
        _refresh_one_viewer(app, kind)


def _refresh_one_viewer(app, kind: str) -> None:
    store = getattr(app, "_db_viewer_widgets", {}) or {}
    w = store.get(kind)
    if not w:
        return
    term = app.terminology_campaign if isinstance(app.terminology_campaign, dict) else {}
    attr_key = {"troops": "troop_attrs", "items": "item_attrs", "settlements": "settlement_attrs"}[kind]
    data = term.get(attr_key) or {}
    q = w["search"].get().strip().lower()
    tree = w["tree"]
    tree.delete(*tree.get_children())
    items = []
    for sid, a in data.items():
        if not isinstance(a, dict):
            a = {"name": a}
        name = str(a.get("name") or sid)
        if q and q not in name.lower() and q not in str(sid).lower():
            continue
        if kind == "troops":
            extra = a.get("tier", "")
        elif kind == "items":
            extra = (term.get("cultures") or {}).get(a.get("culture"), a.get("culture") or "")
        else:
            extra = _settle_type().get(a.get("type"), a.get("type") or "")
        items.append((name, str(sid), extra))
    items.sort(key=lambda x: x[0].lower())
    for name, sid, extra in items[:3000]:
        tree.insert("", "end", iid=sid, text=name, values=(sid, extra))
    w["count"].set(tr("共 {n} 筆").format(n=len(items)))
