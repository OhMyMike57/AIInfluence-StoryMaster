"""Popup editor for a single dynamic event (Phase 5.3 / 0.5.3).

Builds on the staging buffer (``app.dyn_events_pending``) — the dialog
collects an edited copy of the event and on save calls
``app._dyn_stage_edit(event_id, field, new_value)`` for each field that
differs from the on-disk value.  Field-level equality means staging
auto-cancels for fields the user reverted.

Editable fields (see :data:`services.dynamic_event_service.EDITABLE_EVENT_FIELDS`):
    title, type, importance, expiration_campaign_days,
    kingdoms_involved, characters_involved, event_history

The top-level ``description`` and ``creation_campaign_days`` are NOT
edited directly; they are auto-derived from the latest / earliest
``event_history`` entry by ``svc.apply_event_edits`` at commit time.

Dependencies expected on *app*:
    app.world_dynamic_events_items   List[dict]
    app.dyn_events_pending           {"edits": {eid: {field: val}},
                                       "delete_ids": set[str]}
    app.character_meta               Dict[display, meta]
    app.plain_to_path                Dict[display, Path]   (display + sid lookup)
    app.terminology_campaign / primary / fallback (kingdom universe)
    app.resolve_kingdom_name(kid)    -> display name
    app.resolve_display_name(sid)    -> (display, source)
    app._dyn_stage_edit(eid, field, new)
    app._dyn_stage_delete(eid)
    app._dyn_stage_undelete(eid)
"""
from __future__ import annotations

import shutil
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Any, Dict, List, Optional, Set, Tuple

from i18n import tr
from widgets.name_id_combo import NameIdCombo
from widgets.image_view import ImageThumbnail
from widgets.image_picker import open_image_picker, PICKER_REMOVE
from services import display_labels
from services.dynamic_event_service import (
    KNOWN_TYPE_KEYS,
    normalize_type,
    apply_event_edits,
    normalize_economic_effect,
    APPLICABLE_NPC_KEYS,
)
from widgets.game_date_field import GameDateField as _DateField
from ui.theme import paint, labeled_frame
from ui.theme import tcol


# ── Type-key → translated display label ───────────────────────────────────────
def _type_label_map() -> Dict[str, str]:
    return {
        "military":         tr("軍事"),
        "political":        tr("政治"),
        "economic":         tr("經濟"),
        "social":           tr("社會"),
        "mysterious":       tr("神秘"),
        "news":             tr("新聞"),
        "local":            tr("地方"),
        "rumor":            tr("謠言"),
        "diseaseoutbreak":  tr("疫情爆發"),
        "other":            tr("其它"),
    }


# Always show the player as a selectable character.  ``main_hero`` does
# not have a JSON file, so it won't appear in app.character_meta — we
# inject it here so the user can toggle it on or off.
PLAYER_SID = "main_hero"
PLAYER_DISPLAY_LABEL = lambda: tr("玩家 (main_hero)")


