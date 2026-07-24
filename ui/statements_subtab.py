"""Ruler statements + diplomacy status sub-tabs (Phase 6 Stage B, read-only).

Lives inside the 🎭 動態事件 tab's inner notebook (built by
``ui.dynamic_events_tab``).  Stage B scope is browse-only: list / filter /
detail / cross-jump.  Editing arrives in Stage C.

Data expected on *app*:
    app.diplomacy_bundle        dict | None    (full bundle, loaded on reload)
    app.resolve_kingdom_name    (kid) -> display name
    app._dyn_inner_nb           inner ttk.Notebook (for tab switching)

Registers on *app*:
    app._stmt_refresh()         repopulate list from app.diplomacy_bundle
    app._stmt_show_event(eid)   filter list to one event and switch sub-tab
    app._diplo_status_refresh() refresh the diplomacy-status sub-tab
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

from i18n import tr
from services.time_format import format_game_time
from services.diplomacy_service import (
    DIPLOMATIC_ACTIONS,
    action_name,
    bundle_statements,
    bundle_pressure,
    parse_statement,
    statement_key,
    statement_keys,
)
from ui import preview_font
from ui.theme import tcol


def _effective_model(s: dict) -> dict:
    """Return the unified model for either a raw statement or a staged model."""
    if "action_names" in s:        # already a unified model (staged edit / new)
        return s
    return parse_statement(s, embedded=False)

def _all_label() -> str:
    """全部/All filter sentinel, resolved at call time (a module-level literal
    would stay Chinese in English mode).  Maps to the empty-string key via the
    ``*_display_to_key`` maps."""
    return tr("全部")


# ── Action display labels (28 values) ─────────────────────────────────────────

def _action_labels() -> Dict[str, str]:
    return {
        "None":                  tr("純聲明"),
        "DeclareWar":            tr("宣戰"),
        "ProposePeace":          tr("提議和平"),
        "ProposeAlliance":       tr("提議聯盟"),
        "RejectPeace":           tr("拒絕和平"),
        "RejectAlliance":        tr("拒絕聯盟"),
        "AcceptPeace":           tr("接受和平"),
        "AcceptAlliance":        tr("接受聯盟"),
        "BreakAlliance":         tr("撕毀聯盟"),
        "ProposeTradeAgreement": tr("提議貿易協定"),
        "AcceptTradeAgreement":  tr("接受貿易協定"),
        "RejectTradeAgreement":  tr("拒絕貿易協定"),
        "EndTradeAgreement":     tr("終止貿易協定"),
        "TransferTerritory":     tr("轉讓領土"),
        "DemandTerritory":       tr("索要領土"),
        "RejectTerritory":       tr("拒絕領土要求"),
        "DemandTribute":         tr("索要貢金"),
        "AcceptTribute":         tr("接受貢金"),
        "RejectTribute":         tr("拒絕貢金"),
        "EndTribute":            tr("終止貢金"),
        "DemandReparations":     tr("索要賠款"),
        "AcceptReparations":     tr("接受賠款"),
        "RejectReparations":     tr("拒絕賠款"),
        "ExpelClan":             tr("驅逐氏族"),
        "GrantFief":             tr("授予封地"),
        "ReceiveFief":           tr("接受封地"),
        "QuarantineSettlement":  tr("隔離定居點"),
        "SetKingdomTaxPolicy":   tr("稅收政策"),
    }


_ACTION_CATEGORIES: Dict[str, tuple] = {
    # category label key → action names
    "純聲明":     ("None",),  # noqa: cjk (label tr()-translated at use)
    "戰爭與和平": ("DeclareWar", "ProposePeace", "RejectPeace", "AcceptPeace"),  # noqa: cjk (label tr()-translated at use)
    "聯盟":       ("ProposeAlliance", "RejectAlliance", "AcceptAlliance", "BreakAlliance"),  # noqa: cjk (label tr()-translated at use)
    "領土與封地": ("TransferTerritory", "DemandTerritory", "RejectTerritory",  # noqa: cjk (label tr()-translated at use)
                   "GrantFief", "ReceiveFief"),
    "貢金與賠款": ("DemandTribute", "AcceptTribute", "RejectTribute", "EndTribute",  # noqa: cjk (label tr()-translated at use)
                   "DemandReparations", "AcceptReparations", "RejectReparations"),
    "貿易":       ("ProposeTradeAgreement", "AcceptTradeAgreement",  # noqa: cjk (label tr()-translated at use)
                   "RejectTradeAgreement", "EndTradeAgreement"),
    "隔離與稅收": ("QuarantineSettlement", "SetKingdomTaxPolicy"),  # noqa: cjk (label tr()-translated at use)
    "其他":       ("ExpelClan",),  # noqa: cjk (label tr()-translated at use)
}


def _resolve_kingdom(app, kid: str) -> str:
    if not kid:
        return ""
    fn = getattr(app, "resolve_kingdom_name", None)
    if fn is not None:
        try:
            return fn(kid) or kid
        except Exception:
            return kid
    return kid


def _resolve_settlement(app, sid: str) -> str:
    """Settlement id → display name (companion-mod terminology); raw id when
    no terminology is loaded for that settlement."""
    if not sid:
        return ""
    fn = getattr(app, "resolve_settlement_name", None)
    if fn is not None:
        try:
            return fn(sid) or sid
        except Exception:
            return sid
    return sid


def _resolve_clan(app, cid: str) -> str:
    if not cid:
        return ""
    fn = getattr(app, "resolve_clan_name", None)
    if fn is not None:
        try:
            return fn(cid) or cid
        except Exception:
            return cid
    return cid


def _event_by_id(app, eid: str) -> Optional[dict]:
    bundle = getattr(app, "diplomacy_bundle", None) or {}
    for e in bundle.get("dynamic_events", []) or []:
        if isinstance(e, dict) and str(e.get("id", "")) == str(eid):
            return e
    return None


def _embedded_twin(app, stmt: dict) -> Optional[dict]:
    """Find the event-embedded copy of a top-level statement (same kingdom +
    campaign_days) — the embedded copy carries relation_changes."""
    eid = str(stmt.get("event_id") or "")
    ev = _event_by_id(app, eid) if eid else None
    if not ev:
        return None
    try:
        days = float(stmt.get("campaign_days") or 0.0)
    except (TypeError, ValueError):
        return None
    for s in ev.get("kingdom_statements", []) or []:
        try:
            if (str(s.get("kingdom_id") or "") == str(stmt.get("kingdom_id") or "")
                    and abs(float(s.get("campaign_days") or 0.0) - days) < 0.01):
                return s
        except (TypeError, ValueError):
            continue
    return None


# ── Statements sub-tab ────────────────────────────────────────────────────────

def build_statements_subtab(app, parent: ttk.Frame) -> None:
    app._stmt_frame = parent

    # ── Filter bar ────────────────────────────────────────────────────
    fbar = ttk.LabelFrame(parent, text=tr("篩選"), padding=(6, 4))
    fbar.pack(fill=tk.X, padx=4, pady=(4, 4))

    ttk.Label(fbar, text=tr("發言王國:")).grid(row=0, column=0, padx=(0, 2), sticky="w")
    app._stmt_filter_kingdom = tk.StringVar(value=_all_label())
    app._stmt_kingdom_cb = ttk.Combobox(fbar, textvariable=app._stmt_filter_kingdom,
                                        values=[_all_label()], state="readonly", width=14)
    app._stmt_kingdom_cb.grid(row=0, column=1, padx=(0, 10), sticky="w")
    app._stmt_kingdom_display_to_key: Dict[str, str] = {_all_label(): ""}

    ttk.Label(fbar, text=tr("動作類別:")).grid(row=0, column=2, padx=(0, 2), sticky="w")
    app._stmt_filter_cat = tk.StringVar(value=_all_label())
    cat_opts = [_all_label()] + [tr(c) for c in _ACTION_CATEGORIES]
    app._stmt_cat_display_to_key = {_all_label(): ""}
    for c in _ACTION_CATEGORIES:
        app._stmt_cat_display_to_key[tr(c)] = c
    ttk.Combobox(fbar, textvariable=app._stmt_filter_cat, values=cat_opts,
                 state="readonly", width=12).grid(row=0, column=3, padx=(0, 10), sticky="w")

    ttk.Label(fbar, text=tr("關鍵字:")).grid(row=0, column=4, padx=(0, 2), sticky="w")
    app._stmt_filter_kw = tk.StringVar()
    ttk.Entry(fbar, textvariable=app._stmt_filter_kw, width=16).grid(
        row=0, column=5, padx=(0, 10), sticky="w")

    ttk.Button(fbar, text=tr("清除"), command=lambda: _clear_stmt_filters(app),
               style="secondary.TButton").grid(row=0, column=6, padx=(0, 0))

    # Event-filter chip (set via the events sub-tab jump; hidden by default)
    app._stmt_event_filter: Optional[str] = None
    app._stmt_event_chip_var = tk.StringVar(value="")
    chip = ttk.Frame(fbar)
    app._stmt_event_chip = chip
    ttk.Label(chip, textvariable=app._stmt_event_chip_var,
              foreground=tcol("#B5852E"), font=("", 9, "bold")).pack(side=tk.LEFT)
    ttk.Button(chip, text="✕", width=2, style="secondary.TButton",
               command=lambda: _clear_event_filter(app)).pack(side=tk.LEFT, padx=(4, 0))
    app._stmt_event_chip_grid = dict(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))

    for var in (app._stmt_filter_kingdom, app._stmt_filter_cat, app._stmt_filter_kw):
        var.trace_add("write", lambda *_: _refresh_stmt_list(app))

    # ── Action bar — always visible; buttons grey out when not usable.
    # Layout (aligned with 疾病/事件): ➕ 新增聲明 ｜ 選取聲明：✏ 編輯 🗑 刪除
    ebar = ttk.Frame(parent)
    app._stmt_edit_bar = ebar
    ebar.pack(fill=tk.X, padx=4, pady=(4, 0), before=fbar)
    app._stmt_new_btn = ttk.Button(
        ebar, text=tr("➕ 新增聲明"), style="info.TButton",
        command=lambda: _open_stmt_editor_new(app))
    app._stmt_new_btn.pack(side=tk.LEFT, padx=(0, 8), pady=2)
    ttk.Label(ebar, text=tr("選取聲明："),
              foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)
    app._stmt_edit_btn = ttk.Button(
        ebar, text=tr("✏ 編輯…"), style="warning.TButton", state="disabled",
        command=lambda: _open_stmt_editor_selected(app))
    app._stmt_edit_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
    app._stmt_del_btn = ttk.Button(
        ebar, text=tr("🗑 刪除"), style="danger.TButton", state="disabled",
        command=lambda: _delete_selected_stmt(app))
    app._stmt_del_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
    app._stmt_undel_btn = ttk.Button(
        ebar, text=tr("↩ 復原刪除"), style="secondary.TButton",
        command=lambda: _undelete_selected_stmt(app))
    # undel swaps in for 刪除 only when a deleted row is selected.
    edit_var = getattr(app, "edit_mode_var", None) or getattr(app, "_dyn_edit_var", None)
    if edit_var is not None:
        edit_var.trace_add("write", lambda *_: _sync_stmt_edit_bar(app))

    # ── Main area: list (top) + detail (bottom) ───────────────────────
    panes = ttk.PanedWindow(parent, orient=tk.VERTICAL)
    panes.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

    list_outer = ttk.Frame(panes)
    panes.add(list_outer, weight=11)
    cols = ("day", "kingdom", "actions", "targets", "settlement", "event")
    tree = ttk.Treeview(list_outer, columns=cols, show="headings", selectmode="browse")
    app._stmt_tree = tree
    heads = {
        "day":        (tr("日期"), 148, "w"),
        "kingdom":    (tr("發言王國"), 168, "w"),
        "actions":    (tr("動作"), 168, "w"),
        "targets":    (tr("對象"), 196, "w"),
        "settlement": (tr("定居點"), 168, "w"),
        "event":      (tr("關聯事件"), 250, "w"),
    }
    # 動作 is now the stretch column, so the window's spare width widens *it*
    # (its cells hold the longest text, and English runs longer still); 關聯事件
    # is a fixed, much narrower column instead of absorbing everything.
    for c in cols:
        text, width, anchor = heads[c]
        tree.heading(c, text=text)
        tree.column(c, width=width, anchor=anchor, stretch=(c == "actions"))
    vsb = ttk.Scrollbar(list_outer, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    app._stmt_count_var = tk.StringVar(value="")
    ttk.Label(parent, textvariable=app._stmt_count_var,
              foreground=tcol("#6B5B3E")).pack(side=tk.BOTTOM, anchor="w", padx=8, pady=(0, 2))

    det_outer = ttk.Frame(panes)
    panes.add(det_outer, weight=9)
    det = tk.Text(det_outer, wrap="word", state="disabled",
                  font=("Microsoft JhengHei", 10), relief="flat",
                  spacing1=2, spacing3=2, height=9)
    det_vsb = ttk.Scrollbar(det_outer, orient="vertical", command=det.yview)
    det.configure(yscrollcommand=det_vsb.set)
    det.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    det_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    app._stmt_detail_text = det
    det.tag_configure("title",   font=("Microsoft JhengHei", 11, "bold"), foreground=tcol("#1A3A5C"))
    det.tag_configure("section", font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#2471A3"))
    det.tag_configure("key",     font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#6B5B3E"))
    det.tag_configure("val",     font=("Microsoft JhengHei", 10),         foreground=tcol("#333333"))
    det.tag_configure("body",    font=("Microsoft JhengHei", 10),         foreground=tcol("#222222"))
    det.tag_configure("neg",     font=("Microsoft JhengHei", 10),         foreground=tcol("#C0392B"))
    det.tag_configure("pos",     font=("Microsoft JhengHei", 10),         foreground=tcol("#1A7A3F"))
    preview_font.register(det)   # after the tags — see dynamic_events_tab

    # Pending-state visuals
    tree.tag_configure("edited",  foreground=tcol("#E67E22"))
    tree.tag_configure("deleted", foreground=tcol("#C0392B"))
    tree.tag_configure("new",     foreground=tcol("#1A7A3F"))

    app._stmt_rows: List[dict] = []   # row index → row-info dict (見 _refresh_stmt_list)
    tree.bind("<<TreeviewSelect>>", lambda e: _on_stmt_select(app))
    tree.bind("<Double-1>", lambda e: _jump_to_event(app))

    # Hint bar
    ttk.Label(parent, text=tr("雙擊聲明列可跳轉到關聯事件；開啟編輯模式以新增／編輯／刪除聲明"),
              foreground=tcol("#999999"), font=("", 9)).pack(side=tk.BOTTOM, anchor="w",
                                                       padx=8, pady=(0, 2))

    # Public API
    app._stmt_refresh = lambda: _refresh_stmt_subtab(app)
    app._stmt_show_event = lambda eid: _show_event_filter(app, eid)

    _refresh_stmt_subtab(app)


def _clear_stmt_filters(app) -> None:
    app._stmt_filter_kingdom.set(_all_label())
    app._stmt_filter_cat.set(_all_label())
    app._stmt_filter_kw.set("")
    _clear_event_filter(app)


def _clear_event_filter(app) -> None:
    app._stmt_event_filter = None
    try:
        app._stmt_event_chip.grid_forget()
    except Exception:
        pass
    _refresh_stmt_list(app)


def _show_event_filter(app, event_id: str) -> None:
    """Entry point for the events-side jump button."""
    app._stmt_event_filter = str(event_id or "") or None
    if app._stmt_event_filter:
        ev = _event_by_id(app, app._stmt_event_filter)
        title = (ev or {}).get("title") or app._stmt_event_filter[:8]
        app._stmt_event_chip_var.set(tr("僅顯示事件：{title}").format(title=title))
        try:
            app._stmt_event_chip.grid(**app._stmt_event_chip_grid)
        except Exception:
            pass
    _refresh_stmt_list(app)
    nb = getattr(app, "_dyn_inner_nb", None)
    if nb is not None:
        try:
            nb.select(app._stmt_frame)
        except Exception:
            pass


def _refresh_stmt_subtab(app) -> None:
    """Full refresh: rebuild kingdom filter options + list."""
    stmts = bundle_statements(getattr(app, "diplomacy_bundle", None) or {})
    kingdoms: Dict[str, str] = {}
    for s in stmts:
        kid = str(s.get("kingdom_id") or "")
        if kid and kid not in kingdoms:
            kingdoms[kid] = _resolve_kingdom(app, kid)
    disp_map = {_all_label(): ""}
    for kid, disp in sorted(kingdoms.items(), key=lambda kv: kv[1]):
        disp_map[disp] = kid
    app._stmt_kingdom_display_to_key = disp_map
    cur = app._stmt_filter_kingdom.get()
    app._stmt_kingdom_cb.configure(values=list(disp_map.keys()))
    if cur not in disp_map:
        app._stmt_filter_kingdom.set(_all_label())
    _refresh_stmt_list(app)


def _refresh_stmt_list(app) -> None:
    """Rebuild the list, overlaying the staging buffer.

    Row-info dict: ``{"kind": "existing"|"new", "key": str|None,
    "new_index": int|None, "status": ""|"edited"|"deleted"|"new",
    "model": unified model, "raw": original raw dict|None}``
    """
    tree = getattr(app, "_stmt_tree", None)
    if tree is None:
        return
    # Capture the selected row's identity so an edit/delete keeps it selected.
    _prev = _selected_row(app)
    prev_kind = _prev.get("kind") if _prev else None
    prev_key = _prev.get("key") if _prev else None
    prev_new = _prev.get("new_index") if _prev else None
    labels = _action_labels()
    stmts = bundle_statements(getattr(app, "diplomacy_bundle", None) or {})
    keys = statement_keys(stmts)
    pend = getattr(app, "dyn_events_pending", None) or {}
    s_edits = pend.get("stmt_edits", {}) or {}
    s_dels = pend.get("stmt_deletes", set()) or set()
    s_new = pend.get("stmt_new", []) or []

    kid_filter = app._stmt_kingdom_display_to_key.get(app._stmt_filter_kingdom.get(), "")
    cat_key = app._stmt_cat_display_to_key.get(app._stmt_filter_cat.get(), "")
    cat_actions = set(_ACTION_CATEGORIES.get(cat_key, ())) if cat_key else None
    kw = app._stmt_filter_kw.get().strip().lower()
    evt_filter = getattr(app, "_stmt_event_filter", None)

    def _passes(m: dict) -> bool:
        if kid_filter and m["kingdom_id"] != kid_filter:
            return False
        if cat_actions is not None:
            names = m["action_names"] or ["None"]
            if not any(n in cat_actions for n in names):
                return False
        if evt_filter and str(m.get("event_id") or "") != evt_filter:
            return False
        if kw:
            hay = (m["statement_text"] + " " + m["reason"]).lower()
            if kw not in hay:
                return False
        return True

    rows: List[dict] = []
    for key, s in zip(keys, stmts):
        status = "deleted" if key in s_dels else ("edited" if key in s_edits else "")
        m = _effective_model(s_edits.get(key, s))
        if not _passes(m):
            continue
        rows.append({"kind": "existing", "key": key, "new_index": None,
                     "status": status, "model": m, "raw": s})
    for i, nm in enumerate(s_new):
        m = _effective_model(nm)
        if not _passes(m):
            continue
        rows.append({"kind": "new", "key": None, "new_index": i,
                     "status": "new", "model": m, "raw": None})

    rows.sort(key=lambda r: float(r["model"].get("campaign_days") or 0.0), reverse=True)
    app._stmt_rows = rows

    _STATUS_MARK = {"edited": "✏ ", "deleted": "🗑 ", "new": "➕ ", "": ""}
    tree.delete(*tree.get_children())
    for i, row in enumerate(rows):
        m = row["model"]
        try:
            day = format_game_time(float(m["campaign_days"]))
        except (TypeError, ValueError):
            day = str(m["campaign_days"])
        names = m["action_names"] or ["None"]
        act = "＋".join(labels.get(n, n) for n in names)
        targets = "、".join(
            _resolve_kingdom(app, t) for t in m["target_kingdom_ids"]
            if t and t.lower() != "null"
        )
        if m["settlement_ids"] is not None:
            settl = "、".join(_resolve_settlement(app, x) for x in m["settlement_ids"] if x)
        else:
            settl = _resolve_settlement(app, m["settlement_id_raw"] or "")
        eid = str(m.get("event_id") or "")
        ev = _event_by_id(app, eid) if eid else None
        ev_disp = ((ev or {}).get("title") or (eid[:8] if eid else "—"))
        tags = (row["status"],) if row["status"] else ()
        tree.insert("", "end", iid=str(i), tags=tags,
                    values=(_STATUS_MARK[row["status"]] + day,
                            _resolve_kingdom(app, m["kingdom_id"]),
                            act, targets, settl, ev_disp))
    n_pending = sum(1 for r in rows if r["status"])
    suffix = tr("（含 {n_pending} 筆暫存變更）").format(n_pending=n_pending) if n_pending else ""
    app._stmt_count_var.set(tr("共 {v0} 筆聲明").format(v0=len(rows)) + suffix)

    # Restore selection by identity (the tree fully rebuilds on every edit).
    restored = False
    if prev_kind is not None:
        for i, r in enumerate(rows):
            if r["kind"] == prev_kind and (
                    (prev_kind == "existing" and r["key"] == prev_key) or
                    (prev_kind == "new" and r["new_index"] == prev_new)):
                tree.selection_set(str(i))
                tree.see(str(i))
                _render_stmt_detail(app, r)
                restored = True
                break
    if not restored:
        _render_stmt_detail(app, None)
    _sync_stmt_edit_bar(app)


def _selected_row(app) -> Optional[dict]:
    tree = app._stmt_tree
    sel = tree.selection()
    if not sel:
        return None
    try:
        return app._stmt_rows[int(sel[0])]
    except (ValueError, IndexError):
        return None


def _on_stmt_select(app) -> None:
    row = _selected_row(app)
    _render_stmt_detail(app, row)
    _sync_stmt_edit_bar(app)


def _jump_to_event(app) -> None:
    row = _selected_row(app)
    if not row:
        return
    eid = str(row["model"].get("event_id") or "")
    if not eid:
        return
    from ui.dynamic_events_tab import select_event_by_id
    select_event_by_id(app, eid)


# ── Edit-mode bar handlers (Stage C) ─────────────────────────────────────────

def _sync_stmt_edit_bar(app) -> None:
    """Sync always-visible button states (grey out when not usable).

    刪除 and 復原刪除 share one slot — 復原 swaps in only when the selected
    statement is pending-delete.
    """
    edit_var = getattr(app, "edit_mode_var", None) or getattr(app, "_dyn_edit_var", None)
    editing = bool(edit_var.get()) if edit_var is not None else False

    new_btn = getattr(app, "_stmt_new_btn", None)
    if new_btn is not None:
        try:
            new_btn.configure(state="normal" if editing else "disabled")
        except Exception:
            pass

    row = _selected_row(app)
    has_sel = row is not None
    deleted = bool(row and row["status"] == "deleted")
    edit_btn = getattr(app, "_stmt_edit_btn", None)
    del_btn = getattr(app, "_stmt_del_btn", None)
    undel_btn = getattr(app, "_stmt_undel_btn", None)

    if edit_btn is not None:
        try:
            edit_btn.configure(
                state="normal" if (editing and has_sel and not deleted) else "disabled")
        except Exception:
            pass
    if deleted:
        if del_btn is not None:
            try: del_btn.pack_forget()
            except Exception: pass
        if undel_btn is not None:
            try:
                if not undel_btn.winfo_ismapped():
                    undel_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
                undel_btn.configure(state="normal" if (editing and has_sel) else "disabled")
            except Exception: pass
    else:
        if undel_btn is not None:
            try: undel_btn.pack_forget()
            except Exception: pass
        if del_btn is not None:
            try:
                if not del_btn.winfo_ismapped():
                    del_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
                del_btn.configure(state="normal" if (editing and has_sel) else "disabled")
            except Exception: pass


def _open_stmt_editor_new(app) -> None:
    # Same caveat as new events: tool-created statements show in the World Events
    # list but won't trigger AI responses without the in-game pipeline / companion mod.
    from ui.dynamic_events_tab import _companion_mod_warning
    if not _companion_mod_warning(app, kind="statement"):
        return
    from dialogs.statement_editor_dialog import open_statement_editor
    open_statement_editor(app, key=None)


def _open_stmt_editor_selected(app) -> None:
    row = _selected_row(app)
    if not row:
        return
    from dialogs.statement_editor_dialog import open_statement_editor
    if row["kind"] == "new":
        # Edit a staged-new statement in place: replaced on save, kept on cancel.
        idx = row["new_index"]
        model = dict((app.dyn_events_pending.get("stmt_new") or [])[idx])
        open_statement_editor(app, key=None, preload_model=model,
                              replace_new_index=idx)
    else:
        open_statement_editor(app, key=row["key"])


def _delete_selected_stmt(app) -> None:
    row = _selected_row(app)
    if not row:
        return
    if row["kind"] == "new":
        app._stmt_unstage_new(row["new_index"])
    else:
        app._stmt_stage_delete(row["key"])
    if hasattr(app, "_dyn_refresh_pending"):
        app._dyn_refresh_pending()
    _refresh_stmt_list(app)


def _undelete_selected_stmt(app) -> None:
    row = _selected_row(app)
    if not row or row["kind"] != "existing":
        return
    app._stmt_stage_undelete(row["key"])
    if hasattr(app, "_dyn_refresh_pending"):
        app._dyn_refresh_pending()
    _refresh_stmt_list(app)


def _render_stmt_detail(app, row: Optional[dict]) -> None:
    t = app._stmt_detail_text
    labels = _action_labels()
    t.configure(state="normal")
    t.delete("1.0", tk.END)
    if row is None:
        t.insert(tk.END, tr("（選擇一筆聲明以檢視全文）"), "val")
        t.configure(state="disabled")
        return
    m = row["model"]
    stmt = row.get("raw") or {}
    if row["status"]:
        status_label = {"edited": tr("✏ 已暫存編輯"), "deleted": tr("🗑 待刪除"),
                        "new": tr("➕ 新增（未儲存）")}[row["status"]]
        t.insert(tk.END, status_label + "\n", "section")
    speaker = _resolve_kingdom(app, m["kingdom_id"])
    targets = "、".join(_resolve_kingdom(app, x) for x in m["target_kingdom_ids"]
                        if x and x.lower() != "null")
    try:
        day = format_game_time(float(m["campaign_days"]))
    except (TypeError, ValueError):
        day = str(m["campaign_days"])

    t.insert(tk.END, f"{speaker}", "title")
    if targets:
        t.insert(tk.END, f" → {targets}", "title")
    t.insert(tk.END, f"　({day})\n", "val")

    names = m["action_names"] or ["None"]
    t.insert(tk.END, tr("動作："), "key")
    t.insert(tk.END, "＋".join(labels.get(n, n) for n in names) + "\n", "val")

    # Per-action parameters worth surfacing
    params: List[str] = []
    if m["settlement_ids"] is not None:
        settls = [x for x in m["settlement_ids"] if x]
    else:
        settls = [m["settlement_id_raw"]] if m["settlement_id_raw"] else []
    if settls:
        params.append(tr("定居點：") + "、".join(_resolve_settlement(app, x) for x in settls))
    if m["daily_tribute_amount"]:
        params.append(tr("貢金：{v0}/日 × {v1} 日").format(v0=m['daily_tribute_amount'], v1=m['tribute_duration_days']))
    if m["reparations_amount"]:
        params.append(tr("賠款：{v0}").format(v0=m['reparations_amount']))
    if m["tax_rate_percent"]:
        scope = m["tax_scope"] or ""
        params.append(tr("稅率：{v0}%（{scope}）").format(v0=m['tax_rate_percent'], scope=scope))
    if m.get("quarantine_duration_days"):
        params.append(tr("隔離：{v0} 日").format(v0=m['quarantine_duration_days']))
    if m.get("target_clan_id"):
        params.append(tr("目標氏族：") + _resolve_clan(app, str(m["target_clan_id"])))
    for p in params:
        t.insert(tk.END, p + "\n", "val")

    if m["reason"]:
        t.insert(tk.END, "\n" + tr("理由") + "\n", "section")
        t.insert(tk.END, m["reason"] + "\n", "body")

    t.insert(tk.END, "\n" + tr("聲明全文") + "\n", "section")
    t.insert(tk.END, (m["statement_text"] or tr("（空）")) + "\n", "body")

    # relation_changes: staged models may carry them directly (overlay / new);
    # otherwise look up the event-embedded twin.
    if m.get("_embedded_overlay") or row["status"] == "new":
        rels = m.get("relation_changes") or []
    else:
        twin = _embedded_twin(app, stmt) if stmt else None
        rels = (twin or {}).get("relation_changes") or []
    if rels:
        t.insert(tk.END, "\n" + tr("關係變化（事件內嵌副本）") + "\n", "section")
        for r in rels:
            chg = r.get("change", 0)
            tag = "neg" if (isinstance(chg, (int, float)) and chg < 0) else "pos"
            kn = _resolve_kingdom(app, str(r.get("toward_kingdom_id") or ""))
            t.insert(tk.END, f"  {kn}: ", "key")
            t.insert(tk.END, f"{chg:+}　", tag)
            t.insert(tk.END, str(r.get("reason") or "") + "\n", "val")

    t.configure(state="disabled")


# ── Diplomacy status sub-tab (read-only) ──────────────────────────────────────

def build_diplo_status_subtab(app, parent: ttk.Frame) -> None:
    info = ttk.Frame(parent)
    info.pack(fill=tk.X, padx=8, pady=(8, 4))
    app._diplo_info_var = tk.StringVar(value="")
    ttk.Label(info, textvariable=app._diplo_info_var,
              foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)

    # Action bar — always visible; buttons grey out when not usable.
    # Layout (aligned with 疾病/事件/聲明): ➕ 加入王國 ｜ 選取王國：✏ 編輯壓力 🗑 移除
    ebar = ttk.Frame(parent)
    app._diplo_edit_bar = ebar
    ebar.pack(fill=tk.X, padx=8, pady=(0, 2))
    app._diplo_add_btn = ttk.Button(
        ebar, text=tr("➕ 加入王國"), style="success.TButton",
        command=lambda: _diplo_add_kingdom(app), state="disabled")
    app._diplo_add_btn.pack(side=tk.LEFT, padx=(0, 8), pady=2)
    ttk.Label(ebar, text=tr("選取王國："),
              foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)
    app._diplo_edit_btn = ttk.Button(
        ebar, text=tr("✏ 編輯壓力"), style="warning.TButton",
        command=lambda: _diplo_edit_selected(app), state="disabled")
    app._diplo_edit_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
    app._diplo_remove_btn = ttk.Button(
        ebar, text=tr("🗑 移除"), style="danger.TButton",
        command=lambda: _diplo_remove_selected(app), state="disabled")
    app._diplo_remove_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
    # Restore a staged-removed row (parity with 事件 / 統治者聲明 的復原刪除).
    app._diplo_restore_btn = ttk.Button(
        ebar, text=tr("↩ 復原刪除"), style="secondary.TButton",
        command=lambda: _diplo_restore_selected(app), state="disabled")
    app._diplo_restore_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
    app._diplo_pending_var = tk.StringVar(value="")
    ttk.Label(ebar, textvariable=app._diplo_pending_var,
              foreground=tcol("#1A6FA0")).pack(side=tk.LEFT, padx=(8, 0))
    # Help: explain 回應率 (event) vs 回應壓力 (campaign).  Sits top-right.
    ttk.Button(ebar, text=tr("ⓘ 回應率/壓力說明"), style="info.TButton",
               command=lambda: _diplo_show_help(app)).pack(side=tk.RIGHT, padx=(0, 2), pady=2)
    # Snapshot of staged-removed rows so 復原刪除 can put them back.
    app._diplo_removed_snapshot = {}

    box = ttk.LabelFrame(parent, text=tr("王國回應壓力"), padding=(6, 4))
    box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
    app._diplo_box = box
    cols = ("kingdom", "pressure", "event")
    ptree = ttk.Treeview(box, columns=cols, show="headings", selectmode="browse")
    ptree.heading("kingdom", text=tr("王國"))
    ptree.heading("pressure", text=tr("壓力 (0-100)"))
    ptree.heading("event", text=tr("指派回應事件"))
    ptree.column("kingdom", width=185, anchor="w", stretch=False)
    ptree.column("pressure", width=135, anchor="center", stretch=False)
    ptree.column("event", width=256, anchor="w", stretch=True)
    pv = ttk.Scrollbar(box, orient="vertical", command=ptree.yview)
    ptree.configure(yscrollcommand=pv.set)
    ptree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    pv.pack(side=tk.RIGHT, fill=tk.Y)
    ptree.tag_configure("staged", foreground=tcol("#1A6FA0"))
    ptree.tag_configure("removed", foreground=tcol("#C0392B"),
                        font=("Microsoft JhengHei", 10, "overstrike"))
    ptree.bind("<Double-Button-1>", lambda e: _diplo_edit_selected(app))
    ptree.bind("<<TreeviewSelect>>", lambda e: _sync_diplo_edit_bar(app))
    app._diplo_pressure_tree = ptree

    tax_box = ttk.LabelFrame(parent, text=tr("稅收政策（唯讀）"), padding=(6, 4))
    tax_box.pack(fill=tk.X, padx=8, pady=(0, 8))
    app._diplo_tax_var = tk.StringVar(value="")
    ttk.Label(tax_box, textvariable=app._diplo_tax_var,
              foreground=tcol("#6B5B3E"), justify="left").pack(anchor="w")
    app._diplo_tax_text = tk.Text(tax_box, height=4, wrap="none",
                                  font=("Consolas", 9))
    # tax_text is packed on demand in _refresh_diplo_status when policies exist.

    app._diplo_hint_lbl = ttk.Label(
        parent, foreground=tcol("#999999"), font=("", 9),
        text=tr("提示：回應壓力為「既有戰役狀態」，編輯較可能生效；稅收政策結構尚待取樣，暫唯讀。"))
    app._diplo_hint_lbl.pack(side=tk.BOTTOM, anchor="w", padx=8, pady=(0, 4))

    app._diplo_status_refresh = lambda: _refresh_diplo_status(app)
    # Live-sync the edit bar when global edit mode toggles.
    ev = getattr(app, "_dyn_edit_var", None)
    if ev is not None:
        try:
            ev.trace_add("write", lambda *_: _sync_diplo_edit_bar(app))
        except Exception:
            pass
    _refresh_diplo_status(app)


def _diplo_in_edit_mode(app) -> bool:
    ev = getattr(app, "_dyn_edit_var", None)
    return bool(ev is not None and ev.get())


def _sync_diplo_edit_bar(app) -> None:
    """Sync always-visible button states (grey out when not usable).

    ➕ 加入王國 needs edit mode; ✏ 編輯壓力 / 🗑 移除 also need a selected row.
    """
    editing = _diplo_in_edit_mode(app)
    kid = _diplo_selected_kid(app)
    removed = getattr(app, "_diplo_removed_snapshot", None) or {}
    is_removed = bool(kid) and kid in removed   # a struck-through (staged-removed) row
    is_live = bool(kid) and not is_removed
    for attr, on in (("_diplo_add_btn",     editing),
                     ("_diplo_edit_btn",    editing and is_live),
                     ("_diplo_remove_btn",  editing and is_live),
                     ("_diplo_restore_btn", editing and is_removed)):
        b = getattr(app, attr, None)
        if b is not None:
            try:
                b.configure(state="normal" if on else "disabled")
            except Exception:
                pass


def _diplo_effective_pressure(app) -> Dict[str, dict]:
    """Staged pressure if present, else the on-disk bundle's pressure."""
    staged = (getattr(app, "dyn_events_pending", None) or {}).get("pressure")
    if staged is not None:
        return {
            "PressureByKingdomId": dict(staged.get("PressureByKingdomId") or {}),
            "ResponseEventIdByKingdom": dict(staged.get("ResponseEventIdByKingdom") or {}),
        }
    return bundle_pressure(getattr(app, "diplomacy_bundle", None) or {})


