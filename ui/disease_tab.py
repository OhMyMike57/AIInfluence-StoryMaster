"""Top-level Disease management tab.

Layout (v0.25.0 — aligned with 動態事件 top bar + 資料庫 bottom action row)
------
  Top action bar : ☐ 編輯模式 · 🔄 重新載入 · 🔍 有效檢查 · 🧹 清空所有疾病
                   ……（右）N 暫存 · ↩ 取消 · 💾 儲存（僅有變更時顯示）
  Top half       : left = disease catalog (Listbox)
                   right = selected disease details + 🩹 清空此病種感染 / 🗑 刪除此病種
  Infection list : filter row + multi-select Treeview (heroes / troops / prisoners)
  Bottom bar     : ＋ 添加感染英雄 ｜ 選取角色：－ 移除疾病

Edit mode is the app-wide shared ``app.edit_mode_var`` (toggling here flips it on
the 動態事件 / 訊息與秘密 tabs too).  When edit mode is OFF every editing button is
greyed out; reload + validity check stay enabled.

All disease *catalog* operations now route through the staging buffer
(``app.disease_pending``) so 💾 儲存 / ↩ 取消 cover them — only 🧹 清空所有疾病
remains an immediate, campaign-level reset.

Builder::

    build_disease_tab(app, notebook)

Callbacks expected on *app*:
    app.diseases                  List[dict]   — loaded by reload_world_data()
    app.disease_instances         List[dict]   — loaded by reload_world_data()
    app.disease_pending           List[dict]   — staging buffer
    app.edit_mode_var             tk.BooleanVar — shared edit-mode flag
    app._disease_remove(inst)             stage a remove (toggle)
    app._disease_remove_selected(rows)    batch stage removes for selected rows
    app._disease_assign()                 open the assign dialog
    app._disease_clear_infections_for(id) stage clear-infections-of-disease
    app._disease_purge_definition(id)     stage purge-disease-definition
    app._disease_validity_check()
    app._disease_clear_all()              immediate campaign-level wipe
    app._disease_commit() / _disease_discard() / _disease_refresh_action_bar()
"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Any, Optional

from i18n import tr
from services.disease_service import disease_definition, hero_instances
from services.time_format import format_game_time
from ui import preview_font
from ui.theme import paint, labeled_frame
from ui.tree_helpers import make_sortable
from ui.theme import tcol


# ── Player party detection helpers ────────────────────────────────────────────
PLAYER_PARTY_ID = "player_party"
# `lord_4_24_party_1` → owner sid `lord_4_24`
_PARTY_OWNER_RE = re.compile(r"^(.+)_party_\d+$")


def _party_owner_sid(party_id: str) -> Optional[str]:
    """Return the owner-hero StringId encoded in *party_id*, or None.

    Hero-led parties carry the format ``<hero_sid>_party_<n>`` (e.g.
    ``lord_4_24_party_1``).  Generic / faction / bandit parties (e.g.
    ``looters_293``) won't match and return None.
    """
    if not party_id:
        return None
    m = _PARTY_OWNER_RE.match(str(party_id))
    return m.group(1) if m else None


def _sid_to_display(app, sid: str) -> Optional[str]:
    """Lookup display name for a StringId via ``app.character_meta``."""
    if not sid:
        return None
    meta_map = getattr(app, "character_meta", None) or {}
    for display, meta in meta_map.items():
        if isinstance(meta, dict) and meta.get("StringId") == sid:
            return display
    return None


def _is_hero_in_player_party(app, sid: str) -> bool:
    """True iff the hero with this sid has IsInPlayerParty=True."""
    display = _sid_to_display(app, sid)
    if not display:
        return False
    meta = (app.character_meta or {}).get(display, {})
    return bool(meta.get("IsInPlayerParty", False))


def _is_hero_favorited(app, sid: str) -> bool:
    """True iff the hero with this sid is in app.favorites (which keys by display)."""
    favorites = getattr(app, "favorites", None) or set()
    display = _sid_to_display(app, sid)
    return bool(display) and (display in favorites)


# ── Target-type categories (DiseaseTargetType, confirmed by 5.0.2 decompile) ──
# 0 = 英雄 (Hero personal infection)
# 1 = 部隊士兵 (PartyTroops — soldiers in a party)
# 2 = 部隊俘虜 (PartyPrisoners — prisoners in a party)
HERO_TARGET_TYPE = 0
TROOPS_TARGET_TYPE = 1
PRISONER_TARGET_TYPE = 2
PARTY_TARGET_TYPES = (TROOPS_TARGET_TYPE, PRISONER_TARGET_TYPE)


def _is_hero(inst: dict) -> bool:
    return inst.get("target_type") == HERO_TARGET_TYPE


def _is_party(inst: dict) -> bool:
    return inst.get("target_type") in PARTY_TARGET_TYPES


def _is_troops(inst: dict) -> bool:
    return inst.get("target_type") == TROOPS_TARGET_TYPE


def _is_prisoners(inst: dict) -> bool:
    return inst.get("target_type") == PRISONER_TARGET_TYPE


def _all_target_instances(instances):
    """Return only instances we care about — heroes + parties."""
    return [
        x for x in (instances or [])
        if x.get("target_type") in (HERO_TARGET_TYPE,) + PARTY_TARGET_TYPES
    ]


def build_disease_tab(app, notebook: ttk.Notebook) -> None:
    """Build and register the 🦠 疾病 tab onto *notebook*."""
    tab = ttk.Frame(notebook)
    notebook.add(tab, text=tr("🦠 疾病"))
    app._disease_tab = tab
    app._disease_selected_id: Optional[str] = None

    # ── Top action bar (aligned with 動態事件) ────────────────────────────────
    abar = ttk.Frame(tab)
    abar.pack(fill=tk.X, padx=8, pady=(8, 4))

    # LEFT: edit mode (shared) + reload + validity + clear-all
    app._disease_edit_cb = ttk.Checkbutton(
        abar, text=tr("編輯模式"),
        variable=app.edit_mode_var,
        command=lambda: _disease_toggle_edit_mode(app),
    )
    app._disease_edit_cb.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(abar, text=tr("🔄 重新載入"),
               command=lambda: _reload_disease_tab(app),
               style="info.TButton").pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(abar, text=tr("🔍 有效檢查"),
               command=lambda: app._disease_validity_check(),
               style="info.TButton").pack(side=tk.LEFT, padx=(0, 4))
    app._disease_clear_all_btn = ttk.Button(
        abar, text=tr("🧹 清空所有疾病"),
        command=lambda: app._disease_clear_all(),
        style="danger.TButton",
    )
    app._disease_clear_all_btn.pack(side=tk.LEFT, padx=(0, 4))

    # RIGHT: staging badge + 取消 + 儲存 (packed by _disease_refresh_action_bar).
    app._disease_cancel_btn = ttk.Button(
        abar, text=tr("↩ 取消"),
        command=lambda: app._disease_discard(),
        style="secondary.TButton",
    )
    app._disease_save_btn = ttk.Button(
        abar, text=tr("💾 儲存"),
        command=lambda: app._disease_commit(),
        style="success.TButton",
    )
    app._disease_pending_var = tk.StringVar(value="")
    # paint(): constructor colours are dropped under ttkbootstrap, which left
    # this badge rendering as ordinary text instead of an orange pill.
    app._disease_pending_lbl = paint(
        tk.Label(abar, textvariable=app._disease_pending_var,
                 font=("", 9, "bold"), padx=6, pady=1),
        foreground=tcol("#FFFFFF"), background=tcol("#E67E22"))
    app._disease_save_btn_pack_kwargs   = dict(side=tk.RIGHT, padx=(0, 4))
    app._disease_cancel_btn_pack_kwargs = dict(side=tk.RIGHT, padx=(0, 4))
    app._disease_pending_lbl_pack_kwargs = dict(side=tk.RIGHT, padx=(0, 4))

    # Keep button greying in sync with the shared edit-mode flag (the world /
    # dynamic-events tabs add their own traces to the same var).
    app.edit_mode_var.trace_add("write", lambda *_: _disease_apply_edit_ui(app))

    # ── Top section: catalog (left) + details (right) ─────────────────────────
    top = ttk.Frame(tab)
    top.pack(fill=tk.X, expand=False, padx=8, pady=(0, 4))
    # The catalog + detail panel is a fixed, SHORT band — the infection list
    # below it gets the rest.  Children are grid-managed, so grid_propagate(False)
    # (NOT pack_propagate) is what pins the height; otherwise the tall 3-column
    # detail texts stretch this band and swallow the infection list.
    top.configure(height=210)
    top.grid_propagate(False)
    # Catalog 25% / details 75% — the catalog is a short list, details needs room.
    top.columnconfigure(0, weight=1, uniform="dz")
    top.columnconfigure(1, weight=3, uniform="dz")
    top.rowconfigure(0, weight=1)

    # LEFT — disease catalog listbox (25%)
    cat_frame = labeled_frame(top, text=tr("疾病目錄（唯讀）"))
    cat_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

    ttk.Label(
        cat_frame,
        text=tr("📖 疾病目錄（由遊戲 AI 動態生成，僅供檢視）"),
        foreground=tcol("#6B5B3E"),
        font=("Microsoft JhengHei", 9, "italic"),
    ).pack(anchor="w", padx=6, pady=(2, 0))

    cat_inner = ttk.Frame(cat_frame)
    cat_inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    app._disease_lb = tk.Listbox(cat_inner, exportselection=False, activestyle="dotbox")
    cat_vsb = ttk.Scrollbar(cat_inner, orient="vertical", command=app._disease_lb.yview)
    app._disease_lb.configure(yscrollcommand=cat_vsb.set)
    app._disease_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    cat_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    app._disease_lb.bind("<<ListboxSelect>>", lambda e: _on_disease_select(app))

    # RIGHT — disease details (75%) + catalog edit buttons
    det_frame = labeled_frame(top, text=tr("疾病詳情"))
    det_frame.grid(row=0, column=1, sticky="nsew")

    # Action row: edits that apply to the SELECTED disease in the catalog.
    # v0.25.0 — these now STAGE (toggle) instead of writing immediately, and
    # are renamed to disambiguate from the bottom-bar 「－ 移除疾病」.
    det_action = ttk.Frame(det_frame)
    det_action.pack(fill=tk.X, padx=4, pady=(2, 2))
    app._disease_clear_inf_btn = ttk.Button(
        det_action, text=tr("🩹 清空此病種感染"),
        command=lambda: app._disease_clear_infections_for(app._disease_selected_id or ""),
        style="warning.TButton", state="disabled",
    )
    app._disease_clear_inf_btn.pack(side=tk.LEFT, padx=(0, 4))
    app._disease_purge_btn = ttk.Button(
        det_action, text=tr("🗑 刪除此病種"),
        command=lambda: app._disease_purge_definition(app._disease_selected_id or ""),
        style="danger.TButton", state="disabled",
    )
    app._disease_purge_btn.pack(side=tk.LEFT, padx=(0, 4))

    # Detail body — 3 columns side-by-side (屬性 ｜ 效果 ｜ 描述) so the wide,
    # short panel is used well instead of one tall scrolling column.
    det_grid = ttk.Frame(det_frame)
    det_grid.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    det_grid.rowconfigure(0, weight=1)
    app._disease_detail_cols = []
    for i in range(3):
        det_grid.columnconfigure(i, weight=1, uniform="ddet")
        cell = ttk.Frame(det_grid)
        cell.grid(row=0, column=i, sticky="nsew", padx=(0, 4) if i < 2 else 0)
        cell.rowconfigure(0, weight=1)
        cell.columnconfigure(0, weight=1)
        t = tk.Text(cell, wrap="word", state="disabled",
                    font=("Microsoft JhengHei", 10), relief="flat")
        vsb = ttk.Scrollbar(cell, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=vsb.set)
        t.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        _config_disease_detail_tags(t)
        preview_font.register(t)
        app._disease_detail_cols.append(t)
    # Back-compat alias (first column).
    app._disease_detail_text = app._disease_detail_cols[0]

    # ── Infection list section ────────────────────────────────────────────────
    ttk.Separator(tab, orient="horizontal").pack(fill=tk.X, padx=8, pady=(0, 4))

    inf_frame = labeled_frame(tab, text=tr("感染清單"))
    inf_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

    # ── Filter row ────────────────────────────────────────────────────────────
    filt = ttk.Frame(inf_frame)
    filt.pack(fill=tk.X, padx=6, pady=(4, 4))

    # Search by name / id / disease
    ttk.Label(filt, text="🔍").pack(side=tk.LEFT, padx=(0, 2))
    app._disease_filter_kw = tk.StringVar(value="")
    kw_entry = ttk.Entry(filt, textvariable=app._disease_filter_kw, width=20)
    kw_entry.pack(side=tk.LEFT, padx=(0, 8))
    app._disease_filter_kw.trace_add("write",
                                     lambda *_: _populate_infection_list(app))

    # Target kind: 全部 / 英雄 / 部隊士兵 / 部隊俘虜 / 玩家隊伍中 (3-way, 5.0.2 research)
    ttk.Label(filt, text=tr("對象:")).pack(side=tk.LEFT)
    app._DISEASE_KIND_ALL          = tr("全部")
    app._DISEASE_KIND_HERO         = tr("英雄")
    app._DISEASE_KIND_TROOPS       = tr("部隊士兵")
    app._DISEASE_KIND_PRISONERS    = tr("部隊俘虜")
    app._DISEASE_KIND_PLAYER_PARTY = tr("玩家隊伍中")
    app._disease_filter_kind = tk.StringVar(value=app._DISEASE_KIND_ALL)
    kind_cb = ttk.Combobox(
        filt, textvariable=app._disease_filter_kind,
        values=[
            app._DISEASE_KIND_ALL,
            app._DISEASE_KIND_HERO,
            app._DISEASE_KIND_TROOPS,
            app._DISEASE_KIND_PRISONERS,
            app._DISEASE_KIND_PLAYER_PARTY,
        ],
        state="readonly", width=10,
    )
    kind_cb.pack(side=tk.LEFT, padx=(2, 8))
    app._disease_filter_kind.trace_add("write",
                                       lambda *_: _populate_infection_list(app))

    # Disease combobox: 全部疾病 / specific disease
    ttk.Label(filt, text=tr("病名:")).pack(side=tk.LEFT)
    app._disease_filter_disease = tk.StringVar(value=app._DISEASE_KIND_ALL)
    app._disease_filter_disease_cb = ttk.Combobox(
        filt, textvariable=app._disease_filter_disease,
        values=[app._DISEASE_KIND_ALL], state="readonly", width=12,
    )
    app._disease_filter_disease_cb.pack(side=tk.LEFT, padx=(2, 8))
    app._disease_filter_disease.trace_add(
        "write", lambda *_: _populate_infection_list(app),
    )

    # Treatment status: 全部 / 治療中 / 未治療
    ttk.Label(filt, text=tr("治療:")).pack(side=tk.LEFT)
    app._DISEASE_TREAT_ALL      = tr("全部")
    app._DISEASE_TREAT_TREATED  = tr("治療中")
    app._DISEASE_TREAT_UNTREAT  = tr("未治療")
    app._disease_filter_treat = tk.StringVar(value=app._DISEASE_TREAT_ALL)
    treat_cb = ttk.Combobox(
        filt, textvariable=app._disease_filter_treat,
        values=[app._DISEASE_TREAT_ALL, app._DISEASE_TREAT_TREATED, app._DISEASE_TREAT_UNTREAT],
        state="readonly", width=6,
    )
    treat_cb.pack(side=tk.LEFT, padx=(2, 8))
    app._disease_filter_treat.trace_add("write",
                                        lambda *_: _populate_infection_list(app))

    # Clear filters (was 「✗ 重置」 — renamed so it doesn't read as a data reset).
    # Sits directly after 治療 instead of floating alone on the right.
    ttk.Button(filt, text=tr("清除篩選"),
               command=lambda: _reset_filters(app),
               style="secondary.TButton").pack(side=tk.LEFT, padx=(0, 0))

    # ── Infection list (Treeview, multi-select) ───────────────────────────────
    list_wrap = ttk.Frame(inf_frame)
    list_wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    columns = ("kind", "target", "disease", "progress", "treated",
               "infected_at", "immunity")
    tv = ttk.Treeview(
        list_wrap, columns=columns, show="headings",
        selectmode="extended", height=16,
    )
    tv.heading("kind",        text=tr("類型"))
    tv.heading("target",      text=tr("對象"))
    tv.heading("disease",     text=tr("病名"))
    tv.heading("progress",    text=tr("進度"))
    tv.heading("treated",     text=tr("治療中"))
    tv.heading("infected_at", text=tr("感染日期"))
    tv.heading("immunity",    text=tr("免疫狀態"))

    tv.column("kind",        width=60,  anchor="center", stretch=False)
    tv.column("target",      width=196, anchor="w",      stretch=True)
    tv.column("disease",     width=165, anchor="w",      stretch=False)
    tv.column("progress",    width=85,  anchor="e",      stretch=False)
    tv.column("treated",     width=60,  anchor="center", stretch=False)
    tv.column("infected_at", width=148, anchor="center", stretch=False)
    tv.column("immunity",    width=130, anchor="w",      stretch=False)

    list_vsb = ttk.Scrollbar(list_wrap, orient="vertical", command=tv.yview)
    list_hsb = ttk.Scrollbar(list_wrap, orient="horizontal", command=tv.xview)
    tv.configure(yscrollcommand=list_vsb.set, xscrollcommand=list_hsb.set)
    tv.grid(row=0, column=0, sticky="nsew")
    list_vsb.grid(row=0, column=1, sticky="ns")
    list_hsb.grid(row=1, column=0, sticky="ew")
    list_wrap.rowconfigure(0, weight=1)
    list_wrap.columnconfigure(0, weight=1)

    # Tags for staging visualization
    # Pending-add = green bold; pending-remove = red + strikethrough (visually
    # paired so staged adds vs removes read at a glance).
    tv.tag_configure("pending_assign", foreground=tcol("#1A7A3F"),
                     font=("Microsoft JhengHei", 10, "bold"))
    tv.tag_configure("pending_remove", foreground=tcol("#C0392B"),
                     font=("Microsoft JhengHei", 10, "overstrike"))
    tv.tag_configure("party",          foreground=tcol("#5D6D7E"))
    tv.tag_configure("hero_immune",    foreground=tcol("#1A6FA0"))
    # Pinned (favorited heroes / player-party / favorited-hero parties).
    tv.tag_configure("pinned",         background=tcol("#FFF7E0"))

    # Selecting rows updates which bottom-bar actions are available.
    tv.bind("<<TreeviewSelect>>", lambda e: _disease_apply_edit_ui(app))

    # Click-to-sort on every column heading (progress sorts numerically).
    make_sortable(tv, numeric_cols={"progress"})

    app._disease_tree = tv

    # ── Bottom action bar (aligned with 資料庫) ───────────────────────────────
    bottom_bar = ttk.Frame(tab)
    bottom_bar.pack(fill=tk.X, padx=8, pady=(0, 8))
    # 「添加感染英雄」 adds a NEW infected hero — it is not an op on the selected
    # rows, so it sits LEFT of the 「選取角色：」 divider.
    app._disease_assign_btn = ttk.Button(
        bottom_bar, text=tr("＋ 添加感染英雄"),
        command=lambda: app._disease_assign(),
        style="warning.TButton", state="disabled",
    )
    app._disease_assign_btn.pack(side=tk.LEFT, padx=(0, 6))
    ttk.Label(bottom_bar, text=tr("選取角色："),
              foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)
    app._disease_remove_sel_btn = ttk.Button(
        bottom_bar, text=tr("－ 移除疾病"),
        command=lambda: app._disease_remove_selected(_selected_disease_rows(app)),
        style="danger.TButton", state="disabled",
    )
    app._disease_remove_sel_btn.pack(side=tk.LEFT, padx=(0, 4))

    app._disease_count_var = tk.StringVar(value="")
    ttk.Label(bottom_bar, textvariable=app._disease_count_var,
              foreground=tcol("#6B5B3E")).pack(side=tk.RIGHT, padx=8)
    ttk.Label(bottom_bar, text=tr("複選後可批量移除；點欄位標題可排序"),
              foreground=tcol("#999999")).pack(side=tk.RIGHT, padx=(0, 8))

    # Initial render + button-state sync.
    refresh_disease_tab(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def refresh_disease_tab(app) -> None:
    """Re-populate both the catalog and the infection list from app state."""
    _populate_catalog(app)
    _refresh_disease_filter_options(app)
    _populate_infection_list(app)
    _disease_apply_edit_ui(app)


# ── Edit-mode gating (shared edit_mode_var) ────────────────────────────────────

def _disease_pending_count(app) -> int:
    if hasattr(app, "_disease_pending_count"):
        try:
            return app._disease_pending_count()
        except Exception:
            pass
    return len(getattr(app, "disease_pending", []) or [])


def _disease_toggle_edit_mode(app) -> None:
    """編輯模式 checkbox command — guard against leaving with unsaved changes.

    UI greying happens via the shared-var trace (``_disease_apply_edit_ui``);
    this handler only runs the pending-changes guard.
    """
    editing = app.edit_mode_var.get()
    if not editing:
        n = _disease_pending_count(app)
        if n > 0:
            from ui.dynamic_events_tab import _ask_save_discard_cancel
            choice = _ask_save_discard_cancel(
                app, tr("有未儲存的變更"),
                tr("目前有 {n} 個尚未儲存的疾病變更。\n\n離開編輯模式前要如何處理？").format(n=n),
            )
            if choice == "cancel":
                app.edit_mode_var.set(True)   # trace re-syncs UI
                return
            elif choice == "save":
                if not app._disease_commit(confirm=False):   # user already chose save
                    app.edit_mode_var.set(True)
                    return
            elif choice == "discard":
                try:
                    app.disease_pending.clear()
                except Exception:
                    app.disease_pending = []
                app._disease_refresh_action_bar()
                refresh_disease_tab(app)
    _disease_apply_edit_ui(app)


def _disease_apply_edit_ui(app) -> None:
    """Grey / un-grey every editing button by edit-mode + selection state."""
    editing = bool(getattr(app, "edit_mode_var", None) and app.edit_mode_var.get())
    tv = getattr(app, "_disease_tree", None)
    has_row_sel = bool(tv is not None and tv.selection())
    has_cat_sel = bool(getattr(app, "_disease_selected_id", None))

    def _set(attr: str, on: bool) -> None:
        btn = getattr(app, attr, None)
        if btn is not None:
            try:
                btn.configure(state="normal" if on else "disabled")
            except tk.TclError:
                pass

    _set("_disease_clear_all_btn", editing)
    _set("_disease_assign_btn",    editing)
    _set("_disease_remove_sel_btn", editing and has_row_sel)
    _set("_disease_clear_inf_btn", editing and has_cat_sel)
    _set("_disease_purge_btn",     editing and has_cat_sel)


def _selected_disease_rows(app) -> list:
    """Instances/pending-sentinels behind the currently-selected infection rows."""
    tv = getattr(app, "_disease_tree", None)
    if tv is None:
        return []
    m = getattr(app, "_disease_inst_map", {}) or {}
    return [m[i] for i in tv.selection() if i in m]


def _reload_disease_tab(app) -> None:
    """Reload campaign data + refresh disease tab. Asks before discarding pending."""
    pending = list(getattr(app, "disease_pending", []) or [])
    if pending:
        from ui import msgbox as _mb
        if not _mb.askyesno(
            tr("有未儲存的變更"),
            tr("重新載入會丟棄目前 {v0} 筆疾病暫存。\n\n要繼續嗎？").format(v0=len(pending)),
            parent=app.root,
        ):
            return
        app.disease_pending = []
    try:
        app.refresh(ask_dirty=False)
    except TypeError:
        app.refresh()
    refresh_disease_tab(app)


def _populate_catalog(app) -> None:
    lb = app._disease_lb
    # Preserve scroll + selection across the rebuild (catalog order is stable).
    prev_top = lb.yview()[0] if lb.size() else 0.0
    prev_sel = lb.curselection()

    diseases = getattr(app, "diseases", [])
    instances = getattr(app, "disease_instances", [])
    pending = list(getattr(app, "disease_pending", []) or [])
    purge_ids = {str(s.get("disease_id", "")) for s in pending
                 if s.get("op") == "purge_definition"}
    hero_inst = hero_instances(instances)

    lb.delete(0, tk.END)
    app._disease_lb_map: list = []   # index → disease dict

    counts: dict = {}
    for inst in hero_inst:
        did = inst.get("disease_id", "")
        counts[did] = counts.get(did, 0) + 1

    for d in diseases:
        did   = str(d.get("id", ""))
        name  = d.get("name", did)
        count = counts.get(did, 0)
        label = f"{name}  ★{count}" if count else name
        if did in purge_ids:
            label = "🗑 " + label   # staged for deletion (see 💾 儲存 / ↩ 取消)
        lb.insert(tk.END, label)
        app._disease_lb_map.append(d)

    # If the previously-selected disease no longer exists, forget it.
    sel_id = getattr(app, "_disease_selected_id", None) or ""
    still_exists = any(str(d.get("id")) == sel_id for d in diseases) if sel_id else False
    if not still_exists:
        app._disease_selected_id = None
    else:
        for i in prev_sel:
            try:
                lb.selection_set(i)
            except tk.TclError:
                pass
    lb.yview_moveto(prev_top)


def _refresh_disease_filter_options(app) -> None:
    """Refill the disease-name filter dropdown from current catalog."""
    if not hasattr(app, "_disease_filter_disease_cb"):
        return
    diseases = getattr(app, "diseases", [])
    options = [getattr(app, "_DISEASE_KIND_ALL", tr("全部"))]
    seen_ids: set = set()
    for d in diseases:
        did = d.get("id", "")
        if did in seen_ids:
            continue
        seen_ids.add(did)
        options.append(d.get("name", did))
    app._disease_filter_disease_cb.configure(values=options)
    cur = app._disease_filter_disease.get()
    if cur not in options:
        app._disease_filter_disease.set(options[0])


def _reset_filters(app) -> None:
    app._disease_filter_kw.set("")
    app._disease_filter_kind.set(app._DISEASE_KIND_ALL)
    app._disease_filter_disease.set(app._DISEASE_KIND_ALL)
    app._disease_filter_treat.set(app._DISEASE_TREAT_ALL)


def _on_disease_select(app) -> None:
    sel = app._disease_lb.curselection()
    if not sel:
        return
    idx = sel[0]
    if not hasattr(app, "_disease_lb_map") or idx >= len(app._disease_lb_map):
        return
    d = app._disease_lb_map[idx]
    app._disease_selected_id = str(d.get("id", "") or "")
    _disease_apply_edit_ui(app)   # catalog-edit buttons need edit mode + selection
    _render_disease_detail(app, d)


def _config_disease_detail_tags(t: tk.Text) -> None:
    t.tag_configure("key",    foreground=tcol("#6B5B3E"),
                    font=("Microsoft JhengHei", 10, "bold"))
    t.tag_configure("val",    foreground=tcol("#333333"))
    t.tag_configure("head",   foreground=tcol("#2471A3"),
                    font=("Microsoft JhengHei", 11, "bold"))
    t.tag_configure("effect", foreground=tcol("#27AE60"))
    t.tag_configure("empty",  foreground=tcol("#999999"),
                    font=("Microsoft JhengHei", 10, "italic"))


def _disease_type_label(v: Any) -> str:
    """Localize the AI Influence disease ``type`` value (e.g. seasonal /
    disease_outbreak). Unknown values fall through to the raw string."""
    return {
        "seasonal":         tr("季節性"),
        "disease_outbreak": tr("疾病爆發"),
    }.get(str(v or "").strip().lower(), str(v or "?"))


def _render_disease_detail(app, d: dict) -> None:
    """Render the selected disease across three side-by-side columns:
    屬性 ｜ 效果 ｜ 描述."""
    cols = getattr(app, "_disease_detail_cols", None)
    if not cols:
        return
    # Column order: 屬性（摘要）｜ 描述 ｜ 效果.
    c_props, c_desc, c_eff = cols
    for t in cols:
        t.configure(state="normal")
        t.delete("1.0", "end")

    def kv(t, key, val):
        t.insert("end", f"{key}：", "key")
        t.insert("end", str(val) + "\n", "val")

    # ── Column 1: 屬性 ──
    c_props.insert("end", str(d.get("name", "")) + "\n", "head")
    c_props.insert("end", "─" * 16 + "\n")
    kv(c_props, tr("嚴重度"),   d.get("severity", "?"))
    kv(c_props, tr("類型"),     _disease_type_label(d.get("type", "?")))
    kv(c_props, tr("傳染率"),   d.get("spread_rate", "?"))
    kv(c_props, tr("持續天數"), d.get("duration_days", "?"))
    kv(c_props, tr("已隔離"),   "✓" if d.get("is_quarantined") else "✗")

    # ── Column 2: 效果 ──
    c_eff.insert("end", tr("效果") + "\n", "head")
    c_eff.insert("end", "─" * 16 + "\n")
    effects = d.get("effects", {})
    combat  = effects.get("combat_modifiers", {})
    mapmod  = effects.get("map_modifiers", {})
    any_eff = False
    for label, val, delta in (
        (tr("戰鬥傷害"), combat.get("damage_multiplier"),   False),
        (tr("防禦"),     combat.get("defense_multiplier"),  False),
        (tr("速度"),     combat.get("speed_multiplier"),    False),
        (tr("命中率"),   combat.get("accuracy_multiplier"), False),
        (tr("移動速度"), mapmod.get("movement_speed_multiplier"), False),
        (tr("士氣"),     mapmod.get("morale_modifier"),     True),
        (tr("死亡率"),   effects.get("death_chance"),       True),
    ):
        if _effect_line(c_eff, label, val, is_delta=delta):
            any_eff = True
    if not any_eff:
        c_eff.insert("end", tr("（無顯著效果）") + "\n", "empty")

    # ── Column 3: 描述 ──
    c_desc.insert("end", tr("描述") + "\n", "head")
    c_desc.insert("end", "─" * 16 + "\n")
    desc = str(d.get("description", "")).strip()
    c_desc.insert("end", (desc if desc else tr("（無描述）")) + "\n",
                  "val" if desc else "empty")

    for t in cols:
        t.configure(state="disabled")
        t.see("1.0")


def _effect_line(t: tk.Text, label: str, value, is_delta: bool = False) -> bool:
    """Insert one effect line; return True if a line was written."""
    if value is None:
        return False
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return False
    if is_delta:
        disp = f"{fv:+.1f}"
    else:
        pct  = (fv - 1.0) * 100
        disp = f"{pct:+.0f}%" if abs(pct) > 0.01 else tr("（無影響）")
    t.insert("end", f"  {label}: {disp}\n", "effect")
    return True


# ── Filter logic ───────────────────────────────────────────────────────

def _is_target_in_player_party(app, inst: dict) -> bool:
    """True if *inst* targets something travelling with the player.

    * Hero infection — hero's IsInPlayerParty is True.
    * Party named ``player_party`` — always True.
    * Hero-led party (``<sid>_party_<n>``) — owner hero has IsInPlayerParty.
    """
    if _is_hero(inst):
        return _is_hero_in_player_party(app, str(inst.get("target_id", "")))
    if _is_party(inst):
        target_id = str(inst.get("target_id", ""))
        if target_id == PLAYER_PARTY_ID:
            return True
        owner_sid = _party_owner_sid(target_id)
        if owner_sid and _is_hero_in_player_party(app, owner_sid):
            return True
    return False


def _filter_instance(app, inst: dict, defn_lookup) -> bool:
    """Return True if *inst* should be shown given current filter state."""
    # Kind (3-way: heroes / troops / prisoners / player-party)
    kind_sel = app._disease_filter_kind.get()
    if kind_sel == app._DISEASE_KIND_HERO and not _is_hero(inst):
        return False
    if kind_sel == app._DISEASE_KIND_TROOPS and not _is_troops(inst):
        return False
    if kind_sel == app._DISEASE_KIND_PRISONERS and not _is_prisoners(inst):
        return False
    if kind_sel == app._DISEASE_KIND_PLAYER_PARTY and not _is_target_in_player_party(app, inst):
        return False

    # Disease name
    dis_sel = app._disease_filter_disease.get()
    if dis_sel and dis_sel != app._DISEASE_KIND_ALL:
        defn = defn_lookup(inst.get("disease_id", ""))
        cur_name = (defn.get("name") if defn else inst.get("disease_name", "")) or ""
        if cur_name != dis_sel:
            return False

    # Treatment status
    treat_sel = app._disease_filter_treat.get()
    if treat_sel == app._DISEASE_TREAT_TREATED and not inst.get("is_treated"):
        return False
    if treat_sel == app._DISEASE_TREAT_UNTREAT and inst.get("is_treated"):
        return False

    # Keyword (name / id / disease name / target id)
    kw = (app._disease_filter_kw.get() or "").strip().lower()
    if kw:
        target_id = str(inst.get("target_id", "")).lower()
        defn = defn_lookup(inst.get("disease_id", ""))
        dname = (defn.get("name") if defn else inst.get("disease_name", "")) or ""
        # Best-effort hero display name lookup for hero infections + party owners
        hero_disp = ""
        if _is_hero(inst):
            resolver = getattr(app, "resolve_display_name", None)
            if callable(resolver):
                try:
                    disp, _src = resolver(inst.get("target_id", ""), exclude_library=True)
                    hero_disp = (disp or "").lower()
                except Exception:
                    pass
        elif _is_party(inst):
            owner_sid = _party_owner_sid(str(inst.get("target_id", "")))
            if owner_sid:
                resolver = getattr(app, "resolve_display_name", None)
                if callable(resolver):
                    try:
                        disp, _src = resolver(owner_sid, exclude_library=True)
                        hero_disp = (disp or "").lower()
                    except Exception:
                        pass
        haystack = " ".join([target_id, str(dname).lower(), hero_disp])
        if kw not in haystack:
            return False

    return True


# ── Pin priority (favorited heroes / player_party / favorited-hero parties) ──

def _pin_priority(app, inst: dict) -> int:
    """Return a sort priority — lower number = higher in the list.

    0 — favorited hero infection
    1 — ``player_party`` infection
    2 — party owned by a favorited hero (id pattern ``<sid>_party_<n>``)
    9 — everything else (no pin)
    """
    if _is_hero(inst):
        if _is_hero_favorited(app, str(inst.get("target_id", ""))):
            return 0
        return 9
    if _is_party(inst):
        target_id = str(inst.get("target_id", ""))
        if target_id == PLAYER_PARTY_ID:
            return 1
        owner_sid = _party_owner_sid(target_id)
        if owner_sid and _is_hero_favorited(app, owner_sid):
            return 2
    return 9


# ── Infection list rendering (Treeview) ────────────────────────────────

def _populate_infection_list(app) -> None:
    tv = getattr(app, "_disease_tree", None)
    if tv is None:
        return

    # Preserve scroll + selection across the rebuild.  iids are deterministic
    # (target_id::disease_id) so rows that still exist stay selected after an
    # edit — same approach as the 資料庫 character tree.
    prev_sel = list(tv.selection())
    prev_top = tv.yview()[0]

    instances = getattr(app, "disease_instances", [])
    definitions = getattr(app, "diseases", [])
    pending: list = list(getattr(app, "disease_pending", []) or [])

    # Build lookup for fast disease_id → defn
    defn_by_id = {d.get("id", ""): d for d in (definitions or [])}
    def defn_lookup(did):
        return defn_by_id.get(did)

    # Clear table
    for iid in tv.get_children():
        tv.delete(iid)
    app._disease_inst_map = {}  # tree iid → instance OR pending sentinel

    def _put(key: str, payload: dict, obj) -> None:
        """Insert a row under a stable, collision-free iid."""
        iid = key
        n = 1
        while iid in app._disease_inst_map:
            iid = f"{key}#{n}"
            n += 1
        tv.insert("", "end", iid=iid, **payload)
        app._disease_inst_map[iid] = obj

    # Per-instance pending REMOVE keys
    pending_remove_keys = {
        (str(s.get("hero_sid", "")), str(s.get("disease_id", "")))
        for s in pending if s.get("op") == "remove"
    }
    # Catalog-scoped staged ops wipe ALL infections of a disease → show those
    # rows as pending-remove too, so the staged effect is visible pre-commit.
    cleared_disease_ids = {
        str(s.get("disease_id", "")) for s in pending
        if s.get("op") in ("clear_infections", "purge_definition")
    }
    pending_assigns = [s for s in pending if s.get("op") == "assign"]

    resolver = getattr(app, "resolve_display_name", None)

    visible_target_count = {"hero": 0, "party": 0}

    # First pass — (pin_priority, original_idx, payload, inst) for everything
    # passing the filter; then stable-sort by pin priority.
    candidate_rows = []

    for orig_idx, inst in enumerate(_all_target_instances(instances)):
        if not _filter_instance(app, inst, defn_lookup):
            continue
        target_id = str(inst.get("target_id", "?"))
        did       = str(inst.get("disease_id", ""))
        is_pend_remove = ((target_id, did) in pending_remove_keys
                          or did in cleared_disease_ids)

        defn       = defn_lookup(did)
        name       = defn.get("name") if defn else inst.get("disease_name", did)
        progress   = inst.get("disease_progress", 0.0)
        treated    = "✓" if inst.get("is_treated") else "✗"
        try:
            inf_str = format_game_time(float(inst.get("infected_at", 0.0)))
        except (TypeError, ValueError):
            inf_str = str(inst.get("infected_at", 0.0))

        if _is_hero(inst):
            kind_text = "🧑"
            visible_target_count["hero"] += 1
            if resolver is not None:
                try:
                    disp, _src = resolver(target_id, exclude_library=True)
                    target_disp = f"{disp} ({target_id})" if disp and disp != target_id else target_id
                except Exception:
                    target_disp = target_id
            else:
                target_disp = target_id

            if inst.get("has_prevention_effect"):
                try:
                    strength = int(inst.get("prevention_strength", 0) or 0)
                except (TypeError, ValueError):
                    strength = 0
                immune_cell = tr("✓ 已康復(強度{strength})").format(strength=strength)
            else:
                immune_cell = "—"
            kind_tag = "hero_immune" if inst.get("has_prevention_effect") else ""
        else:
            # Party: distinguish troops (🛡) vs prisoners (⛓).
            kind_text = "⛓" if _is_prisoners(inst) else "🛡"
            visible_target_count["party"] += 1
            target_disp = target_id
            owner_sid = _party_owner_sid(target_id)
            if owner_sid and resolver is not None:
                try:
                    disp, _src = resolver(owner_sid, exclude_library=True)
                    if disp and disp != owner_sid:
                        m = _PARTY_OWNER_RE.match(target_id)
                        if m:
                            party_n = target_id[len(owner_sid) + len("_party_"):]
                            party_n = party_n if party_n else "?"
                            target_disp = tr("{owner}的部隊{n} ({tid})").format(owner=disp, n=party_n, tid=target_id)
                        else:
                            target_disp = f"{disp} ({target_id})"
                except Exception:
                    pass
            elif target_id == PLAYER_PARTY_ID:
                target_disp = f"{tr('玩家部隊')} ({target_id})"
            immune_cell = "—"
            kind_tag = "party"

        tags = []
        if is_pend_remove:
            tags.append("pending_remove")
        elif kind_tag:
            tags.append(kind_tag)

        progress_str = f"{progress:.1f}%" if isinstance(progress, (int, float)) else str(progress)
        if is_pend_remove:
            target_disp = f"{target_disp}  · {tr('暫存移除')}"

        pin = _pin_priority(app, inst)
        if pin < 9:
            tags.append("pinned")

        row_payload = dict(
            values=(kind_text, target_disp, name, progress_str,
                    treated, inf_str, immune_cell),
            tags=tuple(tags),
        )
        candidate_rows.append((pin, orig_idx, target_id, did, row_payload, inst))

    # Stable sort by pin first, then by original order within each bucket.
    candidate_rows.sort(key=lambda t: (t[0], t[1]))

    for _pin, _idx, target_id, did, payload, inst in candidate_rows:
        _put(f"{target_id}::{did}", payload, inst)

    # Pending assigns (rendered after existing rows)
    for stage in pending_assigns:
        # Assigns are always heroes → hide when filtering to troops/prisoners.
        if app._disease_filter_kind.get() in (
                app._DISEASE_KIND_TROOPS, app._DISEASE_KIND_PRISONERS):
            continue
        # Disease-name filter
        dis_sel = app._disease_filter_disease.get()
        if dis_sel and dis_sel != app._DISEASE_KIND_ALL:
            if stage.get("disease_name", "") != dis_sel:
                continue
        # Treatment filter — assigns are always untreated initially
        if app._disease_filter_treat.get() == app._DISEASE_TREAT_TREATED:
            continue
        # Keyword filter
        kw = (app._disease_filter_kw.get() or "").strip().lower()
        if kw:
            haystack = " ".join([
                str(stage.get("hero_sid", "")).lower(),
                str(stage.get("hero_display", "")).lower(),
                str(stage.get("disease_name", "")).lower(),
            ])
            if kw not in haystack:
                continue

        hero_sid    = str(stage.get("hero_sid", "?"))
        hero_disp   = stage.get("hero_display") or hero_sid
        dis_name    = stage.get("disease_name", stage.get("disease_id", ""))
        if hero_disp and hero_disp != hero_sid:
            target_disp = f"{hero_disp} ({hero_sid})"
        else:
            target_disp = hero_sid
        target_disp = f"+ {target_disp}  · {tr('暫存新增')}"

        _put(
            f"assign::{hero_sid}::{stage.get('disease_id', '')}",
            dict(values=("🧑", target_disp, dis_name, "—", "—", "—", "—"),
                 tags=("pending_assign",)),
            stage,
        )

    # Restore prior selection (iids that still exist) + scroll position.
    keep = [i for i in prev_sel if i in app._disease_inst_map]
    if keep:
        tv.selection_set(keep)
    tv.yview_moveto(prev_top)

    # Status line
    total_hero  = sum(1 for x in (instances or []) if _is_hero(x))
    total_party = sum(1 for x in (instances or []) if _is_party(x))
    parts = []
    parts.append(tr("英雄 {n}/{total}").format(n=visible_target_count['hero'], total=total_hero))
    parts.append(tr("隊伍 {n}/{total}").format(n=visible_target_count['party'], total=total_party))
    if pending:
        parts.append(tr("暫存 {n} 筆").format(n=len(pending)))
    app._disease_count_var.set(" · ".join(parts))

    # Selection may have changed → re-sync bottom-bar button states.
    _disease_apply_edit_ui(app)