def open_dynamic_event_editor(app, event_id: str, *, new_index: Optional[int] = None) -> None:
    """Open a Toplevel editor for a dynamic event.

    *new_index* not ``None`` → edit a **staged-new** event in place
    (``app.dyn_events_pending["new_events"][new_index]``); save replaces the whole
    dict in that slot.  Otherwise edit an on-disk event by *event_id* with
    field-level staging (toggling a field back to its original auto-cancels).
    """
    is_new = new_index is not None
    if is_new:
        nlist = (getattr(app, "dyn_events_pending", None) or {}).get("new_events", [])
        if not (isinstance(new_index, int) and 0 <= new_index < len(nlist)):
            messagebox.showwarning(tr("編輯動態事件"),
                                   tr("找不到暫存的新事件。"), parent=app.root)
            return
        event = nlist[new_index]
        event_id = str(event.get("id", ""))
        pending_edits: Dict[str, Any] = {}
        is_pending_delete = False
    else:
        event = next(
            (e for e in (app.world_dynamic_events_items or [])
             if str(e.get("id", "")) == event_id),
            None,
        )
        if event is None:
            messagebox.showwarning(
                tr("編輯動態事件"),
                tr("找不到 id={event_id} 的事件。").format(event_id=event_id),
                parent=app.root,
            )
            return
        pending = getattr(app, "dyn_events_pending", None) or {}
        pending_edits = (pending.get("edits") or {}).get(event_id, {})
        is_pending_delete = event_id in (pending.get("delete_ids") or set())

    def eff(key, default=None):
        return pending_edits[key] if key in pending_edits else event.get(key, default)

    # ── Window ────────────────────────────────────────────────────────────────
    win = tk.Toplevel(app.root)
    win.title(tr("新增動態事件") if is_new else tr("編輯動態事件"))
    win.geometry("1180x820")
    try:
        app._center_window(win, 1180, 820)
    except Exception:
        pass
    win.transient(app.root)
    win.grab_set()

    # State holders
    title_var = tk.StringVar(value=str(eff("title", "")))
    importance_var = tk.IntVar(value=int(eff("importance", 1) or 1))
    type_label_map = _type_label_map()
    type_display_to_key = {type_label_map[k]: k for k in KNOWN_TYPE_KEYS}
    cur_type_key = normalize_type(eff("type", "")) or KNOWN_TYPE_KEYS[-1]
    if cur_type_key not in type_label_map:
        cur_type_key = "other"
    type_var = tk.StringVar(value=type_label_map[cur_type_key])

    cur_kingdoms: List[str] = [str(k) for k in (eff("kingdoms_involved", []) or [])]
    cur_chars:    List[str] = [str(c) for c in (eff("characters_involved", []) or [])]
    cur_history:  List[dict] = [dict(h) for h in (eff("event_history", []) or []) if isinstance(h, dict)]

    # New (Stage D) state holders
    player_var = tk.BooleanVar(value=bool(eff("player_involved", False)))
    cur_applicable: List[str] = [str(x) for x in (eff("applicable_npcs", []) or [])]
    cur_participating: List[str] = [str(k) for k in (eff("participating_kingdoms", []) or [])]
    cur_engagement: Dict[str, int] = {}
    for _k, _v in (eff("kingdom_engagement", {}) or {}).items():
        try:
            cur_engagement[str(_k)] = max(0, min(100, int(_v)))
        except (TypeError, ValueError):
            continue
    cur_eco: List[dict] = [dict(e) for e in (eff("economic_effects", []) or []) if isinstance(e, dict)]
    embedded_stmts: List[dict] = [s for s in (event.get("kingdom_statements", []) or []) if isinstance(s, dict)]
    schedule_state = {"cleared": False}  # set True when user clicks "清空排程"

    banner_var = tk.StringVar(value="")
    if is_new:
        banner_var.set(tr("➕ 新事件（尚未儲存；按 💾 儲存才會寫入外交包）"))
    elif is_pending_delete:
        banner_var.set(tr("⚠ 此事件已暫存刪除（按 💾 儲存才會生效）"))
    elif pending_edits:
        banner_var.set(tr("✏ 此事件有未儲存的暫存編輯"))

    # ── Top row: ID + delete/restore + banner ─────────────────────────────────
    head = ttk.Frame(win, padding=(10, 8, 10, 4))
    head.pack(fill=tk.X)
    ttk.Label(head, text=tr("ID:"), foreground=tcol("#666666")).pack(side=tk.LEFT)
    ttk.Label(head, text=event_id, foreground=tcol("#444444"),
              font=("Consolas", 9)).pack(side=tk.LEFT, padx=(4, 12))

    def on_delete():
        if is_new:
            # Drop the staged-new event entirely.
            app._dyn_unstage_new_event(new_index)
            win.destroy()
            _refresh_tab_safely(app)
            return
        if not messagebox.askyesno(
            tr("確認刪除"),
            tr("刪除後將從 dynamic_events.json 移除此事件，並清除所有 NPC JSON 中的引用。\n"
               "（按 💾 儲存才會實際寫入；按 ↩ 取消可復原）\n\n要繼續嗎？"),
            parent=win,
        ):
            return
        app._dyn_stage_delete(event_id)
        win.destroy()
        _refresh_tab_safely(app)

    def on_restore():
        app._dyn_stage_undelete(event_id)
        win.destroy()
        _refresh_tab_safely(app)

    if is_new:
        ttk.Button(head, text=tr("🗑 移除此新事件"), command=on_delete,
                   style="danger.TButton").pack(side=tk.RIGHT)
    elif is_pending_delete:
        ttk.Button(head, text=tr("↩ 復原"), command=on_restore,
                   style="secondary.TButton").pack(side=tk.RIGHT)
    else:
        ttk.Button(head, text=tr("🗑 刪除此事件"), command=on_delete,
                   style="danger.TButton").pack(side=tk.RIGHT)

    if banner_var.get():
        ttk.Label(win, textvariable=banner_var, foreground=tcol("#888888"),
                  font=("Microsoft JhengHei", 9, "italic")).pack(
            anchor="w", padx=10, pady=(0, 2))

    # Footer reserved at the BOTTOM before the notebook so the 完成/取消 buttons
    # are never clipped when a tab's content is tall (Tk pack clips the
    # last-packed widget first; bottom-docking it early fixes that).
    foot = ttk.Frame(win, padding=(10, 4, 10, 8))
    foot.pack(side=tk.BOTTOM, fill=tk.X)
    ttk.Separator(win, orient="horizontal").pack(side=tk.BOTTOM, fill=tk.X)

    # ── Notebook: 基本 / 外交 / 經濟效果 ───────────────────────────────────────
    nb = ttk.Notebook(win)
    nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 0))
    tab_basic = ttk.Frame(nb)
    tab_diplo = ttk.Frame(nb)
    tab_eco   = ttk.Frame(nb)
    tab_image = ttk.Frame(nb)
    nb.add(tab_basic, text=tr("📋 基本"))
    nb.add(tab_diplo, text=tr("🏛 外交"))
    nb.add(tab_eco,   text=tr("💰 經濟效果"))
    nb.add(tab_image, text=tr("🖼 圖像"))
    _build_event_image_tab(app, tab_image, event_id)

    # ── Form: title / type / importance / expiration ──────────────────────────
    form = ttk.Frame(tab_basic, padding=(10, 4, 10, 4))
    form.pack(fill=tk.X)

    ttk.Label(form, text=tr("標題:"), width=8, anchor="e").grid(
        row=0, column=0, sticky="e", padx=(0, 4), pady=2)
    ttk.Entry(form, textvariable=title_var).grid(
        row=0, column=1, columnspan=5, sticky="ew", pady=2)

    ttk.Label(form, text=tr("類型:"), width=8, anchor="e").grid(
        row=1, column=0, sticky="e", padx=(0, 4), pady=2)
    type_cb = ttk.Combobox(
        form, textvariable=type_var, state="readonly", width=14,
        values=[type_label_map[k] for k in KNOWN_TYPE_KEYS],
    )
    type_cb.grid(row=1, column=1, sticky="w", pady=2)

    ttk.Label(form, text=tr("重要度:"), width=8, anchor="e").grid(
        row=1, column=2, sticky="e", padx=(8, 4), pady=2)
    ttk.Spinbox(form, from_=1, to=9, width=5,
                textvariable=importance_var).grid(row=1, column=3, sticky="w", pady=2)

    ttk.Label(form, text=tr("到期日期:"), width=8, anchor="e").grid(
        row=2, column=0, sticky="e", padx=(0, 4), pady=2)
    expiry_field = _DateField(form, initial_value=eff("expiration_campaign_days", 0.0))
    expiry_field.frame.grid(row=2, column=1, columnspan=5, sticky="w", pady=2)

    # Player involved
    ttk.Label(form, text=tr("涉及玩家:"), width=8, anchor="e").grid(
        row=3, column=0, sticky="e", padx=(0, 4), pady=2)
    ttk.Checkbutton(form, variable=player_var,
                    text=tr("此事件與玩家相關")).grid(
        row=3, column=1, columnspan=5, sticky="w", pady=2)

    # Applicable NPC audiences (all ↔ rest mutually exclusive)
    ttk.Label(form, text=tr("適用對象:"), width=8, anchor="e").grid(
        row=4, column=0, sticky="ne", padx=(0, 4), pady=2)
    appl_box = ttk.Frame(form)
    appl_box.grid(row=4, column=1, columnspan=5, sticky="w", pady=2)
    applicable_vars: Dict[str, tk.BooleanVar] = {}
    for col, key in enumerate(APPLICABLE_NPC_KEYS):
        v = tk.BooleanVar(value=(key in cur_applicable))
        applicable_vars[key] = v
        ttk.Checkbutton(appl_box, variable=v,
                        text=display_labels.applicable_npc_label(key)).grid(
            row=0, column=col, sticky="w", padx=(0, 8))

    def _sync_applicable(*_):
        all_on = applicable_vars["all"].get()
        for k, v in applicable_vars.items():
            if k == "all":
                continue
            # When "all" is on, the specific tags are redundant — clear & lock.
            if all_on and v.get():
                v.set(False)
    applicable_vars["all"].trace_add("write", _sync_applicable)

    form.columnconfigure(1, weight=1)
    form.columnconfigure(5, weight=0)

    # ── Middle: dual-list selectors for kingdoms + characters + history ───────
    main = ttk.Frame(tab_basic, padding=(10, 4, 10, 4))
    main.pack(fill=tk.BOTH, expand=True)
    main.rowconfigure(0, weight=1)
    main.rowconfigure(1, weight=2)
    main.columnconfigure(0, weight=1)
    main.columnconfigure(1, weight=1)

    # Kingdom universe — union of every event's kingdoms_involved + terminology cache
    all_kingdoms: Set[str] = set()
    for ev in (app.world_dynamic_events_items or []):
        for k in ev.get("kingdoms_involved", []) or []:
            all_kingdoms.add(str(k))
    # Augment from terminology if available
    for source in ("terminology_campaign", "terminology_primary", "terminology_fallback"):
        payload = getattr(app, source, None) or {}
        if isinstance(payload, dict):
            kdict = payload.get("kingdoms")
            if isinstance(kdict, dict):
                for k in kdict.keys():
                    all_kingdoms.add(str(k))
    for k in cur_kingdoms:
        all_kingdoms.add(k)

    def kingdom_label(kid: str) -> str:
        resolver = getattr(app, "resolve_kingdom_name", None)
        if callable(resolver):
            try:
                disp = resolver(kid)
                if disp and disp != kid:
                    return f"{disp} ({kid})"
            except Exception:
                pass
        return kid

    king_frame = labeled_frame(main, text=tr("🏛 涉及王國"))
    king_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(2, 4))
    king_state = _build_dual_list(
        king_frame,
        all_keys=sorted(all_kingdoms),
        initially_selected=cur_kingdoms,
        label_for=kingdom_label,
    )

    # Character universe = all displays in plain_to_path + main_hero virtual entry
    char_universe: List[Tuple[str, str]] = []   # (sid, display_label)
    char_meta = getattr(app, "character_meta", {}) or {}
    seen_sids: Set[str] = set()
    for display, meta in char_meta.items():
        sid = str((meta or {}).get("StringId", "")).strip()
        if not sid or sid in seen_sids:
            continue
        char_universe.append((sid, display))
        seen_sids.add(sid)
    # Add the player as a selectable character.
    if PLAYER_SID not in seen_sids:
        char_universe.append((PLAYER_SID, PLAYER_DISPLAY_LABEL()))
        seen_sids.add(PLAYER_SID)
    # Also surface any sid in cur_chars that isn't in plain_to_path (deleted hero
    # — keep editable so the user can drop it).
    for sid in cur_chars:
        if sid not in seen_sids:
            char_universe.append((sid, f"{sid} ({tr('已刪除')})"))
            seen_sids.add(sid)
    char_universe.sort(key=lambda p: p[1])

    char_frame = labeled_frame(main, text=tr("🎭 涉及角色"))
    char_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=(2, 4))

    char_state = _build_dual_list(
        char_frame,
        all_keys=[sid for sid, _ in char_universe],
        initially_selected=cur_chars,
        label_for=lambda sid: next(
            (lab for s, lab in char_universe if s == sid),
            sid,
        ),
        # Always pin the player to the top of both sides so the user can
        # find / toggle main_hero without scrolling through the whole roster.
        pin_keys=[PLAYER_SID],
    )

    # ── History entries panel (bottom, full width) ────────────────────────────
    hist_frame = labeled_frame(main, text=tr("📅 歷史記錄（最新一則 ⇒ 同步至事件描述；最早一則 ⇒ 事件建立日期）"))
    hist_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 0))

    hist_canvas = tk.Canvas(hist_frame, highlightthickness=0)
    hist_vsb = ttk.Scrollbar(hist_frame, orient="vertical", command=hist_canvas.yview)
    hist_canvas.configure(yscrollcommand=hist_vsb.set)
    hist_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    hist_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    hist_inner = ttk.Frame(hist_canvas)
    hist_window = hist_canvas.create_window((0, 0), window=hist_inner, anchor="nw")

    def _on_hist_resize(_e):
        hist_canvas.itemconfigure(hist_window, width=hist_canvas.winfo_width())
        hist_canvas.configure(scrollregion=hist_canvas.bbox("all"))
    hist_canvas.bind("<Configure>", _on_hist_resize)
    hist_inner.bind("<Configure>", lambda _e: hist_canvas.configure(
        scrollregion=hist_canvas.bbox("all")))

    # Per-entry widget state
    history_widgets: List[Dict[str, Any]] = []

    def _build_history_rows():
        # Wipe and rebuild from cur_history (sort newest-first for display only)
        for child in hist_inner.winfo_children():
            child.destroy()
        history_widgets.clear()
        if not cur_history:
            ttk.Label(
                hist_inner, foreground=tcol("#999999"),
                text=tr("（此事件無歷史紀錄）"),
                font=("Microsoft JhengHei", 10, "italic"),
            ).pack(anchor="w", padx=10, pady=10)
            return
        # Find latest / earliest by current-day for visual marking
        def hd(h):
            try:
                return float(h.get("campaign_days", float("-inf")))
            except (TypeError, ValueError, AttributeError):
                return float("-inf")
        latest_idx_in_orig = max(range(len(cur_history)), key=lambda i: hd(cur_history[i]))
        earliest_idx_in_orig = min(range(len(cur_history)), key=lambda i: hd(cur_history[i]))

        # Display newest first
        order = sorted(range(len(cur_history)), key=lambda i: hd(cur_history[i]), reverse=True)
        for display_pos, orig_idx in enumerate(order):
            entry = cur_history[orig_idx]
            row_frame = ttk.Frame(hist_inner)
            row_frame.pack(fill=tk.X, padx=8, pady=(6, 2))

            head_row = ttk.Frame(row_frame)
            head_row.pack(fill=tk.X)

            ttk.Label(head_row, text=tr("日期:"), width=6, anchor="e").pack(side=tk.LEFT)
            date_field = _DateField(head_row, initial_value=entry.get("campaign_days", 0.0))
            date_field.frame.pack(side=tk.LEFT, padx=(0, 8))

            reason = str(entry.get("update_reason", "") or "—")
            ttk.Label(head_row, text=tr("原因:") + " " + reason,
                      foreground=tcol("#666666")).pack(side=tk.LEFT, padx=(0, 6))

            tag_parts = []
            if orig_idx == latest_idx_in_orig:
                tag_parts.append(tr("🟢 最新（同步至事件描述）"))
            if orig_idx == earliest_idx_in_orig and earliest_idx_in_orig != latest_idx_in_orig:
                tag_parts.append(tr("🔵 最早（同步至建立日期）"))
            if tag_parts:
                ttk.Label(head_row, text="  ·  ".join(tag_parts),
                          foreground=tcol("#1A6FA0"),
                          font=("Microsoft JhengHei", 9, "bold")).pack(
                    side=tk.LEFT, padx=(4, 0))

            desc_widget = tk.Text(row_frame, wrap="word", height=4,
                                   font=("Microsoft JhengHei", 10))
            desc_widget.pack(fill=tk.X, padx=(46, 0), pady=(2, 4))
            desc_widget.insert("1.0", str(entry.get("description", "") or ""))

            history_widgets.append({
                "orig_idx": orig_idx,
                "date_field": date_field,
                "desc_widget": desc_widget,
            })

    _build_history_rows()

    # ── Tab 外交: participating kingdoms / engagement / embedded stmts / schedule ─
    diplo = ttk.Frame(tab_diplo, padding=(10, 6, 10, 6))
    diplo.pack(fill=tk.BOTH, expand=True)
    diplo.rowconfigure(0, weight=1)
    diplo.columnconfigure(0, weight=1)
    diplo.columnconfigure(1, weight=1)

    part_frame = labeled_frame(diplo, text=tr("🤝 參與王國（participating_kingdoms）"))
    part_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
    part_state = _build_dual_list(
        part_frame,
        all_keys=sorted(all_kingdoms),
        initially_selected=cur_participating,
        label_for=kingdom_label,
    )

    right_col = ttk.Frame(diplo)
    right_col.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
    right_col.rowconfigure(0, weight=2)
    right_col.rowconfigure(1, weight=1)
    right_col.columnconfigure(0, weight=1)

    eng_frame = labeled_frame(right_col, text=tr("📊 各王國回應率 kingdom_engagement（0–100）"))
    eng_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
    eng_state = _build_engagement_editor(
        eng_frame, initial=cur_engagement,
        all_kingdoms=sorted(all_kingdoms), kingdom_label=kingdom_label,
    )

    misc_frame = labeled_frame(right_col, text=tr("🗣 內嵌聲明・排程"))
    misc_frame.grid(row=1, column=0, sticky="nsew")
    if embedded_stmts:
        ttk.Label(misc_frame,
                  text=tr("此事件內嵌 {v0} 筆統治者聲明。").format(v0=len(embedded_stmts)),
                  foreground=tcol("#444444")).pack(anchor="w", padx=8, pady=(6, 2))

        def _open_stmts():
            show = getattr(app, "_stmt_show_event", None)
            win.destroy()
            _refresh_tab_safely(app)
            if callable(show):
                show(event_id)
        ttk.Button(misc_frame, text=tr("在聲明子分頁開啟此事件 →"),
                   command=_open_stmts, style="info.TButton").pack(
            anchor="w", padx=8, pady=(0, 8))
    else:
        ttk.Label(misc_frame, text=tr("（此事件無內嵌聲明）"),
                  foreground=tcol("#999999")).pack(anchor="w", padx=8, pady=(6, 2))

    sched_n = len(eff("next_statement_attempt_days", {}) or {}) + \
        len(eff("failed_statement_attempts", {}) or {})
    sched_lbl = ttk.Label(
        misc_frame, foreground=tcol("#888888"),
        text=tr("聲明排程：next_statement_attempt_days / failed_statement_attempts 共 {sched_n} 筆").format(sched_n=sched_n))
    sched_lbl.pack(anchor="w", padx=8, pady=(8, 2))

    def _clear_schedule():
        schedule_state["cleared"] = True
        sched_lbl.configure(text=tr("✓ 已標記清空排程（儲存後讓 AI 立即可再嘗試聲明）"),
                            foreground=tcol("#1A6FA0"))
    ttk.Button(misc_frame, text=tr("🧹 清空排程"), command=_clear_schedule,
               style="secondary.TButton").pack(anchor="w", padx=8, pady=(0, 8))

    # ── Tab 經濟效果 ───────────────────────────────────────────────────────────
    eco_root = ttk.Frame(tab_eco, padding=(10, 6, 10, 6))
    eco_root.pack(fill=tk.BOTH, expand=True)
    eco_state = _build_economic_effects_editor(eco_root, app, win, initial=cur_eco)

    # ── Footer: 完成 / 取消 (foot already bottom-docked above the notebook) ───
    err_var = tk.StringVar(value="")
    ttk.Label(foot, textvariable=err_var, foreground=tcol("#C0392B")).pack(side=tk.LEFT)

    def collect_and_save():
        # ── Collect form values into a candidate dict ─────────────────────
        new_title = title_var.get()
        new_type_disp = type_var.get().strip()
        new_type_key = type_display_to_key.get(new_type_disp, "")
        try:
            new_imp = int(importance_var.get())
        except (TypeError, ValueError, tk.TclError):
            err_var.set(tr("重要度需為 1–9 的整數"))
            return
        new_imp = max(1, min(9, new_imp))
        try:
            new_expiry = expiry_field.get()
        except (TypeError, ValueError):
            err_var.set(tr("到期日期需為數字"))
            return
        new_kingdoms = list(king_state["selected"]())
        new_chars    = list(char_state["selected"]())

        new_history: List[dict] = []
        for w in history_widgets:
            try:
                day_val = w["date_field"].get()
            except (TypeError, ValueError):
                err_var.set(tr("某筆歷史紀錄的日期無法解析"))
                return
            desc_val = w["desc_widget"].get("1.0", "end-1c")
            base = dict(cur_history[w["orig_idx"]])
            base["campaign_days"] = day_val
            base["description"]   = str(desc_val)
            new_history.append(base)
        # Sort by day ascending so the on-disk list has stable temporal order.
        new_history.sort(key=lambda h: float(h.get("campaign_days", 0.0)))

        # ── Collect the Stage-D fields ────────────────────────────────────
        new_player = bool(player_var.get())
        if applicable_vars["all"].get():
            new_applicable = ["all"]
        else:
            new_applicable = [k for k in APPLICABLE_NPC_KEYS
                              if k != "all" and applicable_vars[k].get()]
        new_participating = list(part_state["selected"]())
        new_engagement = eng_state["get"]()
        new_eco = eco_state["get"]()

        collected: Dict[str, Any] = {
            "title": new_title,
            "importance": new_imp,
            "expiration_campaign_days": new_expiry,
            "kingdoms_involved": new_kingdoms,
            "characters_involved": new_chars,
            "event_history": new_history,
            "player_involved": new_player,
            "applicable_npcs": new_applicable,
            "participating_kingdoms": new_participating,
            "kingdom_engagement": new_engagement,
            "economic_effects": new_eco,
        }
        if new_type_key:
            collected["type"] = new_type_key
        if schedule_state["cleared"]:
            collected["next_statement_attempt_days"] = {}
            collected["failed_statement_attempts"] = {}

        if is_new:
            # Rebuild the whole event from template + collected fields, write
            # it back to the staged-new slot (no field-level diff for new ones).
            app._dyn_replace_new_event(new_index, apply_event_edits(event, collected))
        else:
            # Field-level staging keeps auto-cancel-on-revert semantics.
            for field, value in collected.items():
                app._dyn_stage_edit(event_id, field, value)

        win.destroy()
        _refresh_tab_safely(app)

    ttk.Button(foot, text=tr("完成"), command=collect_and_save,
               style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(foot, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)


# ── Helpers ──────────────────────────────────────────────────────────────────
# The campaign-day / 年季日 picker now lives in ``widgets.game_date_field``
# (imported as ``_DateField`` above) so the plot / memory insert dialog reuses it.


def _refresh_tab_safely(app) -> None:
    """Refresh the dynamic events tab if mounted (no-op otherwise)."""
    try:
        from ui.dynamic_events_tab import refresh_dynamic_events_tab
        refresh_dynamic_events_tab(app)
    except Exception:
        pass


def _event_campaign_dir(app) -> Optional[Path]:
    try:
        sd = getattr(app, "save_data_dir", None)
        cid = app._current_campaign_id()
        if sd and cid:
            return Path(sd) / cid
    except Exception:
        pass
    return None


def _build_event_image_tab(app, parent, event_id: str) -> None:
    """Image tab: view / replace the event's ``event_images/<id>.png`` file.

    DynamicEvent has no image field — the game associates an image purely by the
    filename convention, so 'change' means replacing that file (old copy backed
    up beside it). Reuses the shared image picker (folder tabs + preview).
    """
    root = ttk.Frame(parent, padding=(12, 10, 12, 10))
    root.pack(fill=tk.BOTH, expand=True)
    cdir = _event_campaign_dir(app)
    target = (cdir / "event_images" / f"{event_id}.png") if cdir else None

    ttk.Label(root, text=tr("動態事件圖像（event_images/<事件id>.png）"),
              foreground=tcol("#444444")).pack(anchor="w")
    name_var = tk.StringVar()
    ttk.Label(root, textvariable=name_var, foreground=tcol("#6B5B3E")).pack(anchor="w", pady=(2, 4))
    thumb = ImageThumbnail(root, thumb_size=(360, 200))
    thumb.pack(anchor="w", pady=(0, 6))

    def _refresh():
        if target is not None and target.exists():
            thumb.load(target)
            name_var.set(target.name)
        else:
            thumb.clear()
            name_var.set(tr("（此事件目前無圖像）"))

    def _backup(p: Path) -> None:
        bak = p.parent / (p.name + ".bak_" + time.strftime("%Y%m%d_%H%M%S"))
        shutil.copy2(p, bak)

    def _remove_image():
        # Events associate an image purely by filename; 'remove association'
        # therefore moves the file aside (backed up, not deleted).
        if target is None or not target.exists():
            return
        try:
            _backup(target)
            target.unlink()
            try:
                app.log(tr("已移除事件圖像 {event_id}（原圖已備份）").format(event_id=event_id), "SUCCESS")
            except Exception:
                pass
        except Exception as ex:
            messagebox.showwarning(tr("圖像"), tr("更換失敗：{ex}").format(ex=ex), parent=parent)
            return
        _refresh()

    def _replace():
        if not cdir or target is None:
            messagebox.showinfo(tr("圖像"), tr("尚未載入戰役，無法更換圖像。"), parent=parent)
            return
        used = {}
        b = getattr(app, "diplomacy_bundle", None)
        if isinstance(b, dict):
            used["event_images"] = {str(e.get("id", "")) for e in (b.get("dynamic_events") or [])
                                    if e.get("id")}
        pick = open_image_picker(parent, campaign_dir=cdir, title=tr("選擇圖像"),
                                 used_by_folder=used, allow_remove=True)
        if pick is None:
            return
        if pick is PICKER_REMOVE:
            _remove_image()
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                _backup(target)
            shutil.copy2(pick, target)
            try:
                app.log(tr("已更換事件圖像 {event_id}").format(event_id=event_id), "SUCCESS")
            except Exception:
                pass
        except Exception as ex:
            messagebox.showwarning(tr("圖像"), tr("更換失敗：{ex}").format(ex=ex), parent=parent)
            return
        _refresh()

    btns = ttk.Frame(root)
    btns.pack(anchor="w")
    ttk.Button(btns, text=tr("更換圖像"), command=_replace, style="info.TButton").pack(side=tk.LEFT)
    ttk.Button(btns, text=tr("🚫 移除圖像"), command=_remove_image,
               style="danger.TButton").pack(side=tk.LEFT, padx=(6, 0))
    ttk.Label(root, text=tr("提示：事件以檔名關聯圖像，更換＝以所選圖片覆寫此事件的圖檔（原圖自動備份為 .bak）。"),
              foreground=tcol("#888888"), wraplength=560, justify="left").pack(anchor="w", pady=(8, 0))
    _refresh()


def _build_dual_list(
    parent,
    *,
    all_keys: List[str],
    initially_selected: List[str],
    label_for,
    pin_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a "selected (left) / available (right) + search" dual list.

    Returns a small interface dict::

        {
            "selected": () -> List[str],   # current selection
            "refresh":  () -> None,        # force redraw
        }

    The widget mutates an internal ``selected_set`` and ``available_set``
    each time the user adds / removes entries.  Listboxes show the
    formatted labels via ``label_for(key)`` while keeping the raw key for
    application logic.

    *pin_keys* (optional) — keys that should always sort to the top of
    both lists (in their given order).  Useful to surface the player
    entry above the alphabetical body.
    """
    selected_set: Set[str] = set(initially_selected)
    available_set: Set[str] = set(all_keys) - selected_set
    pin_order: Dict[str, int] = {
        k: i for i, k in enumerate(pin_keys or [])
    }

    def _sort_key(k: str):
        # Pinned entries get priority 0..N (preserved order); the rest get
        # priority "infinity" + alphabetical label.
        if k in pin_order:
            return (0, pin_order[k], "")
        return (1, 0, label_for(k).lower())

    inner = ttk.Frame(parent)
    inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    inner.rowconfigure(1, weight=1)
    inner.columnconfigure(0, weight=1)
    inner.columnconfigure(1, weight=0)
    inner.columnconfigure(2, weight=1)

    # Search row spanning both lists
    search_row = ttk.Frame(inner)
    search_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
    ttk.Label(search_row, text="🔍").pack(side=tk.LEFT)
    search_var = tk.StringVar(value="")
    ttk.Entry(search_row, textvariable=search_var).pack(
        side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

    sel_frame = ttk.LabelFrame(inner, text=tr("已選"))
    sel_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 2))
    avail_frame = ttk.LabelFrame(inner, text=tr("可選"))
    avail_frame.grid(row=1, column=2, sticky="nsew", padx=(2, 0))

    # Selected list
    sel_lb = tk.Listbox(sel_frame, selectmode=tk.EXTENDED, exportselection=False)
    sel_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sel_vsb = ttk.Scrollbar(sel_frame, orient="vertical", command=sel_lb.yview)
    sel_lb.configure(yscrollcommand=sel_vsb.set)
    sel_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    sel_keys: List[str] = []

    # Buttons in the middle
    btn_col = ttk.Frame(inner)
    btn_col.grid(row=1, column=1, sticky="ns", padx=2)
    btn_col.rowconfigure(0, weight=1)
    btn_col.rowconfigure(7, weight=1)

    # Available list
    avail_lb = tk.Listbox(avail_frame, selectmode=tk.EXTENDED, exportselection=False)
    avail_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    avail_vsb = ttk.Scrollbar(avail_frame, orient="vertical", command=avail_lb.yview)
    avail_lb.configure(yscrollcommand=avail_vsb.set)
    avail_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    avail_keys: List[str] = []

    def refresh():
        term = (search_var.get() or "").strip().lower()
        sel_lb.delete(0, tk.END)
        sel_keys.clear()
        for k in sorted(selected_set, key=_sort_key):
            label = label_for(k)
            if term and term not in label.lower() and term not in k.lower():
                continue
            sel_lb.insert(tk.END, label)
            sel_keys.append(k)
        avail_lb.delete(0, tk.END)
        avail_keys.clear()
        for k in sorted(available_set, key=_sort_key):
            label = label_for(k)
            if term and term not in label.lower() and term not in k.lower():
                continue
            avail_lb.insert(tk.END, label)
            avail_keys.append(k)

    def selected_picks() -> List[str]:
        return [sel_keys[i] for i in sel_lb.curselection() if i < len(sel_keys)]

    def available_picks() -> List[str]:
        return [avail_keys[i] for i in avail_lb.curselection() if i < len(avail_keys)]

    def add_picks():
        for k in available_picks():
            available_set.discard(k)
            selected_set.add(k)
        refresh()

    def remove_picks():
        for k in selected_picks():
            selected_set.discard(k)
            available_set.add(k)
        refresh()

    def add_all_visible():
        for k in list(avail_keys):
            available_set.discard(k)
            selected_set.add(k)
        refresh()

    def remove_all_visible():
        for k in list(sel_keys):
            selected_set.discard(k)
            available_set.add(k)
        refresh()

    ttk.Button(btn_col, text="◀", width=4, command=add_picks).grid(
        row=1, column=0, padx=2, pady=2, sticky="ew")
    ttk.Button(btn_col, text="▶", width=4, command=remove_picks).grid(
        row=2, column=0, padx=2, pady=2, sticky="ew")
    ttk.Separator(btn_col, orient="horizontal").grid(
        row=3, column=0, padx=2, pady=4, sticky="ew")
    ttk.Button(btn_col, text="◀◀", width=4, command=add_all_visible).grid(
        row=4, column=0, padx=2, pady=2, sticky="ew")
    ttk.Button(btn_col, text="▶▶", width=4, command=remove_all_visible).grid(
        row=5, column=0, padx=2, pady=2, sticky="ew")

    # Double-click to swap a single entry for fast clicking
    avail_lb.bind("<Double-Button-1>", lambda e: add_picks())
    sel_lb.bind("<Double-Button-1>", lambda e: remove_picks())

    search_var.trace_add("write", lambda *_: refresh())

    refresh()
    return {
        "selected": lambda: sorted(selected_set, key=_sort_key),
        "refresh": refresh,
    }


# ── Stage D helpers ────────────────────────────────────────────────────────────

# Common Bannerlord trade-good category ids (editable combobox; freeform allowed).
# Official ItemCategory string ids (v0.38.0, verified against the game's
# decompiled DefaultItemCategories.RegisterAll for v1.4.6).  The previous list
# carried five ids that DO NOT exist in the game (cattle / raw_silk /
# cotton_cloth / iron_ore / cotton_yarn / wool_cloth / leather_armor) — writing
# those into an event's price modifiers silently does nothing in-game.
# Trade goods first, then the priceable equipment categories.
_MARKET_CATEGORIES = (
    "grain", "fish", "meat", "cheese", "oil", "butter", "wine", "beer",
    "wool", "cotton", "flax", "linen", "velvet", "leather", "fur", "hides",
    "clay", "salt", "hardwood", "iron", "silver", "tools", "pottery",
    "jewelry", "felt", "planks", "horse", "war_horse", "noble_horse",
    "sumpter_horse", "sheep", "cow", "hog", "date_fruit", "grape", "olives",
    "cloth", "garment", "melee_weapons", "ranged_weapons", "shield",
    "horse_equipment", "light_armor", "medium_armor", "heavy_armor",
    "ultra_armor", "arrows", "banner",
)

def _cat_localized(cid: str):
    """Official localized name for a market-category id, or ``None`` if unknown.

    These market categories carry NO name in the companion-mod database export
    (they are ItemCategory/trade-good ids, not items), so their localized names
    come from the tool's own i18n. The zh-Hant keys are the official TaleWorlds
    translations pulled from the language pack (SandBoxCore std_spitems + Native
    std_common_strings / std_module_strings); the 4 pure ItemCategories with no
    standalone game string (horse / noble_horse / ranged_weapons /
    horse_equipment) use the conventional TW terms. NOTE the game quirk: the
    item with id "cotton" is officially named "Raw Silk" → 生絲.

    Built as literal tr() calls (not a data dict + tr(var)) so the i18n coverage
    checker sees every key and the display-audit stays clean.
    """
    return {
        "grain": tr("穀物"), "fish": tr("魚"), "meat": tr("肉"), "cheese": tr("乳酪"),
        "oil": tr("油"), "butter": tr("奶油"), "wine": tr("葡萄酒"), "beer": tr("啤酒"),
        "wool": tr("羊毛"), "cotton": tr("生絲"), "flax": tr("亞麻"), "linen": tr("亞麻布"),
        "velvet": tr("天鵝絨"), "leather": tr("皮革"), "fur": tr("毛皮"), "hides": tr("獸皮"),
        "clay": tr("黏土"), "salt": tr("鹽"), "hardwood": tr("硬木"), "iron": tr("鐵"),
        "silver": tr("銀礦石"), "tools": tr("工具"), "pottery": tr("陶器"),
        "jewelry": tr("珠寶"), "felt": tr("毛氈"), "planks": tr("木材"),
        "horse": tr("馬"), "war_horse": tr("戰馬"), "noble_horse": tr("貴族馬"),
        "sumpter_horse": tr("馱馬"), "sheep": tr("綿羊"), "cow": tr("牛"),
        "hog": tr("肉豬"), "date_fruit": tr("椰棗"), "grape": tr("葡萄"),
        "olives": tr("橄欖"), "cloth": tr("布匹"), "garment": tr("服裝"),
        "melee_weapons": tr("近戰武器"), "ranged_weapons": tr("遠程武器"),
        "shield": tr("盾牌"), "horse_equipment": tr("馬具"),
        "light_armor": tr("輕甲"), "medium_armor": tr("中甲"),
        "heavy_armor": tr("重型護甲"), "ultra_armor": tr("終極護甲"),
        "arrows": tr("箭矢"), "banner": tr("旗幟"),
    }.get(cid)


def _cat_display(cid: str, resolver=None) -> str:
    """「名稱（id）」 display for a category id.

    *resolver*: optional callable(id) → localized name (companion-mod
    terminology, when the id happens to be a real item).  Falls back to the
    official localized category name, then the raw id — so custom/legacy ids
    (e.g. the old bogus "cattle") still round-trip.
    """
    cid = str(cid or "")
    lab = None
    if resolver is not None:
        try:
            lab = resolver(cid)
        except Exception:
            lab = None
    lab = lab or _cat_localized(cid)
    return f"{lab}（{cid}）" if lab else cid


def _cat_id_from_display(text: str) -> str:
    """Extract the raw category id from a 「中文（id）」 display string."""
    text = str(text or "").strip()
    if text.endswith("）") and "（" in text:
        return text[text.rfind("（") + 1:-1].strip()
    return text


def _eco_type_options():
    """[(display, value)] for the economic-effect target type (translatable)."""
    return [(tr("王國"), "kingdom"), (tr("定居點"), "settlement")]


def _eco_scope_options():
    """[(display, value)] for the economic-effect target scope (translatable)."""
    return [(tr("（不限）"), ""), (tr("城鎮"), "towns"), (tr("村莊"), "villages"),
            (tr("城堡"), "castles"), (tr("全部"), "all")]


def _eco_type_label(v) -> str:
    return {vv: dd for dd, vv in _eco_type_options()}.get(str(v or ""), str(v or ""))


def _eco_scope_label(v) -> str:
    return {vv: dd for dd, vv in _eco_scope_options()}.get(str(v or ""), str(v or ""))


def _build_engagement_editor(parent, *, initial: Dict[str, int],
                             all_kingdoms: List[str], kingdom_label) -> Dict[str, Any]:
    """Per-kingdom engagement-rate editor (0–100). Returns ``{"get": ()->dict}``."""
    state: Dict[str, int] = {}
    for k, v in (initial or {}).items():
        try:
            state[str(k)] = max(0, min(100, int(v)))
        except (TypeError, ValueError):
            continue
    row_vars: Dict[str, tk.StringVar] = {}
    avail_holder: Dict[str, List[str]] = {"list": []}

    container = ttk.Frame(parent)
    container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))
    canvas = tk.Canvas(container, highlightthickness=0)
    vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    rows_holder = ttk.Frame(canvas)
    win_id = canvas.create_window((0, 0), window=rows_holder, anchor="nw")
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=canvas.winfo_width()))
    rows_holder.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    add_row = ttk.Frame(parent)
    add_row.pack(fill=tk.X, padx=4, pady=(2, 4))
    add_var = tk.StringVar()
    add_cb = ttk.Combobox(add_row, textvariable=add_var, state="readonly", width=22)
    add_cb.pack(side=tk.LEFT)

    def _sync_state_from_vars():
        for kid, var in row_vars.items():
            try:
                state[kid] = max(0, min(100, int(var.get())))
            except (TypeError, ValueError):
                pass

    def _refresh_add_options():
        avail = [k for k in all_kingdoms if k not in state]
        avail_holder["list"] = avail
        add_cb.configure(values=[kingdom_label(k) for k in avail])
        add_var.set("")

    def _rebuild():
        _sync_state_from_vars()
        for c in rows_holder.winfo_children():
            c.destroy()
        row_vars.clear()
        if not state:
            ttk.Label(rows_holder, foreground=tcol("#999999"),
                      text=tr("（尚未設定任何王國回應率）")).pack(anchor="w", padx=6, pady=6)
        for kid in sorted(state, key=lambda k: kingdom_label(k).lower()):
            r = ttk.Frame(rows_holder)
            r.pack(fill=tk.X, pady=1)
            ttk.Label(r, text=kingdom_label(kid), width=24, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(state[kid]))
            row_vars[kid] = var
            ttk.Spinbox(r, from_=0, to=100, width=5, textvariable=var).pack(side=tk.LEFT, padx=4)
            ttk.Button(r, text="🗑", width=3,
                       command=lambda k=kid: _remove(k)).pack(side=tk.LEFT)
        _refresh_add_options()

    def _remove(kid):
        _sync_state_from_vars()
        state.pop(kid, None)
        _rebuild()

    def _add():
        i = add_cb.current()
        avail = avail_holder["list"]
        if 0 <= i < len(avail):
            _sync_state_from_vars()
            state.setdefault(avail[i], 50)
            _rebuild()
    ttk.Button(add_row, text=tr("＋加入王國"), command=_add,
               style="secondary.TButton").pack(side=tk.LEFT, padx=6)

    _rebuild()

    def get() -> Dict[str, int]:
        _sync_state_from_vars()
        return dict(state)
    return {"get": get}


def _build_economic_effects_editor(parent, app, win, initial: List[dict]) -> Dict[str, Any]:
    """List + add/edit/remove of event-embedded economic effects.

    Returns ``{"get": ()->list}``. Editing opens a second-level dialog."""
    effects: List[dict] = [normalize_economic_effect(e) for e in (initial or []) if isinstance(e, dict)]

    ttk.Label(parent, text=tr("事件內嵌經濟效果（economic_effects；每筆一個目標＋商品物價修正）"),
              foreground=tcol("#444444")).pack(anchor="w", pady=(0, 4))

    body = ttk.Frame(parent)
    body.pack(fill=tk.BOTH, expand=True)
    lb = tk.Listbox(body, font=("Microsoft JhengHei", 10))
    vsb = ttk.Scrollbar(body, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _summary(e: dict) -> str:
        tt = _eco_type_label(e.get("target_type", "?"))
        ti = e.get("target_id", "?")
        scope = e.get("target_scope")
        rs = str(e.get("reason", "") or "").replace("\n", " ")[:34]
        npm = len(e.get("market_price_modifiers", []) or [])
        scope_s = f"/{_eco_scope_label(scope)}" if scope else ""
        return f"[{tt}:{ti}{scope_s}]  {rs}   ({tr('物價')} {npm})"

    def _refresh():
        lb.delete(0, tk.END)
        for e in effects:
            lb.insert(tk.END, _summary(e))

    def _sel():
        s = lb.curselection()
        return s[0] if s else None

    def _add():
        _open_eco_effect_dialog(app, win, None,
                                lambda e: (effects.append(e), _refresh()))

    def _edit():
        i = _sel()
        if i is None:
            return
        def _save(e, idx=i):
            effects[idx] = e
            _refresh()
        _open_eco_effect_dialog(app, win, effects[i], _save)

    def _del():
        i = _sel()
        if i is None:
            return
        effects.pop(i)
        _refresh()

    # Prominent banner: economic-effect add/edit may not take effect (the game
    # instantiates effects to economic_effects.json at runtime; editing the
    # event-embedded copy won't necessarily apply).  f-string → not i18n-scanned.
    warn = paint(
        tk.Label(
            parent,
            text=tr("⚠ 受技術限制：經濟效果的「新增／編輯」可能無法如期生效——遊戲會在運行時把效果實例化到 economic_effects.json，工具改動事件內嵌的效果未必會套用。最可靠的用途仍是修正既有事件的文字。"),
            font=("Microsoft JhengHei", 9, "bold"),
            wraplength=620, justify="left", padx=8, pady=4),
        bg=tcol("#E67E22"), fg=tcol("#FFFFFF"))
    warn.pack(fill=tk.X, pady=(6, 2))

    btns = ttk.Frame(parent)
    btns.pack(fill=tk.X, pady=(2, 0))
    ttk.Button(btns, text=tr("➕ 新增效果"), command=_add,
               style="success.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(btns, text=tr("✏ 編輯"), command=_edit,
               style="info.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(btns, text=tr("🗑 刪除"), command=_del,
               style="danger.TButton").pack(side=tk.LEFT, padx=2)
    lb.bind("<Double-Button-1>", lambda e: _edit())

    _refresh()
    return {"get": lambda: [normalize_economic_effect(e) for e in effects]}


def _open_eco_effect_dialog(app, parent_win, effect: Optional[dict], on_save) -> None:
    """Second-level editor for one economic_effect.  Calls *on_save(effect_dict)*."""
    e = dict(effect or {})
    win = tk.Toplevel(parent_win)
    win.title(tr("編輯經濟效果") if effect else tr("新增經濟效果"))
    win.geometry("620x640")
    try:
        app._center_window(win, 620, 640)
    except Exception:
        pass
    win.transient(parent_win)
    win.grab_set()

    # Bottom-dock the footer first so 確定/取消 stay visible (see note in the
    # main editor: Tk pack clips the last-packed widget when space is short).
    foot = ttk.Frame(win, padding=(10, 4, 10, 8))
    foot.pack(side=tk.BOTTOM, fill=tk.X)
    ttk.Separator(win, orient="horizontal").pack(side=tk.BOTTOM, fill=tk.X)

    body = ttk.Frame(win, padding=10)
    body.pack(fill=tk.BOTH, expand=True)

    # Target
    tgt = ttk.LabelFrame(body, text=tr("目標"))
    tgt.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(tgt, text=tr("類型")).grid(row=0, column=0, sticky="e", padx=4, pady=3)
    _type_opts = _eco_type_options()
    _type_disp_to_val = {d: v for d, v in _type_opts}
    _type_val_to_disp = {v: d for d, v in _type_opts}
    type_var = tk.StringVar(
        value=_type_val_to_disp.get(str(e.get("target_type", "kingdom")), _type_opts[0][0]))

    def _cur_type():
        return _type_disp_to_val.get(type_var.get(), "kingdom")

    ttk.Combobox(tgt, textvariable=type_var, width=12, state="readonly",
                 values=[d for d, _ in _type_opts]).grid(row=0, column=1, sticky="w", padx=4)
    ttk.Label(tgt, text=tr("目標 id")).grid(row=0, column=2, sticky="e", padx=4)
    _init_cat = "settlements" if _cur_type() == "settlement" else "kingdoms"
    id_combo = NameIdCombo(tgt, app, _init_cat,
                           initial_id=str(e.get("target_id", "") or ""), width=16,
                           autocomplete=True)
    id_combo.grid(row=0, column=3, sticky="w", padx=4)

    def _on_target_type_change(*_):
        id_combo.set_category("settlements" if _cur_type() == "settlement" else "kingdoms")
    type_var.trace_add("write", _on_target_type_change)
    ttk.Label(tgt, text=tr("範圍")).grid(row=0, column=4, sticky="e", padx=4)
    _scope_opts = _eco_scope_options()
    _scope_disp_to_val = {d: v for d, v in _scope_opts}
    _scope_val_to_disp = {v: d for d, v in _scope_opts}
    scope_var = tk.StringVar(
        value=_scope_val_to_disp.get(str(e.get("target_scope", "") or ""), _scope_opts[0][0]))
    ttk.Combobox(tgt, textvariable=scope_var, width=12, state="readonly",
                 values=[d for d, _ in _scope_opts]).grid(
        row=0, column=5, sticky="w", padx=4)

    # Numeric deltas (2-column grid)
    nums = ttk.LabelFrame(body, text=tr("數值（每日 / 一次性）"))
    nums.pack(fill=tk.X, pady=(0, 6))
    num_specs = [
        ("prosperity_delta_per_day", tr("繁榮/日")),
        ("prosperity_delta",         tr("繁榮(一次)")),
        ("food_delta_per_day",       tr("食物/日")),
        ("food_delta",               tr("食物(一次)")),
        ("security_delta_per_day",   tr("治安/日")),
        ("security_delta",           tr("治安(一次)")),
        ("loyalty_delta_per_day",    tr("忠誠/日")),
        ("loyalty_delta",            tr("忠誠(一次)")),
        ("income_multiplier",        tr("收入倍率")),
        ("duration_days",            tr("持續天數")),
    ]
    num_vars: Dict[str, tk.StringVar] = {}
    for i, (key, label) in enumerate(num_specs):
        r, c = divmod(i, 2)
        ttk.Label(nums, text=label, width=12, anchor="e").grid(
            row=r, column=c * 2, sticky="e", padx=4, pady=2)
        default = e.get(key, 0)
        if key == "income_multiplier" and key not in e:
            default = 1.0
        v = tk.StringVar(value=str(default))
        num_vars[key] = v
        ttk.Entry(nums, textvariable=v, width=12).grid(
            row=r, column=c * 2 + 1, sticky="w", padx=4, pady=2)

    # Reason
    ttk.Label(body, text=tr("原因 reason")).pack(anchor="w")
    reason_txt = tk.Text(body, height=3, wrap="word", font=("Microsoft JhengHei", 10))
    reason_txt.pack(fill=tk.X, pady=(0, 6))
    reason_txt.insert("1.0", str(e.get("reason", "") or ""))

    # Market price modifiers
    mpm_frame = ttk.LabelFrame(body, text=tr("商品物價修正 market_price_modifiers（%）"))
    mpm_frame.pack(fill=tk.BOTH, expand=True)
    mpm_rows: List[Dict[str, tk.StringVar]] = []
    mpm_holder = ttk.Frame(mpm_frame)
    mpm_holder.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # Localized category names via companion-mod terminology when present;
    # otherwise the English base labels (user architecture: EN+id fallback).
    # Route through app.resolve_item_name so the *campaign* terminology cache is
    # consulted — the primary/fallback library layers have been empty since the
    # ProemConfig removal (v0.29), so querying them directly always missed.
    def _cat_resolver(cid: str):
        fn = getattr(app, "resolve_item_name", None)
        if callable(fn):
            try:
                name = fn(cid)
                if name and name != cid:
                    return name
            except Exception:
                pass
        return None  # → _cat_display falls back to the localized _CAT_ZH name + id

    def _add_mpm(category: str = "", percent: Any = 0.0):
        r = ttk.Frame(mpm_holder)
        r.pack(fill=tk.X, pady=1)
        cat_var = tk.StringVar(value=_cat_display(category, _cat_resolver) if category else "")
        pct_var = tk.StringVar(value=str(percent if percent is not None else 0.0))
        ttk.Combobox(r, textvariable=cat_var, width=22,
                     values=[_cat_display(c, _cat_resolver) for c in _MARKET_CATEGORIES]).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(r, text=tr("變動%")).pack(side=tk.LEFT)
        ttk.Entry(r, textvariable=pct_var, width=8).pack(side=tk.LEFT, padx=4)
        row_rec = {"category_id": cat_var, "price_change_percent": pct_var, "frame": r}
        mpm_rows.append(row_rec)
        ttk.Button(r, text="🗑", width=3,
                   command=lambda: (_remove_mpm(row_rec))).pack(side=tk.LEFT)

    def _remove_mpm(rec):
        try:
            mpm_rows.remove(rec)
        except ValueError:
            pass
        rec["frame"].destroy()

    for m in (e.get("market_price_modifiers", []) or []):
        if isinstance(m, dict):
            _add_mpm(m.get("category_id", ""), m.get("price_change_percent", 0.0))
    ttk.Button(mpm_frame, text=tr("＋加入物價修正"),
               command=lambda: _add_mpm(), style="secondary.TButton").pack(
        anchor="w", padx=4, pady=(0, 4))

    err_var = tk.StringVar(value="")
    ttk.Label(body, textvariable=err_var, foreground=tcol("#C0392B")).pack(anchor="w")

    def _save():
        out = dict(e)  # preserve unknown keys
        out["target_type"] = _cur_type()
        out["target_id"] = id_combo.get_id().strip()
        scope = _scope_disp_to_val.get(scope_var.get(), "")
        if scope:
            out["target_scope"] = scope
        else:
            out.pop("target_scope", None)
        for key, var in num_vars.items():
            raw = var.get().strip()
            try:
                out[key] = float(raw) if raw else 0.0
            except ValueError:
                err_var.set(tr("「{key}」需為數字").format(key=key))
                return
        out["reason"] = reason_txt.get("1.0", "end-1c")
        mpm_out: List[dict] = []
        for rec in mpm_rows:
            cat = _cat_id_from_display(rec["category_id"].get())
            if not cat:
                continue
            try:
                pct = float(rec["price_change_percent"].get().strip() or 0.0)
            except ValueError:
                err_var.set(tr("物價修正的百分比需為數字"))
                return
            mpm_out.append({"category_id": cat, "price_change_percent": pct})
        out["market_price_modifiers"] = mpm_out
        on_save(normalize_economic_effect(out))
        win.destroy()

    ttk.Button(foot, text=tr("確定"), command=_save,
               style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(foot, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
