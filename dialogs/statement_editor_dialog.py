"""Popup editor for a single ruler statement (Phase 6 Stage C).

Works on the unified statement model (services.diplomacy_service); on save the
model is staged into ``app.dyn_events_pending`` via ``app._stmt_stage_edit`` /
``app._stmt_stage_new`` — actual file writing happens in ``app._dyn_commit``
(dual-format sync handled by the service layer).

Modes
-----
* Edit:  ``open_statement_editor(app, key=<stmt_key>)`` — speaker kingdom and
  linked event are fixed; everything else editable.  The model is loaded with
  the embedded twin's fields overlaid (relation_changes etc.).
* New:   ``open_statement_editor(app, key=None)`` — speaker kingdom + linked
  event are choosable; campaign_days defaults to the bundle's saved day.

Dependencies expected on *app*:
    app.diplomacy_bundle, app.world_dynamic_events_items
    app.resolve_kingdom_name(kid)
    app._stmt_stage_edit(key, model) / app._stmt_stage_new(model)
    app._stmt_refresh() / app._dyn_refresh_pending()
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Any, Dict, List, Optional, Set

from i18n import tr
from widgets.name_id_combo import NameIdCombo
from services.diplomacy_service import (
    DIPLOMATIC_ACTIONS,
    SETTLEMENT_ACTIONS,
    bundle_statements,
    statement_keys,
    parse_statement_with_twin,
    new_statement,
)
from dialogs.dynamic_event_editor_dialog import _DateField
from ui.statements_subtab import _action_labels
from ui.theme import labeled_frame


def _kingdom_universe(app) -> List[str]:
    """Union of bundle kingdoms + terminology kingdoms, sorted by display."""
    out: Set[str] = set()
    bundle = getattr(app, "diplomacy_bundle", None) or {}
    for s in bundle_statements(bundle):
        for k in [s.get("kingdom_id")] + list(s.get("target_kingdom_ids") or []):
            ks = str(k or "")
            if ks and ks.lower() not in ("null", "all"):
                out.add(ks)
    for ev in bundle.get("dynamic_events", []) or []:
        for k in (ev.get("kingdom_engagement") or {}):
            out.add(str(k))
    for source in ("terminology_campaign", "terminology_primary", "terminology_fallback"):
        payload = getattr(app, source, None) or {}
        kdict = payload.get("kingdoms") if isinstance(payload, dict) else None
        if isinstance(kdict, dict):
            out.update(str(k) for k in kdict)
    resolver = getattr(app, "resolve_kingdom_name", lambda k: k)
    return sorted(out, key=lambda k: str(resolver(k) or k))


def open_statement_editor(app, key: Optional[str] = None,
                          preload_model: Optional[dict] = None,
                          replace_new_index: Optional[int] = None) -> None:
    """Open the statement editor.

    * ``key`` given → edit that existing statement.
    * ``key=None``  → create a new statement; ``preload_model`` (optional)
      re-opens a staged-new model, and ``replace_new_index`` makes save
      replace that buffer slot instead of appending (cancel keeps original).
    """
    bundle = getattr(app, "diplomacy_bundle", None)
    if not isinstance(bundle, dict):
        messagebox.showinfo(tr("聲明編輯"), tr("目前戰役為舊版格式，無聲明資料。"),
                            parent=app.root)
        return

    is_new = key is None
    resolver = getattr(app, "resolve_kingdom_name", lambda k: k)
    labels = _action_labels()
    label_to_action = {v: k for k, v in labels.items()}

    # ── Load model ─────────────────────────────────────────────────────
    if is_new:
        if preload_model is not None:
            model = preload_model
        else:
            try:
                day0 = float(bundle.get("saved_campaign_days") or 0.0)
            except (TypeError, ValueError):
                day0 = 0.0
            model = new_statement("", None, day0)
    else:
        stmts = bundle_statements(bundle)
        keys = statement_keys(stmts)
        try:
            idx = keys.index(key)
        except ValueError:
            messagebox.showerror(tr("聲明編輯"), tr("找不到該聲明（可能已重新載入）。"),
                                 parent=app.root)
            return
        stmt = stmts[idx]
        eid = str(stmt.get("event_id") or "")
        event = None
        for e in bundle.get("dynamic_events", []) or []:
            if str(e.get("id", "")) == eid:
                event = e
                break
        # Staged edit takes precedence so re-opening shows pending state.
        staged = (app.dyn_events_pending.get("stmt_edits") or {}).get(key)
        model = dict(staged) if staged else parse_statement_with_twin(stmt, event)
    initial_rels = [dict(r) for r in (model.get("relation_changes") or [])]

    kingdoms = _kingdom_universe(app)
    kingdom_disp = [f"{resolver(k) or k} ({k})" for k in kingdoms]
    disp_to_kid = dict(zip(kingdom_disp, kingdoms))
    kid_to_disp = dict(zip(kingdoms, kingdom_disp))

    events = bundle.get("dynamic_events", []) or []
    evt_disp = [tr("（無關聯事件）")] + [
        f"{(e.get('title') or '')[:24]} ({str(e.get('id',''))[:8]})" for e in events]
    evt_ids: List[Optional[str]] = [None] + [str(e.get("id", "")) for e in events]

    # ── Window ─────────────────────────────────────────────────────────
    win = tk.Toplevel(app.root)
    win.title(tr("➕ 新增聲明") if is_new else tr("✏ 編輯聲明"))
    W, H = 760, 720
    win.geometry(f"{W}x{H}")
    app._center_window(win, W, H)
    win.transient(app.root)
    win.grab_set()

    # Bottom button bar — packed FIRST so the scroll canvas can't squeeze it out.
    bar = ttk.Frame(win)
    bar.pack(side=tk.BOTTOM, fill=tk.X, pady=8, padx=10)

    # Scrollable body
    canvas = tk.Canvas(win, highlightthickness=0)
    vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
    body = ttk.Frame(canvas)
    body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=body, anchor="nw", width=W - 30)
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    # ── Header: speaker / event / date ─────────────────────────────────
    head = labeled_frame(body, text=tr("基本資訊"))
    head.pack(fill=tk.X, padx=10, pady=(10, 4))
    hg = ttk.Frame(head)
    hg.pack(fill=tk.X, padx=6, pady=4)

    ttk.Label(hg, text=tr("發言王國:")).grid(row=0, column=0, sticky="w")
    speaker_var = tk.StringVar(value=kid_to_disp.get(model["kingdom_id"], model["kingdom_id"]))
    speaker_cb = ttk.Combobox(hg, textvariable=speaker_var, values=kingdom_disp,
                              state=("readonly" if is_new else "disabled"), width=24)
    speaker_cb.grid(row=0, column=1, sticky="w", padx=(4, 16))

    ttk.Label(hg, text=tr("關聯事件:")).grid(row=0, column=2, sticky="w")
    cur_eid = model.get("event_id")
    try:
        evt_idx = evt_ids.index(cur_eid)
    except ValueError:
        evt_idx = 0
    event_var = tk.StringVar(value=evt_disp[evt_idx])
    event_cb = ttk.Combobox(hg, textvariable=event_var, values=evt_disp,
                            state=("readonly" if is_new else "disabled"), width=34)
    event_cb.grid(row=0, column=3, sticky="w", padx=(4, 0))

    ttk.Label(hg, text=tr("日期:")).grid(row=1, column=0, sticky="w", pady=(6, 0))
    date_field = _DateField(hg, initial_value=model["campaign_days"])
    date_field.frame.grid(row=1, column=1, columnspan=3, sticky="w", padx=(4, 0), pady=(6, 0))

    # ── Actions (per-row: action / target kingdom / settlement) ───────
    act_frame = labeled_frame(body, text=tr("動作（依序；對象王國與定居點逐動作對應）"))
    act_frame.pack(fill=tk.X, padx=10, pady=4)
    act_rows_holder = ttk.Frame(act_frame)
    act_rows_holder.pack(fill=tk.X, padx=6, pady=(2, 0))
    act_rows: List[dict] = []

    def _settlement_state(action_name_: str) -> str:
        return "normal" if action_name_ in SETTLEMENT_ACTIONS else "disabled"

    def _add_action_row(action: str = "None", target: str = "",
                        settlement: Optional[str] = None) -> None:
        rowf = ttk.Frame(act_rows_holder)
        rowf.pack(fill=tk.X, pady=2)
        a_var = tk.StringVar(value=labels.get(action, action))
        a_cb = ttk.Combobox(rowf, textvariable=a_var,
                            values=[labels[n] for n in DIPLOMATIC_ACTIONS],
                            state="readonly", width=14)
        a_cb.pack(side=tk.LEFT)
        ttk.Label(rowf, text=tr("對象:")).pack(side=tk.LEFT, padx=(8, 2))
        t_var = tk.StringVar(value=kid_to_disp.get(target, "" if target.lower() in ("", "null") else target))
        ttk.Combobox(rowf, textvariable=t_var, values=[""] + kingdom_disp,
                     state="readonly", width=20).pack(side=tk.LEFT)
        ttk.Label(rowf, text=tr("定居點:")).pack(side=tk.LEFT, padx=(8, 2))
        s_combo = NameIdCombo(rowf, app, "settlements",
                              initial_id=(settlement or ""), width=16,
                              autocomplete=True)
        s_combo.set_state(_settlement_state(action))
        s_combo.pack(side=tk.LEFT)
        row = {"frame": rowf, "action": a_var, "target": t_var,
               "settlement": s_combo}

        def _on_action_change(*_):
            name = label_to_action.get(a_var.get(), a_var.get())
            s_combo.set_state(_settlement_state(name))
        a_var.trace_add("write", _on_action_change)

        def _remove():
            act_rows.remove(row)
            rowf.destroy()
        ttk.Button(rowf, text="✕", width=2, style="secondary.TButton",
                   command=_remove).pack(side=tk.LEFT, padx=(8, 0))
        act_rows.append(row)

    names0 = model["action_names"] or ["None"]
    targets0 = list(model["target_kingdom_ids"] or [])
    if model["settlement_ids"] is not None:
        settls0: List[Optional[str]] = list(model["settlement_ids"])
    else:
        raw = model.get("settlement_id_raw")
        settls0 = [raw] + [None] * (len(names0) - 1) if raw else [None] * len(names0)
    for i, n in enumerate(names0):
        _add_action_row(
            n,
            targets0[i] if i < len(targets0) else "",
            settls0[i] if i < len(settls0) else None,
        )
    ttk.Button(act_frame, text=tr("＋ 加入動作"), style="info.TButton",
               command=lambda: _add_action_row()).pack(anchor="w", padx=6, pady=(2, 4))

    # ── Scalar parameters ──────────────────────────────────────────────
    par = labeled_frame(body, text=tr("參數（依動作需要填寫）"))
    par.pack(fill=tk.X, padx=10, pady=4)
    pg = ttk.Frame(par)
    pg.pack(fill=tk.X, padx=6, pady=4)
    scalar_vars: Dict[str, tk.StringVar] = {}
    scalar_defs = [
        ("daily_tribute_amount",          tr("貢金/日"), 8),
        ("tribute_duration_days",         tr("貢金天數"), 8),
        ("reparations_amount",            tr("賠款"), 8),
        ("trade_agreement_duration_years", tr("貿易年數"), 8),
        ("tax_rate_percent",              tr("稅率 %"), 8),
        ("tax_scope",                     tr("稅範圍"), 14),
        ("tax_settlement_id",             tr("課稅定居點"), 14),
        ("target_clan_id",                tr("目標氏族"), 14),
        ("quarantine_duration_days",      tr("隔離天數"), 8),
    ]
    scalar_widgets: Dict[str, NameIdCombo] = {}   # id-typed scalars use NameIdCombo
    _scalar_categories = {"tax_settlement_id": "settlements", "target_clan_id": "clans"}
    for i, (fkey, flabel, width) in enumerate(scalar_defs):
        r, c = divmod(i, 3)
        ttk.Label(pg, text=flabel + ":").grid(row=r, column=c * 2, sticky="w",
                                              padx=(0 if c == 0 else 12, 2), pady=2)
        v = model.get(fkey)
        cur = "" if v in (None, "") else str(v)
        if fkey in _scalar_categories:
            w = NameIdCombo(pg, app, _scalar_categories[fkey], initial_id=cur,
                            width=width, autocomplete=True)
            w.grid(row=r, column=c * 2 + 1, sticky="w", pady=2)
            scalar_widgets[fkey] = w
        else:
            sv = tk.StringVar(value=cur)
            scalar_vars[fkey] = sv
            ttk.Entry(pg, textvariable=sv, width=width).grid(row=r, column=c * 2 + 1,
                                                             sticky="w", pady=2)

    # ── relation_changes ───────────────────────────────────────────────
    rel = labeled_frame(body, text=tr("關係變化（寫入事件內嵌副本）"))
    rel.pack(fill=tk.X, padx=10, pady=4)
    rel_holder = ttk.Frame(rel)
    rel_holder.pack(fill=tk.X, padx=6, pady=(2, 0))
    rel_rows: List[dict] = []

    def _add_rel_row(toward: str = "", change: Any = -5, reason: str = "") -> None:
        rowf = ttk.Frame(rel_holder)
        rowf.pack(fill=tk.X, pady=2)
        k_var = tk.StringVar(value=kid_to_disp.get(toward, toward))
        ttk.Combobox(rowf, textvariable=k_var, values=kingdom_disp,
                     state="readonly", width=20).pack(side=tk.LEFT)
        c_var = tk.StringVar(value=str(change))
        ttk.Spinbox(rowf, textvariable=c_var, from_=-100, to=100, width=5).pack(
            side=tk.LEFT, padx=(8, 0))
        r_var = tk.StringVar(value=reason)
        ttk.Entry(rowf, textvariable=r_var, width=40).pack(side=tk.LEFT, padx=(8, 0),
                                                           fill=tk.X, expand=True)
        row = {"frame": rowf, "toward": k_var, "change": c_var, "reason": r_var}

        def _remove():
            rel_rows.remove(row)
            rowf.destroy()
        ttk.Button(rowf, text="✕", width=2, style="secondary.TButton",
                   command=_remove).pack(side=tk.LEFT, padx=(8, 0))
        rel_rows.append(row)

    for r in initial_rels:
        _add_rel_row(str(r.get("toward_kingdom_id") or ""), r.get("change", 0),
                     str(r.get("reason") or ""))
    ttk.Button(rel, text=tr("＋ 加入關係變化"), style="info.TButton",
               command=lambda: _add_rel_row()).pack(anchor="w", padx=6, pady=(2, 4))

    # ── Reason + full text ─────────────────────────────────────────────
    rs = labeled_frame(body, text=tr("理由（AI 內部動機）"))
    rs.pack(fill=tk.X, padx=10, pady=4)
    reason_txt = tk.Text(rs, wrap="word", height=3, font=("Microsoft JhengHei", 10))
    reason_txt.pack(fill=tk.X, padx=6, pady=4)
    reason_txt.insert("1.0", model.get("reason") or "")

    ft = labeled_frame(body, text=tr("聲明全文"))
    ft.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
    text_txt = tk.Text(ft, wrap="word", height=9, font=("Microsoft JhengHei", 10))
    text_txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
    text_txt.insert("1.0", model.get("statement_text") or "")

    # ── Save / cancel ──────────────────────────────────────────────────
    def _collect_and_stage() -> None:
        # speaker / event
        if is_new:
            kid = disp_to_kid.get(speaker_var.get(), "")
            if not kid:
                messagebox.showwarning(tr("聲明編輯"), tr("請選擇發言王國。"), parent=win)
                return
            model["kingdom_id"] = kid
            try:
                model["event_id"] = evt_ids[evt_disp.index(event_var.get())]
            except ValueError:
                model["event_id"] = None
        try:
            model["campaign_days"] = float(date_field.get())
        except (TypeError, ValueError):
            messagebox.showwarning(tr("聲明編輯"), tr("日期格式無法解析。"), parent=win)
            return

        # actions / per-action targets & settlements
        names: List[str] = []
        targets: List[str] = []
        settls: List[Optional[str]] = []
        for row in act_rows:
            name = label_to_action.get(row["action"].get(), row["action"].get())
            names.append(name)
            tk_id = disp_to_kid.get(row["target"].get(), "")
            targets.append(tk_id if tk_id else "null")
            s = row["settlement"].get_id().strip()
            settls.append(s if (s and name in SETTLEMENT_ACTIONS) else None)
        if not names:
            names = ["None"]
            targets, settls = [], [None]
        model["action_names"] = names
        # targets: drop list entirely when nothing meaningful
        if all(t == "null" for t in targets):
            model["target_kingdom_ids"] = []
        elif len(targets) == 1:
            model["target_kingdom_ids"] = [t for t in targets if t != "null"]
        else:
            model["target_kingdom_ids"] = targets
        model["settlement_ids"] = settls
        model["settlement_id_raw"] = None

        # scalars
        def _num(sv: str, *, as_float: bool, default):
            s = sv.strip()
            if not s:
                return default
            try:
                return float(s) if as_float else int(float(s))
            except (TypeError, ValueError):
                return default
        model["daily_tribute_amount"]  = _num(scalar_vars["daily_tribute_amount"].get(),  as_float=False, default=0)
        model["tribute_duration_days"] = _num(scalar_vars["tribute_duration_days"].get(), as_float=False, default=0)
        model["reparations_amount"]    = _num(scalar_vars["reparations_amount"].get(),    as_float=False, default=0)
        model["trade_agreement_duration_years"] = _num(
            scalar_vars["trade_agreement_duration_years"].get(), as_float=True, default=1.0)
        model["tax_rate_percent"]      = _num(scalar_vars["tax_rate_percent"].get(),      as_float=True, default=0.0)
        model["quarantine_duration_days"] = _num(
            scalar_vars["quarantine_duration_days"].get(), as_float=False, default=0)
        for fkey in ("tax_scope", "tax_settlement_id", "target_clan_id"):
            if fkey in scalar_widgets:
                s = scalar_widgets[fkey].get_id().strip()
            else:
                s = scalar_vars[fkey].get().strip()
            model[fkey] = s or None

        # relation_changes
        rels: List[dict] = []
        for row in rel_rows:
            kid = disp_to_kid.get(row["toward"].get(), "")
            if not kid:
                continue
            try:
                chg = int(float(row["change"].get()))
            except (TypeError, ValueError):
                chg = 0
            rels.append({"toward_kingdom_id": kid, "change": chg,
                         "reason": row["reason"].get().strip()})
        model["relation_changes"] = rels
        if rels != initial_rels:
            model["_embedded_overlay"] = True
            model["_embedded_overlay_dirty"] = True

        model["reason"] = reason_txt.get("1.0", "end-1c").strip()
        model["statement_text"] = text_txt.get("1.0", "end-1c").strip()

        if is_new:
            new_list = app.dyn_events_pending.setdefault("stmt_new", [])
            if replace_new_index is not None and 0 <= replace_new_index < len(new_list):
                new_list[replace_new_index] = model
            else:
                app._stmt_stage_new(model)
        else:
            app._stmt_stage_edit(key, model)
        if hasattr(app, "_dyn_refresh_pending"):
            app._dyn_refresh_pending()
        if hasattr(app, "_stmt_refresh"):
            app._stmt_refresh()
        win.destroy()

    ttk.Button(bar, text=tr("💾 暫存變更"), command=_collect_and_stage,
               style="success.TButton").pack(side=tk.RIGHT, padx=(6, 16))
    ttk.Button(bar, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT)