def _refresh_diplo_status(app) -> None:
    bundle = getattr(app, "diplomacy_bundle", None) or {}
    ver = bundle.get("Version", "—")
    days = bundle.get("saved_campaign_days")
    try:
        day_s = format_game_time(float(days))
    except (TypeError, ValueError):
        day_s = "—"
    n_stmt = len(bundle_statements(bundle))
    n_evt = len(bundle.get("dynamic_events", []) or [])
    app._diplo_info_var.set(
        tr("外交包 Version {ver}　｜　存檔遊戲日：{day_s}　｜　事件 {n_evt} 筆・聲明 {n_stmt} 筆").format(ver=ver, day_s=day_s, n_evt=n_evt, n_stmt=n_stmt))

    staged = (getattr(app, "dyn_events_pending", None) or {}).get("pressure") is not None
    app._diplo_pending_var.set(tr("⚖ 壓力已暫存（按 💾 儲存生效）") if staged else "")

    # When nothing is staged (committed / discarded / reloaded), the removed-row
    # snapshot is stale — drop it so old strikethrough rows don't linger.
    if not staged:
        app._diplo_removed_snapshot = {}

    p = _diplo_effective_pressure(app)
    tree = app._diplo_pressure_tree
    prev_sel = tree.selection()   # preserve selected kingdom across the rebuild
    tree.delete(*tree.get_children())
    assigned = p["ResponseEventIdByKingdom"]
    live = set(p["PressureByKingdomId"]) | set(assigned)
    for kid in sorted(live,
                      key=lambda k: -(_safe_pressure(p["PressureByKingdomId"].get(k, 0)))):
        eid = str(assigned.get(kid) or "")
        ev = _event_by_id(app, eid) if eid else None
        ev_disp = ((ev or {}).get("title") or (eid[:8] if eid else "—"))
        tree.insert("", "end", iid=kid, tags=(("staged",) if staged else ()), values=(
            _resolve_kingdom(app, kid),
            p["PressureByKingdomId"].get(kid, "—"),
            ev_disp,
        ))

    # Staged-removed rows — shown struck-through so 復原刪除 can restore them.
    removed = getattr(app, "_diplo_removed_snapshot", None) or {}
    for kid, snap in removed.items():
        if kid in live:
            continue
        eid = str(snap.get("eid") or "")
        ev = _event_by_id(app, eid) if eid else None
        ev_disp = ((ev or {}).get("title") or (eid[:8] if eid else "—"))
        tree.insert("", "end", iid=kid, tags=("removed",), values=(
            _resolve_kingdom(app, kid),
            snap.get("pressure", "—"),
            ev_disp,
        ))

    # Restore selection (iids are kingdom ids — stable across the rebuild).
    for kid in prev_sel:
        if tree.exists(kid):
            tree.selection_set(kid)

    policies = ((bundle.get("kingdom_tax") or {}).get("Policies")) or []
    txt = app._diplo_tax_text
    if policies:
        app._diplo_tax_var.set(tr("{v0} 條政策（結構尚待取樣，以原始 JSON 唯讀檢視）").format(v0=len(policies)))
        import json as _json
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("1.0", _json.dumps(policies, ensure_ascii=False, indent=2))
        txt.configure(state="disabled")
        if not txt.winfo_ismapped():
            txt.pack(fill=tk.X, pady=(4, 0))
    else:
        app._diplo_tax_var.set(tr("目前沒有稅收政策"))
        try:
            txt.pack_forget()
        except Exception:
            pass

    _sync_diplo_edit_bar(app)


def _safe_pressure(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# ── Pressure editing (Stage E) ────────────────────────────────────────────────

def _diplo_stage_working(app, pressure: Dict[str, dict]) -> None:
    """Stage the working pressure block and refresh everything."""
    app._dyn_stage_pressure(pressure)
    if hasattr(app, "_dyn_refresh_pending"):
        app._dyn_refresh_pending()
    _refresh_diplo_status(app)


def _diplo_selected_kid(app) -> Optional[str]:
    sel = app._diplo_pressure_tree.selection()
    return sel[0] if sel else None


def _diplo_edit_selected(app) -> None:
    if not _diplo_in_edit_mode(app):
        return
    kid = _diplo_selected_kid(app)
    if not kid:
        return
    _open_pressure_row_editor(app, kid, is_new=False)


def _diplo_remove_selected(app) -> None:
    if not _diplo_in_edit_mode(app):
        return
    kid = _diplo_selected_kid(app)
    if not kid:
        return
    removed = getattr(app, "_diplo_removed_snapshot", None)
    if removed is None:
        removed = app._diplo_removed_snapshot = {}
    if kid in removed:
        return  # already staged-removed
    p = _diplo_effective_pressure(app)
    if kid not in p["PressureByKingdomId"] and kid not in p["ResponseEventIdByKingdom"]:
        return
    # Snapshot current values so 復原刪除 can restore the row, then drop + stage.
    removed[kid] = {
        "pressure": p["PressureByKingdomId"].get(kid),
        "eid": p["ResponseEventIdByKingdom"].get(kid),
    }
    p["PressureByKingdomId"].pop(kid, None)
    p["ResponseEventIdByKingdom"].pop(kid, None)
    _diplo_stage_working(app, p)


def _diplo_restore_selected(app) -> None:
    if not _diplo_in_edit_mode(app):
        return
    kid = _diplo_selected_kid(app)
    if not kid:
        return
    removed = getattr(app, "_diplo_removed_snapshot", None) or {}
    snap = removed.get(kid)
    if snap is None:
        return
    p = _diplo_effective_pressure(app)
    if snap.get("pressure") is not None:
        p["PressureByKingdomId"][kid] = snap["pressure"]
    if snap.get("eid"):
        p["ResponseEventIdByKingdom"][kid] = snap["eid"]
    removed.pop(kid, None)
    _diplo_stage_working(app, p)


def _diplo_show_help(app) -> None:
    """Popup explaining 回應率 (event-scoped) vs 回應壓力 (campaign-scoped)."""
    win = tk.Toplevel(app.root)
    win.title(tr("回應率 vs 回應壓力"))
    W, H = 580, 400
    win.transient(app.root)
    try:
        app._center_window(win, W, H)
    except Exception:
        win.geometry(f"{W}x{H}")
    try:
        win.grab_set()
    except Exception:
        pass
    outer = ttk.Frame(win, padding=12)
    outer.pack(fill=tk.BOTH, expand=True)
    txtf = ttk.Frame(outer)
    txtf.pack(fill=tk.BOTH, expand=True)
    txt = tk.Text(txtf, wrap="word", font=("Microsoft JhengHei", 10),
                  relief="flat", padx=10, pady=8, spacing1=2, spacing3=4)
    vsb = ttk.Scrollbar(txtf, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=vsb.set)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    txt.tag_configure("h", font=("Microsoft JhengHei", 11, "bold"),
                      foreground=tcol("#1A3A5C"), spacing1=8, spacing3=4)
    txt.tag_configure("b", font=("Microsoft JhengHei", 10), foreground=tcol("#222222"))
    txt.insert("end", tr("回應率（事件級・在「事件」分頁的事件詳情中）\n"), "h")
    txt.insert("end",
               tr("每個事件對每個王國各有一個 0–100 的「回應率」（kingdom_engagement）。\n"
                  "它是遊戲「每日為該王國擲骰、決定要不要針對『這個事件』發出統治者聲明」"
                  "的機率。屬於單一事件的屬性——不同事件、不同王國各自不同。\n\n"), "b")
    txt.insert("end", tr("回應壓力（戰役級・在「外交狀態」分頁）\n"), "h")
    txt.insert("end",
               tr("每個王國有一個 0–100 的「回應壓力」（kingdom_response_pressure），"
                  "是跨事件累積的全域外交壓力；壓力越高，王國越可能、越快發出聲明，"
                  "同時記錄「該王國目前被指派回應哪一個事件」。屬於整個戰役的狀態。\n\n"), "b")
    txt.insert("end", tr("一句話區分\n"), "h")
    txt.insert("end",
               tr("回應率＝「對這個事件，今天會不會回應」的機率（事件級）；\n"
                  "回應壓力＝「這個王國整體有多想／多快發聲」的累積值（戰役級）。\n"), "b")
    txt.configure(state="disabled")
    ttk.Button(outer, text=tr("關閉"), command=win.destroy,
               style="secondary.TButton").pack(anchor="e", pady=(8, 0))


def _diplo_kingdom_universe(app) -> List[str]:
    """All kingdom ids known from terminology + events + current pressure."""
    ks: set = set()
    for src in ("terminology_campaign", "terminology_primary", "terminology_fallback"):
        payload = getattr(app, src, None) or {}
        kd = payload.get("kingdoms") if isinstance(payload, dict) else None
        if isinstance(kd, dict):
            ks.update(str(k) for k in kd.keys())
    bundle = getattr(app, "diplomacy_bundle", None) or {}
    for e in bundle.get("dynamic_events", []) or []:
        for k in (e.get("kingdoms_involved", []) or []):
            ks.add(str(k))
    p = _diplo_effective_pressure(app)
    ks.update(p["PressureByKingdomId"].keys())
    return sorted(ks)


def _diplo_add_kingdom(app) -> None:
    if not _diplo_in_edit_mode(app):
        return
    p = _diplo_effective_pressure(app)
    existing = set(p["PressureByKingdomId"]) | set(p["ResponseEventIdByKingdom"])
    avail = [k for k in _diplo_kingdom_universe(app) if k not in existing]
    if not avail:
        return
    _open_pressure_row_editor(app, None, is_new=True, candidates=avail)


def _open_pressure_row_editor(app, kid: Optional[str], *, is_new: bool,
                              candidates: Optional[List[str]] = None) -> None:
    p = _diplo_effective_pressure(app)
    win = tk.Toplevel(app.root)
    win.title(tr("加入王國回應壓力") if is_new else tr("編輯回應壓力"))
    win.geometry("460x230")
    try:
        app._center_window(win, 460, 230)
    except Exception:
        pass
    win.transient(app.root)
    win.grab_set()

    body = ttk.Frame(win, padding=12)
    body.pack(fill=tk.BOTH, expand=True)

    # Kingdom row
    ttk.Label(body, text=tr("王國:"), width=10, anchor="e").grid(row=0, column=0, sticky="e", pady=4)
    if is_new:
        kid_disp_to_id = {f"{_resolve_kingdom(app, k)} ({k})": k for k in (candidates or [])}
        kid_var = tk.StringVar(value=next(iter(kid_disp_to_id), ""))
        ttk.Combobox(body, textvariable=kid_var, state="readonly", width=28,
                     values=list(kid_disp_to_id)).grid(row=0, column=1, sticky="w", pady=4)
    else:
        ttk.Label(body, text=f"{_resolve_kingdom(app, kid)} ({kid})").grid(
            row=0, column=1, sticky="w", pady=4)

    # Pressure
    ttk.Label(body, text=tr("壓力 (0-100):"), width=10, anchor="e").grid(row=1, column=0, sticky="e", pady=4)
    cur_pre = _safe_pressure(p["PressureByKingdomId"].get(kid, 50)) if not is_new else 50
    pre_var = tk.StringVar(value=str(cur_pre))
    ttk.Spinbox(body, from_=0, to=100, width=8, textvariable=pre_var).grid(row=1, column=1, sticky="w", pady=4)

    # Assigned response event
    ttk.Label(body, text=tr("指派回應事件:"), width=10, anchor="e").grid(row=2, column=0, sticky="ne", pady=4)
    bundle = getattr(app, "diplomacy_bundle", None) or {}
    none_lbl = tr("（無）")
    ev_disp_to_id = {none_lbl: ""}
    for e in bundle.get("dynamic_events", []) or []:
        eid = str(e.get("id", ""))
        if not eid:
            continue
        ev_disp_to_id[f"{str(e.get('title') or eid[:8])[:30]} ({eid[:8]})"] = eid
    cur_eid = str(p["ResponseEventIdByKingdom"].get(kid, "")) if not is_new else ""
    cur_disp = next((d for d, i in ev_disp_to_id.items() if i == cur_eid), none_lbl)
    ev_var = tk.StringVar(value=cur_disp)
    ttk.Combobox(body, textvariable=ev_var, state="readonly", width=36,
                 values=list(ev_disp_to_id)).grid(row=2, column=1, sticky="w", pady=4)

    err_var = tk.StringVar(value="")
    ttk.Label(body, textvariable=err_var, foreground=tcol("#C0392B")).grid(
        row=3, column=0, columnspan=2, sticky="w")

    def _save():
        if is_new:
            sel_kid = kid_disp_to_id.get(kid_var.get())
            if not sel_kid:
                err_var.set(tr("請選擇王國"))
                return
            target = sel_kid
        else:
            target = kid
        try:
            pre = max(0, min(100, int(pre_var.get())))
        except (TypeError, ValueError):
            err_var.set(tr("壓力需為 0-100 的整數"))
            return
        eid = ev_disp_to_id.get(ev_var.get(), "")
        work = _diplo_effective_pressure(app)
        work["PressureByKingdomId"][target] = pre
        if eid:
            work["ResponseEventIdByKingdom"][target] = eid
        else:
            work["ResponseEventIdByKingdom"].pop(target, None)
        _diplo_stage_working(app, work)
        win.destroy()

    foot = ttk.Frame(win, padding=(10, 4, 10, 8))
    foot.pack(side=tk.BOTTOM, fill=tk.X)
    ttk.Button(foot, text=tr("確定"), command=_save,
               style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(foot, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
