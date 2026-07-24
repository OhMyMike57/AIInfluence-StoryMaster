"""Top-level Dynamic Events browse + edit tab (Phase 5 Stage F).

Layout
------
  Top:    filter bar (type, kingdoms, importance, player, keyword)
          + edit-mode header (☐ 編輯模式  🔍 有效檢查  N 暫存  💾 儲存  ↩ 取消)
  Middle: left = filtered event list (Listbox)
          right = event detail panel (tk.Text, read-only) OR editor panel

Stage F brings:
* i18n type/kingdom/character labels via app.resolve_*_name()
* Sort newest-first by creation_campaign_days
* Edit mode with field editors (title, description, importance, kingdoms,
  characters); save/cancel via staging buffer (app.dyn_events_pending)
* Delete event with cascade: removes from dynamic_events.json AND from
  every NPC JSON that references it
* Validity check: orphan-scan NPC DynamicEvents fields against the live
  event list

Builder::

    build_dynamic_events_tab(app, notebook)

Data expected on *app*:
    app.world_dynamic_events_items   List[dict]
    app.economic_effects             List[dict]
    app.plain_to_path                Dict[str, Path]   (used by validity check)
    app.character_meta               Dict[str, dict]   (sid → meta lookup)
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from i18n import tr
from services.time_format import format_game_time
from services import display_labels
from widgets.image_view import ImageThumbnail
from services.dynamic_event_service import (
    KNOWN_TYPE_KEYS,
    normalize_type,
    sort_events_by_creation,
    filter_events as svc_filter_events,
    new_event_template as svc_new_event_template,
    EDITABLE_EVENT_FIELDS,
)
from ui import preview_font
from ui.theme import paint, labeled_frame, tcol


# ── Type display labels (i18n; covers the 10 known categories) ────────
def _type_label_map() -> Dict[str, str]:
    """Dynamic-event type → localized label (shared map for terminology alignment)."""
    return display_labels.dynamic_event_type_labels()


# Raw light-mode palette (module level → kept unwrapped; adapt at use via
# ``_type_colors()`` so dark mode maps through ui.theme.c()).
_TYPE_COLORS: Dict[str, str] = {
    "military":         "#C0392B",
    "political":        "#2471A3",
    "economic":         "#884EA0",
    "social":           "#1A9A6C",
    "mysterious":       "#7B3F98",
    "news":             "#1A5276",
    "local":            "#7D6608",
    "rumor":            "#909090",
    "diseaseoutbreak":  "#A04000",
    "other":            "#5D6D7E",
}


def _type_colors() -> Dict[str, str]:
    """Event-type colours adapted to the active theme (light returns as-is)."""
    return {k: tcol(v) for k, v in _TYPE_COLORS.items()}

def _all_label() -> str:
    """全部/All filter sentinel, resolved at call time.

    A module-level ``tr("全部")`` would capture the startup-default language
    (zh_TW) before ``set_lang`` runs, leaving the dropdown Chinese in English
    mode.  Callers store this label in their StringVar and map it back to the
    canonical empty-string key via their ``*_display_to_key`` maps.
    """
    return tr("全部")


# ── Importance stars display (1-9 scale in data) ──────────────────────
def _importance_label(n) -> str:
    try:
        return f"★{int(n)}"
    except (TypeError, ValueError):
        return str(n)


# ── Delta display helper ──────────────────────────────────────────────
def _delta(val: float, unit: str = "") -> str:
    try:
        fv = float(val)
    except (TypeError, ValueError):
        return ""
    if unit == "%":
        pct = (fv - 1.0) * 100.0
        if abs(pct) < 1e-9:
            return ""
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.0f}%"
    if abs(fv) < 1e-9:
        return ""
    sign = "+" if fv > 0 else ""
    return f"{sign}{fv:.2f}{unit}"


def _format_creation_day(event: dict) -> str:
    """Render `(1085年夏3日)`-style label for the event's creation day."""
    days = event.get("creation_campaign_days")
    try:
        return f"({format_game_time(float(days))})"
    except (TypeError, ValueError):
        return ""


# ── Public builder ────────────────────────────────────────────────────

def build_dynamic_events_tab(app, notebook: ttk.Notebook) -> None:
    """Build and register the 🎭 動態事件 tab onto *notebook*."""
    tab = ttk.Frame(notebook)
    notebook.add(tab, text=tr("🎭 動態事件"))
    app._dyn_tab = tab

    # ── Action / staging header (NOW AT TOP) ──────────────────────────
    abar = ttk.Frame(tab)
    abar.pack(fill=tk.X, padx=8, pady=(8, 4))

    # LEFT: edit mode + reload + validity check
    # Bound to the app-wide shared edit-mode variable: toggling here (or in any
    # other tab) flips edit mode everywhere. Our checkbox command runs the
    # pending-changes guard; external flips sync the panel via the trace below.
    app._dyn_edit_var = getattr(app, "edit_mode_var", None) or tk.BooleanVar(value=False)
    app._dyn_edit_cb = ttk.Checkbutton(
        abar, text=tr("編輯模式"),
        variable=app._dyn_edit_var,
        command=lambda: _toggle_edit_mode(app),
    )
    app._dyn_edit_cb.pack(side=tk.LEFT, padx=(0, 8))
    app._dyn_edit_var.trace_add("write", lambda *_: _apply_edit_ui(app))

    ttk.Button(
        abar, text=tr("🔄 重新載入"),
        command=lambda: _reload_dyn_tab(app),
        style="info.TButton",
    ).pack(side=tk.LEFT, padx=(0, 4))

    ttk.Button(
        abar, text=tr("🔍 有效檢查"),
        command=lambda: app._dyn_validity_check(),
        style="info.TButton",
    ).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(
        abar, text=tr("📖 使用說明"),
        command=lambda: _open_dyn_help(app),
        style="info.TButton",
    ).pack(side=tk.LEFT, padx=(0, 4))

    # ── Inner sub-notebook (Phase 6 Stage B) ──────────────────────────
    # The diplomacy bundle holds three kinds of content; the shared toolbar
    # above (edit mode / reload / validity / staging) applies to all of them.
    inner_nb = ttk.Notebook(tab)
    inner_nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
    app._dyn_inner_nb = inner_nb

    sub_events = ttk.Frame(inner_nb)
    inner_nb.add(sub_events, text=tr("📜 事件"))
    app._dyn_sub_events = sub_events

    from ui.statements_subtab import build_statements_subtab, build_diplo_status_subtab
    sub_statements = ttk.Frame(inner_nb)
    inner_nb.add(sub_statements, text=tr("🗣 統治者聲明"))
    build_statements_subtab(app, sub_statements)

    sub_diplo = ttk.Frame(inner_nb)
    inner_nb.add(sub_diplo, text=tr("⚖ 外交狀態"))
    build_diplo_status_subtab(app, sub_diplo)

    # ── Filter bar (events sub-tab) ───────────────────────────────────
    fbar = ttk.LabelFrame(sub_events, text=tr("篩選"), padding=(6, 4))
    fbar.pack(fill=tk.X, padx=4, pady=(4, 4))

    # Type — show translated labels, store the lowercase key
    ttk.Label(fbar, text=tr("類型:")).grid(row=0, column=0, padx=(0, 2), sticky="w")
    app._dyn_filter_type = tk.StringVar(value=_all_label())
    type_label_map = _type_label_map()
    type_display_to_key: Dict[str, str] = {_all_label(): ""}
    for k in KNOWN_TYPE_KEYS:
        type_display_to_key[type_label_map[k]] = k
    app._dyn_type_display_to_key = type_display_to_key
    type_opts = [_all_label()] + [type_label_map[k] for k in KNOWN_TYPE_KEYS]
    type_cb = ttk.Combobox(fbar, textvariable=app._dyn_filter_type,
                           values=type_opts, state="readonly", width=12)
    type_cb.grid(row=0, column=1, padx=(0, 10), sticky="w")

    # Importance
    ttk.Label(fbar, text=tr("重要度:")).grid(row=0, column=2, padx=(0, 2), sticky="w")
    app._dyn_filter_importance = tk.StringVar(value=_all_label())
    imp_opts = [_all_label()] + [str(i) for i in range(1, 10)]
    imp_cb = ttk.Combobox(fbar, textvariable=app._dyn_filter_importance,
                          values=imp_opts, state="readonly", width=6)
    imp_cb.grid(row=0, column=3, padx=(0, 10), sticky="w")

    # Kingdoms
    ttk.Label(fbar, text=tr("王國:")).grid(row=0, column=4, padx=(0, 2), sticky="w")
    app._dyn_filter_kingdom = tk.StringVar(value=_all_label())
    app._dyn_kingdom_cb = ttk.Combobox(fbar, textvariable=app._dyn_filter_kingdom,
                                       values=[_all_label()], state="readonly", width=14)
    app._dyn_kingdom_cb.grid(row=0, column=5, padx=(0, 10), sticky="w")
    app._dyn_kingdom_display_to_key: Dict[str, str] = {_all_label(): ""}

    # Player involved
    app._dyn_filter_player = tk.BooleanVar(value=False)
    ttk.Checkbutton(fbar, text=tr("僅涉及玩家"),
                    variable=app._dyn_filter_player).grid(row=0, column=6, padx=(0, 10))

    # Keyword — moved to row 2 first slot (event titles are long; searching by
    # keyword is the primary way to find one).
    ttk.Label(fbar, text=tr("關鍵字:")).grid(row=1, column=0, padx=(0, 2), sticky="w", pady=(4, 0))
    app._dyn_filter_kw = tk.StringVar()
    kw_entry = ttk.Entry(fbar, textvariable=app._dyn_filter_kw, width=18)
    kw_entry.grid(row=1, column=1, padx=(0, 10), sticky="w", pady=(4, 0))

    # Sort direction (after keyword)
    ttk.Label(fbar, text=tr("排序:")).grid(row=1, column=2, padx=(0, 2), sticky="w", pady=(4, 0))
    app._DYN_SORT_NEW_FIRST = tr("新→舊")
    app._DYN_SORT_OLD_FIRST = tr("舊→新")
    app._dyn_filter_sort = tk.StringVar(value=app._DYN_SORT_NEW_FIRST)
    sort_cb = ttk.Combobox(
        fbar, textvariable=app._dyn_filter_sort,
        values=[app._DYN_SORT_NEW_FIRST, app._DYN_SORT_OLD_FIRST],
        state="readonly", width=8,
    )
    sort_cb.grid(row=1, column=3, padx=(0, 10), sticky="w", pady=(4, 0))

    # Clear filters — directly after 排序, not floating off to the right.
    ttk.Button(fbar, text=tr("清除篩選"),
               command=lambda: _clear_filters(app),
               style="secondary.TButton").grid(row=1, column=4, padx=(0, 0), pady=(4, 0))

    # Bind all filter changes
    for var in (app._dyn_filter_type, app._dyn_filter_importance,
                app._dyn_filter_kingdom, app._dyn_filter_player,
                app._dyn_filter_kw, app._dyn_filter_sort):
        var.trace_add("write", lambda *_: _apply_and_refresh_list(app))

    # RIGHT: staging widgets — only visible when pending > 0
    app._dyn_pending_var = tk.StringVar(value="")
    app._dyn_pending_lbl = paint(
        tk.Label(abar, textvariable=app._dyn_pending_var,
                 font=("", 9, "bold"), padx=6, pady=1),
        foreground=tcol("#FFFFFF"), background=tcol("#E67E22"))
    app._dyn_save_btn = ttk.Button(
        abar, text=tr("💾 儲存"),
        command=lambda: app._dyn_commit(),
        style="success.TButton",
    )
    app._dyn_cancel_btn = ttk.Button(
        abar, text=tr("↩ 取消"),
        command=lambda: app._dyn_discard(),
        style="secondary.TButton",
    )
    app._dyn_save_btn_pack_kwargs   = dict(side=tk.RIGHT, padx=(0, 4))
    app._dyn_cancel_btn_pack_kwargs = dict(side=tk.RIGHT, padx=(0, 4))
    app._dyn_pending_lbl_pack_kwargs = dict(side=tk.RIGHT, padx=(0, 4))

    # ── Main area: list (left) + detail (right) ───────────────────────
    main = ttk.Frame(sub_events)
    main.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
    # 40% / 60% split — two-line rows make the list legible at 40%; uniform
    # makes the ratio exact.
    main.columnconfigure(0, weight=4, uniform="evcol")
    main.columnconfigure(1, weight=6, uniform="evcol")
    main.rowconfigure(0, weight=1)

    # LEFT — event list
    list_frame = labeled_frame(main, text=tr("事件清單"))
    list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

    list_inner = ttk.Frame(list_frame)
    list_inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    list_inner.rowconfigure(0, weight=1)
    list_inner.columnconfigure(0, weight=1)

    app._dyn_lb = tk.Listbox(
        list_inner, exportselection=False, activestyle="dotbox",
        font=("Microsoft JhengHei", 10),
    )
    list_vsb = ttk.Scrollbar(list_inner, orient="vertical", command=app._dyn_lb.yview)
    app._dyn_lb.configure(yscrollcommand=list_vsb.set)
    app._dyn_lb.grid(row=0, column=0, sticky="nsew")
    list_vsb.grid(row=0, column=1, sticky="ns")

    # Count label below list
    app._dyn_count_var = tk.StringVar(value="")
    ttk.Label(list_frame, textvariable=app._dyn_count_var,
              foreground=tcol("#6B5B3E")).pack(side=tk.BOTTOM, anchor="w", padx=4, pady=(0, 2))

    app._dyn_lb.bind("<<ListboxSelect>>", lambda e: _on_event_select(app))

    # RIGHT — event detail panel (read-only viewer; edit happens in popup)
    det_frame = labeled_frame(main, text=tr("事件詳情"))
    det_frame.grid(row=0, column=1, sticky="nsew")
    app._dyn_det_frame = det_frame

    # Always-visible action bar — buttons grey out when not usable instead of
    # appearing/disappearing (aligned with the 疾病 / 資料庫 tabs).  Layout:
    #   ➕ 新增事件 ｜ 選取事件：✏ 編輯  🗑 刪除   …（右）🗣 查看此事件的聲明
    actbar = ttk.Frame(det_frame)
    actbar.pack(fill=tk.X, padx=4, pady=(2, 0))
    app._dyn_edit_bar = actbar   # legacy attribute name
    app._dyn_new_event_btn = ttk.Button(
        actbar, text=tr("➕ 新增事件"),
        command=lambda: _new_event(app),
        style="success.TButton", state="disabled",
    )
    app._dyn_new_event_btn.pack(side=tk.LEFT, padx=(2, 8), pady=2)
    ttk.Label(actbar, text=tr("選取事件："),
              foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)
    app._dyn_edit_btn = ttk.Button(
        actbar, text=tr("✏ 編輯…"),
        command=lambda: _open_editor_for_selected(app),
        style="warning.TButton", state="disabled",
    )
    app._dyn_edit_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
    app._dyn_delete_btn = ttk.Button(
        actbar, text=tr("🗑 刪除"),
        command=lambda: _delete_selected_via_bar(app),
        style="danger.TButton", state="disabled",
    )
    app._dyn_delete_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
    app._dyn_restore_btn = ttk.Button(
        actbar, text=tr("↩ 復原刪除"),
        command=lambda: _restore_selected_via_bar(app),
        style="secondary.TButton",
    )
    # restore swaps in for delete only when the selected event is pending-delete.
    app._dyn_stmt_jump_btn = ttk.Button(
        actbar, text=tr("🗣 查看此事件的聲明"),
        command=lambda: _jump_to_statements(app),
        style="info.TButton", state="disabled",
    )
    app._dyn_stmt_jump_btn.pack(side=tk.RIGHT, padx=(0, 2), pady=1)

    # Read-only viewer
    det_inner = ttk.Frame(det_frame)
    det_inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    app._dyn_det_inner = det_inner
    det_inner.rowconfigure(0, weight=1)
    det_inner.columnconfigure(0, weight=1)

    app._dyn_detail_text = tk.Text(
        det_inner, wrap="word", state="disabled",
        font=("Microsoft JhengHei", 10), relief="flat", spacing1=2, spacing3=2,
    )
    det_vsb = ttk.Scrollbar(det_inner, orient="vertical",
                             command=app._dyn_detail_text.yview)
    app._dyn_detail_text.configure(yscrollcommand=det_vsb.set)
    app._dyn_detail_text.grid(row=0, column=0, sticky="nsew")
    det_vsb.grid(row=0, column=1, sticky="ns")

    # Event image (Player2; event_images/<event id>.png) — below the text.
    app._dyn_event_image = ImageThumbnail(det_inner, thumb_size=(260, 146))
    app._dyn_event_image.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    # Tags for detail text
    _configure_detail_tags(app._dyn_detail_text)
    # AFTER the tags exist: registration snapshots tag fonts, so registering
    # first scaled only the widget default — and every character of this pane
    # is tagged, so nothing visibly changed.
    preview_font.register(app._dyn_detail_text)

    # Internal state
    app._dyn_filtered_events: List[dict] = []
    app._dyn_lb_map: List[dict] = []
    app._dyn_selected_event_id: Optional[str] = None
    # Statements sub-tab needs to refresh the shared staging widgets.
    app._dyn_refresh_pending = lambda: _refresh_pending_widgets(app)

    # Initial render
    refresh_dynamic_events_tab(app)


# ── Refresh entry point ───────────────────────────────────────────────

def refresh_dynamic_events_tab(app) -> None:
    """Repopulate kingdom filter options and reload event list + sub-tabs."""
    _rebuild_kingdom_options(app)
    _apply_and_refresh_list(app)
    _refresh_pending_widgets(app)
    # Stage B sub-tabs read app.diplomacy_bundle refreshed by the same reload.
    for fn_name in ("_stmt_refresh", "_diplo_status_refresh"):
        fn = getattr(app, fn_name, None)
        if fn is not None:
            try:
                fn()
            except Exception:
                pass


# ── Internal helpers ──────────────────────────────────────────────────

def _configure_detail_tags(t: tk.Text) -> None:
    t.tag_configure("title",    font=("Microsoft JhengHei", 12, "bold"), foreground=tcol("#1A3A5C"))
    t.tag_configure("section",  font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#2471A3"))
    t.tag_configure("key",      font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#6B5B3E"))
    t.tag_configure("val",      font=("Microsoft JhengHei", 10),         foreground=tcol("#333333"))
    t.tag_configure("desc",     font=("Microsoft JhengHei", 10),         foreground=tcol("#222222"))
    t.tag_configure("hist_day", font=("Microsoft JhengHei", 9, "bold"),  foreground=tcol("#555555"))
    t.tag_configure("hist_txt", font=("Microsoft JhengHei", 9),          foreground=tcol("#444444"))
    t.tag_configure("eco_good", font=("Microsoft JhengHei", 9),          foreground=tcol("#1A8A4A"))
    t.tag_configure("eco_bad",  font=("Microsoft JhengHei", 9),          foreground=tcol("#C0392B"))
    t.tag_configure("eco_key",  font=("Microsoft JhengHei", 9, "bold"),  foreground=tcol("#555555"))
    t.tag_configure("empty",    font=("Microsoft JhengHei", 10, "italic"), foreground=tcol("#999999"))
    t.tag_configure("placeholder", font=("Microsoft JhengHei", 10, "italic"), foreground=tcol("#999999"))
    t.tag_configure("pending_delete", font=("Microsoft JhengHei", 10, "italic"), foreground=tcol("#C0392B"), overstrike=True)
    t.tag_configure("pending_edit",   font=("Microsoft JhengHei", 9, "italic"),  foreground=tcol("#27AE60"))
    for tkey, color in _type_colors().items():
        t.tag_configure(f"type_{tkey}", foreground=color,
                        font=("Microsoft JhengHei", 10, "bold"))


def _rebuild_kingdom_options(app) -> None:
    """Collect unique kingdoms from all events and update kingdom combobox.

    Display value uses ``app.resolve_kingdom_name(kid)`` so the dropdown
    shows translated names while filtering still uses raw ID.
    """
    events = getattr(app, "world_dynamic_events_items", [])
    kingdoms: Set[str] = set()
    for e in events:
        for k in e.get("kingdoms_involved", []) or []:
            kingdoms.add(str(k))

    resolver = getattr(app, "resolve_kingdom_name", None)
    display_to_key: Dict[str, str] = {_all_label(): ""}
    sorted_kingdoms = sorted(kingdoms)
    options = [_all_label()]
    for k in sorted_kingdoms:
        disp = resolver(k) if callable(resolver) else k
        # Keep raw ID alongside display name to disambiguate duplicates
        label = f"{disp} ({k})" if disp != k else k
        display_to_key[label] = k
        options.append(label)
    app._dyn_kingdom_cb.configure(values=options)
    app._dyn_kingdom_display_to_key = display_to_key
    cur = app._dyn_filter_kingdom.get()
    if cur not in options:
        app._dyn_filter_kingdom.set(_all_label())


def _apply_filters(app) -> List[dict]:
    """Apply filter widgets + sort according to user-selected direction."""
    type_display = app._dyn_filter_type.get()
    type_key     = app._dyn_type_display_to_key.get(type_display, "")
    fimp_str     = app._dyn_filter_importance.get()
    king_display = app._dyn_filter_kingdom.get()
    king_key     = app._dyn_kingdom_display_to_key.get(king_display, "")
    fplay        = app._dyn_filter_player.get()
    fkw          = app._dyn_filter_kw.get().strip()

    fimp = None
    if fimp_str != _all_label():
        try:
            fimp = int(fimp_str)
        except ValueError:
            fimp = None

    events = getattr(app, "world_dynamic_events_items", [])

    # Drop events that are pending-delete from the visible list, but
    # keep them in the underlying data so 取消 can restore them.
    pending = getattr(app, "dyn_events_pending", None) or {}
    pending_deletes = pending.get("delete_ids", set())

    filtered = svc_filter_events(
        events,
        type_eq=type_key or None,
        importance_eq=fimp,
        kingdom_in=king_key or None,
        player_only=fplay,
        keyword=fkw or None,
    )
    sort_dir = getattr(app, "_dyn_filter_sort", None)
    descending = True
    if sort_dir is not None:
        descending = (sort_dir.get() == getattr(app, "_DYN_SORT_NEW_FIRST", tr("新→舊")))
    return sort_events_by_creation(filtered, descending=descending)


def _apply_and_refresh_list(app) -> None:
    """Re-apply filters and repopulate the listbox (Stage F: sorted newest-first,
    delete-pending events shown with strikethrough)."""
    filtered = _apply_filters(app)
    app._dyn_filtered_events = filtered

    type_label_map = _type_label_map()
    pending = getattr(app, "dyn_events_pending", None) or {}
    pending_deletes: Set[str] = pending.get("delete_ids", set())
    pending_edits:   Dict[str, dict] = pending.get("edits", {})
    new_events:      List[dict] = pending.get("new_events", []) or []

    # Staged-new events are shown first (always, regardless of filters) with a ➕
    # marker.  Each event spans TWO listbox lines for easy visual separation:
    #   line 1: 時間-[類型]★重要度
    #   line 2: 　　標題           (indented with full-width spaces)
    # Both line indices map to the same event so a click on either selects it;
    # ``_dyn_lb_pair[idx]`` gives the event's line-1 index, ``_dyn_lb_first[pos]``
    # the line-1 index per combined position.
    combined: List[dict] = list(new_events) + list(filtered)
    app._dyn_lb_map = []          # listbox index → event
    app._dyn_lb_new_index = []    # listbox index → new-event index | None
    app._dyn_lb_pair = []         # listbox index → its event's line-1 index
    app._dyn_lb_first: List[int] = []   # combined pos → line-1 listbox index

    lb = app._dyn_lb
    lb.delete(0, tk.END)

    for pos, e in enumerate(combined):
        is_new = pos < len(new_events)
        eid = str(e.get("id", ""))
        edited = {} if is_new else pending_edits.get(eid, {})
        etype  = normalize_type(e.get("type", "?"))
        type_label = type_label_map.get(etype, e.get("type", etype))
        imp_val    = edited.get("importance", e.get("importance", ""))
        imp        = _importance_label(imp_val)
        title      = edited.get("title", e.get("title", e.get("id", "?")))

        days = e.get("creation_campaign_days")
        try:
            time_prefix = format_game_time(float(days))
        except (TypeError, ValueError):
            time_prefix = tr("（無日期）")

        if is_new:
            marker = "➕ "
        elif eid in pending_deletes:
            marker = "🗑 "
        elif edited:
            marker = "✏ "
        else:
            marker = ""

        nidx = pos if is_new else None
        first = lb.size()
        app._dyn_lb_first.append(first)
        lb.insert(tk.END, f"{marker}{time_prefix}-[{type_label}]{imp}")
        lb.insert(tk.END, f"　　{title}")
        for _ in range(2):
            app._dyn_lb_map.append(e)
            app._dyn_lb_new_index.append(nidx)
            app._dyn_lb_pair.append(first)

    total = len(getattr(app, "world_dynamic_events_items", []))
    shown = len(filtered)
    parts = []
    if shown == total:
        parts.append(tr("共 {total} 筆").format(total=total))
    else:
        parts.append(tr("{shown} / {total} 筆").format(shown=shown, total=total))
    if new_events:
        parts.append(tr("暫存新增 {v0} 筆").format(v0=len(new_events)))
    if pending_deletes:
        parts.append(tr("暫存刪除 {v0} 筆").format(v0=len(pending_deletes)))
    if pending_edits:
        parts.append(tr("暫存編輯 {v0} 筆").format(v0=len(pending_edits)))
    app._dyn_count_var.set(" · ".join(parts))

    # Try to restore selection if the previously-selected event is still visible
    # (select BOTH lines of the event so the whole row highlights).
    if app._dyn_selected_event_id:
        for pos, e in enumerate(combined):
            if str(e.get("id", "")) == app._dyn_selected_event_id:
                first = app._dyn_lb_first[pos]
                app._dyn_lb_selecting = True
                try:
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(first, first + 1)
                finally:
                    app._dyn_lb_selecting = False
                lb.see(first + 1)
                lb.see(first)
                app._dyn_selected_new_index = (
                    app._dyn_lb_new_index[first] if first < len(app._dyn_lb_new_index) else None)
                _render_panel_for_event(app, e)
                return

    # No selection — clear panels
    _render_panel_for_event(app, None)


def _clear_filters(app) -> None:
    app._dyn_filter_type.set(_all_label())
    app._dyn_filter_importance.set(_all_label())
    app._dyn_filter_kingdom.set(_all_label())
    app._dyn_filter_player.set(False)
    app._dyn_filter_kw.set("")
    if hasattr(app, "_dyn_filter_sort") and hasattr(app, "_DYN_SORT_NEW_FIRST"):
        app._dyn_filter_sort.set(app._DYN_SORT_NEW_FIRST)


def _reload_dyn_tab(app) -> None:
    """Reload campaign data from disk and refresh the tab.

    Mirrors the main tab's reload, but first checks for pending changes so
    edits aren't silently lost.
    """
    n = _pending_total(app)
    if n > 0:
        choice = _ask_save_discard_cancel(
            app,
            tr("有未儲存的變更"),
            tr("重新載入會丟棄目前 {n} 個尚未儲存的事件變更。\n\n要如何處理？").format(n=n),
        )
        if choice == "cancel":
            return
        if choice == "save":
            if not app._dyn_commit(confirm=False):   # user already chose save
                return
        elif choice == "discard":
            app._dyn_discard(skip_confirm=True)
    # Delegate to the main app refresh (it reloads everything and triggers
    # this tab's refresh as part of its workflow).
    try:
        app.refresh(ask_dirty=False)
    except TypeError:
        # refresh() may not accept ask_dirty in some signatures
        app.refresh()
    refresh_dynamic_events_tab(app)


def _on_event_select(app) -> None:
    # Guard against the re-entrant <<ListboxSelect>> our own snap fires.
    if getattr(app, "_dyn_lb_selecting", False):
        return
    lb = app._dyn_lb
    sel = lb.curselection()
    if not sel:
        app._dyn_selected_event_id = None
        app._dyn_selected_new_index = None
        _sync_stmt_jump_btn(app)
        _render_panel_for_event(app, None)
        return
    idx = sel[0]
    lb_map = getattr(app, "_dyn_lb_map", [])
    if idx >= len(lb_map):
        app._dyn_selected_event_id = None
        app._dyn_selected_new_index = None
        _sync_stmt_jump_btn(app)
        _render_panel_for_event(app, None)
        return
    event = lb_map[idx]
    # Snap selection to both lines of the event (full-row highlight).
    pair = getattr(app, "_dyn_lb_pair", [])
    first = pair[idx] if idx < len(pair) else idx
    app._dyn_lb_selecting = True
    try:
        lb.selection_clear(0, tk.END)
        lb.selection_set(first, first + 1)
    finally:
        app._dyn_lb_selecting = False
    nidx_map = getattr(app, "_dyn_lb_new_index", [])
    app._dyn_selected_new_index = nidx_map[first] if first < len(nidx_map) else None
    app._dyn_selected_event_id = str(event.get("id", ""))
    _sync_stmt_jump_btn(app)
    _render_panel_for_event(app, event)


def _sync_stmt_jump_btn(app) -> None:
    btn = getattr(app, "_dyn_stmt_jump_btn", None)
    if btn is not None:
        btn.configure(state="normal" if app._dyn_selected_event_id else "disabled")


# ── Cross-subtab navigation (Stage B) ─────────────────────────────────

def _jump_to_statements(app) -> None:
    """Switch to the statements sub-tab filtered to the selected event."""
    eid = app._dyn_selected_event_id
    if not eid:
        return
    show = getattr(app, "_stmt_show_event", None)
    if show is not None:
        show(eid)


def select_event_by_id(app, event_id: str) -> bool:
    """Select *event_id* in the events sub-tab (clearing filters if hidden).

    Used by the statements sub-tab's reverse jump. Returns True on success.
    """
    eid = str(event_id or "")
    if not eid:
        return False

    def _try_select() -> bool:
        for idx, ev in enumerate(getattr(app, "_dyn_lb_map", [])):
            if str(ev.get("id", "")) == eid:
                app._dyn_lb.selection_clear(0, tk.END)
                app._dyn_lb.selection_set(idx)
                app._dyn_lb.see(idx)
                _on_event_select(app)
                return True
        return False

    if not _try_select():
        # Event exists but is filtered out → clear filters and retry.
        _clear_filters(app)
        if not _try_select():
            return False
    nb = getattr(app, "_dyn_inner_nb", None)
    sub = getattr(app, "_dyn_sub_events", None)
    if nb is not None and sub is not None:
        nb.select(sub)
    return True


def _render_panel_for_event(app, event: Optional[dict]) -> None:
    """Render the right panel.

    The viewer is always shown; in edit mode we additionally surface a slim
    action bar at the top (✏ 編輯 + 🗑 刪除 / ↩ 復原).  The actual editing
    happens in :mod:`dialogs.dynamic_event_editor_dialog` so the workspace
    stays clean and the dialog can offer a much richer character / kingdom
    picker than the embedded layout could.
    """
    _refresh_edit_bar(app, event)
    _render_detail(app, event)


def _refresh_edit_bar(app, event: Optional[dict]) -> None:
    """Sync the always-visible action-bar button states.

    Buttons stay visible at all times; they grey out when not usable (no
    selection / not in edit mode).  Delete and Restore share one slot — Restore
    swaps in only when the selected event is pending-delete.
    """
    in_edit_mode = bool(app._dyn_edit_var.get())
    has_sel = event is not None

    def _state(attr: str, on: bool) -> None:
        b = getattr(app, attr, None)
        if b is not None:
            try:
                b.configure(state="normal" if on else "disabled")
            except Exception:
                pass

    # ➕ 新增事件 — edit mode only (independent of selection).
    _state("_dyn_new_event_btn", in_edit_mode)

    eid = str(event.get("id", "")) if event else ""
    pending = getattr(app, "dyn_events_pending", None) or {}
    is_pending_delete = bool(eid) and eid in (pending.get("delete_ids") or set())

    # ✏ 編輯 — edit mode + selection + not pending-delete.
    _state("_dyn_edit_btn", in_edit_mode and has_sel and not is_pending_delete)

    delete_btn  = getattr(app, "_dyn_delete_btn",  None)
    restore_btn = getattr(app, "_dyn_restore_btn", None)
    if is_pending_delete:
        if delete_btn is not None:
            try: delete_btn.pack_forget()
            except Exception: pass
        if restore_btn is not None:
            try:
                if not restore_btn.winfo_ismapped():
                    restore_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
            except Exception: pass
        _state("_dyn_restore_btn", in_edit_mode and has_sel)
    else:
        if restore_btn is not None:
            try: restore_btn.pack_forget()
            except Exception: pass
        if delete_btn is not None:
            try:
                if not delete_btn.winfo_ismapped():
                    delete_btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)
            except Exception: pass
        _state("_dyn_delete_btn", in_edit_mode and has_sel)


def _open_editor_for_selected(app) -> None:
    from dialogs.dynamic_event_editor_dialog import open_dynamic_event_editor
    nidx = getattr(app, "_dyn_selected_new_index", None)
    if nidx is not None:
        open_dynamic_event_editor(app, "", new_index=nidx)
        return
    eid = getattr(app, "_dyn_selected_event_id", None)
    if not eid:
        return
    open_dynamic_event_editor(app, eid)


def _companion_mod_warning(app, *, kind: str) -> bool:
    """Once-per-session warning that tool-created content won't propagate in-game.

    *kind* is "event" or "statement".  Returns True to proceed, False to cancel.
    AI Influence only assigns events to NPCs / schedules statement responses /
    instantiates economic effects through its in-game generation pipeline
    (DiplomacyManager / EconomicEffectsManager).  Content added purely from this
    tool shows in the World Events list but is otherwise inert until a companion
    mod can inject it through the mod's own APIs.  Editing existing text works.
    """
    flag = f"_companion_warned_{kind}"
    if getattr(app, flag, False):
        return True
    label = tr("事件") if kind == "event" else tr("聲明")
    ok = messagebox.askokcancel(
        tr("新增{label}的限制").format(label=label),
        tr("⚠ 純由本工具「新增」的{label}，遊戲不會將其納入 AI 效應機制——即使核心模組運作中也一樣（經實測，目前仍無法可靠地讓「新增」的事件／聲明真正生效）：\n\n  • 不會指派給任何 NPC（角色檔的 DynamicEvents 不會新增此 id）\n  • 不會觸發其他王國的聲明回應\n  • 內嵌的經濟效果不會套用到定居點\n\n目前唯一能讓「新增」實際生效的作法，是你自行到相關角色的存檔 JSON、在其 DynamicEvents 欄位手動加入此事件 id——但這相當繁瑣、不便。\n\n本工具真正可靠的用途是「編輯遊戲『已生成』的既有事件／聲明文字」——例如修正 AI 生成內容的邏輯或文字錯誤。\n\n（本提示每次啟動只顯示一次）仍要新增嗎？").format(label=label),
        icon="warning",
        parent=app.root,
    )
    if ok:
        setattr(app, flag, True)
    return ok


def _open_dyn_help(app) -> None:
    """Tabbed mini-manual for the 動態事件 tab — what edits work, what doesn't,
    and why.  Content is hardcoded zh-Hant (like the diplo help popup)."""
    win = tk.Toplevel(app.root)
    win.title(tr("動態事件使用說明"))
    W, H = 760, 580
    win.transient(app.root)
    try:
        app._center_window(win, W, H)
    except Exception:
        win.geometry(f"{W}x{H}")
    try:
        win.grab_set()
    except Exception:
        pass

    nb = ttk.Notebook(win)
    nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

    def _page(title: str, blocks):
        frame = ttk.Frame(nb)
        nb.add(frame, text=tr(title))
        txtf = ttk.Frame(frame)
        txtf.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        t = tk.Text(txtf, wrap="word", font=("Microsoft JhengHei", 10),
                    relief="flat", padx=12, pady=8, spacing1=2, spacing3=3,
                    cursor="arrow")
        vsb = ttk.Scrollbar(txtf, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=vsb.set)
        t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        t.tag_configure("h", font=("Microsoft JhengHei", 12, "bold"),
                        foreground=tcol("#1A3A5C"), spacing1=10, spacing3=4)
        t.tag_configure("body", foreground=tcol("#222222"), spacing1=2, spacing3=3)
        t.tag_configure("ok", font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#1A7A3F"))
        t.tag_configure("warn", font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#C0392B"))
        t.tag_configure("tip", font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#B5852E"))
        for tag, text in blocks:
            t.insert("end", tr(text) + "\n", tag)
        t.configure(state="disabled")
        t.see("1.0")

    _page("📌 總覽與侷限", [  # noqa: cjk (help text tr()-translated at use)
        ("h", "先理解邊界，省下大量試誤"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "本工具對「動態事件」的編輯有明確的能力邊界。先分清楚什麼有效、"
                 "什麼無效，會讓你事半功倍。"),  # noqa: cjk (help text tr()-translated at use)
        ("ok", "✅ 最有效：編輯由遊戲正常流程「已生成」的事件與聲明（文字與屬性）。"),  # noqa: cjk (help text tr()-translated at use)
        ("warn", "⚠ 不穩定／無效：新增事件、新增聲明，以及調整「已經作用過」的效果"
                 "（如經濟效果、王國關係變化）。"),  # noqa: cjk (help text tr()-translated at use)
        ("h", "為什麼？"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "許多效果是在「遊戲生成事件的當下」就立即結算並寫入存檔——例如經濟效果"
                 "會被攤平套用到各定居點、關係增減會直接加到王國之間。事後再用本工具修改，"
                 "存檔裡那些既成結果並不會回溯改變。\n\n"
                 "相對地，後端 AI 只有在「載入某個事件、要生成新的回應／聲明」時，才會重新"
                 "讀取該事件的敘事與屬性。因此你改的若是「未來 AI 會再讀到的資訊」就有效；"
                 "改的若是「過去已結算的結果」就無效。"),  # noqa: cjk (help text tr()-translated at use)
        ("tip", "一句話：能改的是「未來會被再讀取的資訊」，不能改的是「過去已結算的結果」。"),  # noqa: cjk (help text tr()-translated at use)
    ])

    _page("✏ 編輯事件", [  # noqa: cjk (help text tr()-translated at use)
        ("h", "可有效調整的事件欄位"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "當你發現某個 AI 生成的事件出現敘事矛盾、設定錯誤，或只是不滿意，"
                 "可以用本工具調整以下欄位。它們會在後端 AI 下次載入此事件生成回應時被"
                 "讀取，因此調整有效："),  # noqa: cjk (help text tr()-translated at use)
        ("body", "　• 標題、描述　（最常用——修正文字或邏輯）\n"
                 "　• 類型（軍事／政治／經濟…）\n"
                 "　• 涉及的王國與角色\n"
                 "　• 重要度\n"
                 "　• 建立日期（開始時間）與到期日期\n"
                 "　• 各王國回應率（詳見「回應率」分頁）"),  # noqa: cjk (help text tr()-translated at use)
        ("warn", "❌ 無法有效調整：事件內嵌的「經濟效果」。"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "繁榮／食物／物價等變化，是在事件生成的當下就套用到定居點並寫入存檔的；"
                 "事後修改事件內嵌的效果，不會改變存檔中已生效的數值。編輯器內雖仍可改"
                 "（已加橙色警告橫幅），但僅供檢視／理論用途。"),  # noqa: cjk (help text tr()-translated at use)
    ])

    _page("🗣 編輯聲明", [  # noqa: cjk (help text tr()-translated at use)
        ("h", "可有效調整的統治者聲明"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "統治者聲明（外交包）除了可以調整「聲明文字」，也可以調整其外交動作的"
                 "參數，例如："),  # noqa: cjk (help text tr()-translated at use)
        ("body", "　• 索要的領地（定居點）\n"
                 "　• 賠款金額\n"
                 "　• 貢金（每日金額／持續天數）\n"
                 "　• 稅率、隔離天數、目標氏族等"),  # noqa: cjk (help text tr()-translated at use)
        ("tip", "💡 實務上，AI 最常出錯的就是「索要領地」的選擇——例如索要一個地理上"
                "不合理、或根本沒有爭議的領地。把目標定居點改成合理對象，是很實用的修正。"),  # noqa: cjk (help text tr()-translated at use)
        ("warn", "❌ 無法有效調整：聲明內嵌的「關係變化（relation_changes）」。"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "王國之間的關係增減，是在事件生成的當下就結算並寫入存檔，事後修改不會"
                 "回溯影響既有關係。"),  # noqa: cjk (help text tr()-translated at use)
    ])

    _page("📊 回應率", [  # noqa: cjk (help text tr()-translated at use)
        ("h", "回應率是什麼"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "「各王國回應率」（kingdom_engagement）是每個事件對每個王國的 0–100 數值，"
                 "代表遊戲每日為該王國擲骰、決定是否針對「這個事件」發出統治者聲明的機率。"),  # noqa: cjk (help text tr()-translated at use)
        ("warn", "⏳ 重要：調整回應率只影響「尚未被回應過」的事件／王國。"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "已經回應過（已產生聲明）的組合，不會因為你調高回應率而重新觸發。"),  # noqa: cjk (help text tr()-translated at use)
        ("tip", "別和「外交狀態」分頁的「回應壓力」混淆：回應率是「單一事件」的屬性；"
                "回應壓力是「整個王國跨事件累積」的全域狀態。詳見外交狀態分頁右上角的"
                "「ⓘ 回應率/壓力說明」。"),  # noqa: cjk (help text tr()-translated at use)
    ])

    _page("➕ 新增事件/聲明", [  # noqa: cjk (help text tr()-translated at use)
        ("h", "新增目前無法有效傳播"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "純由本工具「新增」的事件或聲明，目前無法被遊戲的 AI 效應機制傳播或生效"
                 "——即使核心模組運作中也一樣。新增的內容只會出現在本工具的清單中，但："),  # noqa: cjk (help text tr()-translated at use)
        ("body", "　• 不會指派給任何 NPC\n"
                 "　• 不會觸發其他王國的回應\n"
                 "　• 內嵌的經濟效果不會套用"),  # noqa: cjk (help text tr()-translated at use)
        ("tip", "🔧 唯一的手動變通：自行到「相關角色的存檔 JSON」，在其 DynamicEvents 欄位"
                "手動加入該事件的 id。如此該角色在生成回應時才會「知道」這個事件。"),  # noqa: cjk (help text tr()-translated at use)
        ("warn", "但這作法相當繁瑣、容易出錯，且需要逐一處理每個你希望知情的角色，並不方便。"),  # noqa: cjk (help text tr()-translated at use)
        ("body", "結論：除非你願意手動編輯角色 JSON，否則「新增」目前僅適合佔位／實驗用途；"
                 "想真正影響遊戲，請以「編輯既有事件／聲明」為主。"),  # noqa: cjk (help text tr()-translated at use)
    ])

    ttk.Button(win, text=tr("關閉"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.BOTTOM, anchor="e",
                                                padx=10, pady=(0, 8))


def _new_event(app) -> None:
    """Create a fresh event from the template, stage it, and open the editor."""
    if not bool(getattr(app, "_dyn_edit_var", None) and app._dyn_edit_var.get()):
        return
    if not _companion_mod_warning(app, kind="event"):
        return
    # Anchor the new event to the campaign's current day (bundle), else the
    # latest on-disk creation day, else 0.
    day = 0.0
    bundle = getattr(app, "diplomacy_bundle", None)
    if isinstance(bundle, dict):
        try:
            day = float(bundle.get("saved_campaign_days") or 0.0)
        except (TypeError, ValueError):
            day = 0.0
    if not day:
        for e in (getattr(app, "world_dynamic_events_items", []) or []):
            try:
                day = max(day, float(e.get("creation_campaign_days") or 0.0))
            except (TypeError, ValueError):
                pass
    tmpl = svc_new_event_template(event_type="political", creation_campaign_days=day, title="")
    idx = app._dyn_stage_new_event(tmpl)
    app._dyn_selected_event_id = str(tmpl.get("id", ""))
    app._dyn_selected_new_index = idx
    _refresh_pending_widgets(app)
    _apply_and_refresh_list(app)
    from dialogs.dynamic_event_editor_dialog import open_dynamic_event_editor
    open_dynamic_event_editor(app, "", new_index=idx)


def _delete_selected_via_bar(app) -> None:
    nidx = getattr(app, "_dyn_selected_new_index", None)
    if nidx is not None:
        # Staged-new event → just drop it from the buffer (nothing on disk yet).
        app._dyn_unstage_new_event(nidx)
        app._dyn_selected_event_id = None
        app._dyn_selected_new_index = None
        _refresh_pending_widgets(app)
        _apply_and_refresh_list(app)
        return
    eid = getattr(app, "_dyn_selected_event_id", None)
    if not eid:
        return
    if not messagebox.askyesno(
        tr("確認刪除"),
        tr("刪除後將從 dynamic_events.json 移除此事件，並清除所有 NPC JSON 中的引用。\n"
           "（按 💾 儲存才會實際寫入；按 ↩ 取消可復原）\n\n要繼續嗎？"),
        parent=app.root,
    ):
        return
    app._dyn_stage_delete(eid)
    _refresh_pending_widgets(app)
    _apply_and_refresh_list(app)


def _restore_selected_via_bar(app) -> None:
    eid = getattr(app, "_dyn_selected_event_id", None)
    if not eid:
        return
    app._dyn_stage_undelete(eid)
    _refresh_pending_widgets(app)
    _apply_and_refresh_list(app)


# ── Read-only detail renderer ─────────────────────────────────────────

def _render_detail(app, event: Optional[dict]) -> None:
    t = app._dyn_detail_text
    t.configure(state="normal")
    t.delete("1.0", "end")

    if event is None:
        t.insert("end", tr("（請點選左側事件以查看詳情）"), "empty")
        t.configure(state="disabled")
        if getattr(app, "_dyn_event_image", None) is not None:
            app._dyn_event_image.clear()
        return

    eid     = str(event.get("id", ""))

    # Event image (event_images/<id>.png under the active campaign folder).
    if getattr(app, "_dyn_event_image", None) is not None:
        img = None
        try:
            sd = getattr(app, "save_data_dir", None)
            cid = app._current_campaign_id()
            if sd and cid and eid:
                p = Path(sd) / cid / "event_images" / f"{eid}.png"
                if p.exists():
                    img = p
        except Exception:
            img = None
        app._dyn_event_image.load(img)
    pending = getattr(app, "dyn_events_pending", None) or {}
    pending_deletes: Set[str] = pending.get("delete_ids", set())
    pending_edits:   Dict[str, dict] = pending.get("edits", {})
    edits   = pending_edits.get(eid, {})

    # Pending-delete marker
    if eid in pending_deletes:
        t.insert("end", tr("⚠ 此事件已暫存刪除（按 💾 儲存才會生效）") + "\n\n", "pending_delete")

    # Staged-new marker
    new_ids = {str(e.get("id", "")) for e in (pending.get("new_events") or [])}
    if eid in new_ids:
        t.insert("end", tr("➕ 新事件（尚未儲存；按 💾 儲存才會寫入外交包）") + "\n\n", "pending_edit")

    # Effective field values: pending edit overrides on-disk value
    def eff(key, default=None):
        return edits[key] if key in edits else event.get(key, default)

    # ── Title ─────────────────────────────────────────────────────────
    title_str = str(eff("title", event.get("id", "?")))
    t.insert("end", title_str + "\n", "title")
    t.insert("end", "─" * 60 + "\n", "val")

    if edits:
        t.insert("end", tr("✏ 此事件有未儲存的暫存編輯") + "\n\n", "pending_edit")

    # ── Meta info ─────────────────────────────────────────────────────
    type_label_map = _type_label_map()
    etype     = normalize_type(event.get("type", "?"))
    type_text = type_label_map.get(etype, event.get("type", etype))
    type_tag  = f"type_{etype}"
    t.insert("end", f"{tr('類型')}：", "key")
    t.insert("end", type_text + "  ", type_tag)
    imp = eff("importance", "?")
    t.insert("end", f"  {tr('重要度')}：", "key")
    t.insert("end", _importance_label(imp) + "\n", "val")

    def kv(key: str, val: str) -> None:
        t.insert("end", f"{key}：", "key")
        t.insert("end", val + "\n", "val")

    # Kingdoms with translation
    kingdoms = eff("kingdoms_involved", []) or []
    if kingdoms:
        resolver = getattr(app, "resolve_kingdom_name", None)
        names = []
        for k in kingdoms:
            kid = str(k)
            if callable(resolver):
                disp = resolver(kid)
                names.append(f"{disp} ({kid})" if disp != kid else kid)
            else:
                names.append(kid)
        kv(tr("涉及王國"), "、".join(names))

    # Characters with name resolution
    chars = eff("characters_involved", []) or []
    if chars:
        resolver = getattr(app, "resolve_display_name", None)
        char_meta = getattr(app, "character_meta", {})
        t.insert("end", f"{tr('涉及角色')}：", "key")
        first = True
        for cid in chars:
            cid_s = str(cid)
            if not first:
                t.insert("end", "、", "val")
            first = False
            display = None
            source  = "id_only"
            if callable(resolver):
                try:
                    display, source = resolver(cid_s)
                except Exception:
                    display, source = cid_s, "id_only"
            else:
                # legacy path
                meta = char_meta.get(cid_s, {}) if isinstance(char_meta, dict) else {}
                display = meta.get("Name") or cid_s
                source = "json" if meta.get("Name") else "id_only"
            if source == "id_only":
                t.insert("end", display, "placeholder")
            else:
                t.insert("end", str(display), "val")
                if display != cid_s:
                    t.insert("end", f" ({cid_s})", "placeholder")
        t.insert("end", "\n")

    player_inv = eff("player_involved", False)
    kv(tr("涉及玩家"), "✓" if player_inv else "✗")

    applicable = eff("applicable_npcs", []) or []
    if applicable:
        kv(tr("適用對象"), "、".join(display_labels.applicable_npc_label(x) for x in applicable))
    participating = eff("participating_kingdoms", []) or []
    if participating:
        resolver = getattr(app, "resolve_kingdom_name", None)
        pnames = []
        for k in participating:
            kid = str(k)
            disp = resolver(kid) if callable(resolver) else kid
            pnames.append(f"{disp} ({kid})" if disp and disp != kid else kid)
        kv(tr("參與王國"), "、".join(pnames))

    creation = event.get("creation_campaign_days")
    expiry   = event.get("expiration_campaign_days")
    try:
        kv(tr("建立日期"), format_game_time(float(creation)))
    except (TypeError, ValueError):
        pass
    try:
        kv(tr("到期日期"), format_game_time(float(expiry)))
    except (TypeError, ValueError):
        pass

    # ── Description ───────────────────────────────────────────────────
    desc = str(eff("description", "")).strip()
    if desc:
        t.insert("end", "\n")
        t.insert("end", tr("📋 描述") + "\n", "section")
        t.insert("end", "─" * 40 + "\n", "val")
        t.insert("end", desc + "\n", "desc")

    # ── Event history (read-only — never editable) ────────────────────
    history = event.get("event_history", [])
    if history:
        t.insert("end", "\n")
        t.insert("end", tr("📅 歷史記錄") + "\n", "section")
        t.insert("end", "─" * 40 + "\n", "val")
        # Identify the latest entry so we can mark it (game UI displays this one).
        def _hist_day(h):
            try:
                return float(h.get("campaign_days", float("-inf")))
            except (TypeError, ValueError, AttributeError):
                return float("-inf")
        try:
            latest_idx = max(range(len(history)), key=lambda i: _hist_day(history[i]))
        except ValueError:
            latest_idx = -1
        for idx, entry in enumerate(history):
            days   = entry.get("campaign_days", 0.0)
            reason = entry.get("update_reason", "")
            hdesc  = str(entry.get("description", "")).strip()
            try:
                day_str = format_game_time(float(days))
            except (TypeError, ValueError):
                day_str = str(days)
            marker = tr("（最新・遊戲顯示此則）") if idx == latest_idx else ""
            t.insert("end", f"  {day_str}", "hist_day")
            if reason:
                t.insert("end", f" — {reason}", "hist_txt")
            if marker:
                t.insert("end", f"  {marker}", "pending_edit")
            t.insert("end", "\n")
            if hdesc:
                t.insert("end", f"    {hdesc}\n", "hist_txt")

    # ── Economic effects (inline) joined with economic_effects.json ──
    inline_effects = event.get("economic_effects", [])
    if inline_effects:
        eco_all = getattr(app, "economic_effects", [])
        creation_days = event.get("creation_campaign_days", -1e9)
        reason_to_ext: dict = {}
        for ext in eco_all:
            ext_reason = str(ext.get("Reason", "")).strip()
            if ext_reason:
                reason_to_ext.setdefault(ext_reason, []).append(ext)

        t.insert("end", "\n")
        t.insert("end", tr("💰 經濟效果") + "\n", "section")
        t.insert("end", "─" * 40 + "\n", "val")

        for ee in inline_effects:
            ee_reason = str(ee.get("reason", "")).strip()
            if ee_reason:
                t.insert("end", f"  ▶ {ee_reason}\n", "eco_key")
            # Authoritative snake-case numbers from the embedded effect itself.
            _render_embedded_eco(t, ee, app)
            # Supplementary: runtime economic_effects.json (PascalCase) if present.
            ext_matches = [
                x for x in reason_to_ext.get(ee_reason, [])
                if abs(float(x.get("StartDay", 0)) - float(creation_days)) < 1.0
            ]
            if not ext_matches:
                ext_matches = reason_to_ext.get(ee_reason, [])
            for ext in ext_matches:
                _render_eco_entry(t, ext, app)

    # ── Kingdom engagement (回應率) ────────────────────────────────────
    engagement = eff("kingdom_engagement", {}) or {}
    if isinstance(engagement, dict) and engagement:
        t.insert("end", "\n")
        t.insert("end", tr("📊 各王國回應率") + "\n", "section")
        t.insert("end", "─" * 40 + "\n", "val")
        resolver = getattr(app, "resolve_kingdom_name", None)
        for kid, pct in sorted(engagement.items(), key=lambda kv_: -_safe_int(kv_[1])):
            n = max(0, min(100, _safe_int(pct)))
            disp = resolver(str(kid)) if callable(resolver) else str(kid)
            bar = "▓" * (n // 10) + "░" * (10 - n // 10)
            t.insert("end", f"  {disp}  ", "key")
            t.insert("end", f"{bar} {n}%\n", "val")

    # ── Embedded statements summary ───────────────────────────────────
    emb_stmts = event.get("kingdom_statements", []) or []
    if emb_stmts:
        t.insert("end", "\n")
        t.insert("end", tr("🗣 內嵌統治者聲明：{v0} 筆").format(v0=len(emb_stmts)) + "\n", "section")
        t.insert("end", tr("（在編輯模式可用「🗣 查看此事件的聲明」跳至聲明子分頁）") + "\n",
                 "placeholder")

    # ── Statement schedule (debug, gray) ──────────────────────────────
    nsa = eff("next_statement_attempt_days", {}) or {}
    fsa = eff("failed_statement_attempts", {}) or {}
    if nsa or fsa:
        t.insert("end", "\n")
        t.insert("end", tr("⏳ 聲明排程：next_statement_attempt_days {v0} 筆 / failed_statement_attempts {v1} 筆").format(v0=len(nsa), v1=len(fsa)) + "\n", "placeholder")

    t.configure(state="disabled")
    t.see("1.0")


def _safe_int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _resolve_eco_target(app, target_type: Any, target_id: Any) -> str:
    """Resolve an economic-effect target id to a display name based on its
    ``target_type`` (``settlement`` / ``kingdom``).  Returns ``"name (id)"``
    when a terminology name is available, else the raw id."""
    tid = str(target_id or "")
    if not tid or tid == "?":
        return tid
    tt = str(target_type or "").strip().lower()
    name = None
    if tt in ("settlement", "town", "castle", "village"):
        fn = getattr(app, "resolve_settlement_name", None)
    elif tt in ("kingdom", "faction"):
        fn = getattr(app, "resolve_kingdom_name", None)
    else:
        # Unknown / numeric type: fall back to id shape.
        fn = (getattr(app, "resolve_settlement_name", None)
              if tid.startswith(("town_", "castle_", "village_")) else None)
    if callable(fn):
        try:
            name = fn(tid)
        except Exception:
            name = None
    return f"{name} ({tid})" if name and name != tid else tid


def _eco_target_type_label(tt: Any) -> str:
    """Localize an economic-effect target type (settlement / kingdom / …)."""
    return {
        "settlement": tr("定居點"), "kingdom": tr("王國"),
        "town": tr("城鎮"), "castle": tr("城堡"), "village": tr("村莊"),
        "faction": tr("陣營"),
    }.get(str(tt or "").strip().lower(), str(tt or ""))


def _eco_scope_label(scope: Any) -> str:
    """Localize an economic-effect target scope (towns / villages / …)."""
    return {
        "towns": tr("城鎮"), "villages": tr("村莊"),
        "castles": tr("城堡"), "all": tr("全部"),
    }.get(str(scope or "").strip().lower(), str(scope or ""))


def _eco_cat_display(cat: Any, app=None) -> str:
    """Localized 「名稱（id）」 for a market category id, reusing the editor's map."""
    from dialogs.dynamic_event_editor_dialog import _cat_display

    def _resolver(cid):
        fn = getattr(app, "resolve_item_name", None) if app is not None else None
        if callable(fn):
            try:
                name = fn(cid)
                if name and name != cid:
                    return name
            except Exception:
                pass
        return None
    return _cat_display(str(cat or ""), _resolver)


def _render_embedded_eco(t: tk.Text, ee: dict, app=None) -> None:
    """Render one event-embedded economic_effect's snake-case numbers."""
    tt    = ee.get("target_type", "")
    ti    = _resolve_eco_target(app, tt, ee.get("target_id", "?")) if app is not None \
            else str(ee.get("target_id", "?"))
    scope = ee.get("target_scope")
    dur   = ee.get("duration_days", "?")
    scope_s = f"/{_eco_scope_label(scope)}" if scope else ""
    t.insert("end", f"    [{_eco_target_type_label(tt)}:{ti}{scope_s}]  ({tr('持續')} {dur} {tr('日')})\n", "eco_key")
    per_day = [
        ("prosperity_delta_per_day", tr("繁榮")),
        ("food_delta_per_day",       tr("食物")),
        ("security_delta_per_day",   tr("治安")),
        ("loyalty_delta_per_day",    tr("忠誠")),
    ]
    for key, label in per_day:
        try:
            val = float(ee.get(key, 0) or 0)
        except (TypeError, ValueError):
            val = 0.0
        if val == 0:
            continue
        tag = "eco_good" if val > 0 else "eco_bad"
        t.insert("end", f"      {label} {val:+g}" + tr("/日") + "\n", tag)
    try:
        mult = float(ee.get("income_multiplier", 1) or 1)
    except (TypeError, ValueError):
        mult = 1.0
    if mult != 1.0:
        t.insert("end", f"      {tr('收入倍率')} ×{mult:g}\n",
                 "eco_good" if mult > 1 else "eco_bad")
    for m in (ee.get("market_price_modifiers", []) or []):
        if not isinstance(m, dict):
            continue
        cat = m.get("category_id", "?")
        try:
            pct = float(m.get("price_change_percent", 0) or 0)
        except (TypeError, ValueError):
            pct = 0.0
        tag = "eco_bad" if pct > 0 else "eco_good"  # higher price = bad for buyer
        t.insert("end", f"      {tr('物價')} {_eco_cat_display(cat, app)}: {pct:+g}%\n", tag)


def _render_eco_entry(t: tk.Text, ext: dict, app=None) -> None:
    target_id   = ext.get("TargetId", "?")
    target_type = ext.get("TargetType", "")
    duration    = ext.get("DurationDays", "?")
    ti = _resolve_eco_target(app, target_type, target_id) if app is not None \
         else str(target_id)
    t.insert("end", f"    [{_eco_target_type_label(target_type)}] {ti}  ({tr('持續')} {duration} {tr('日')})\n", "eco_key")
    fields = [
        ("ProsperityDeltaPerDay",  tr("繁榮"), tr("/日")),
        ("FoodDeltaPerDay",        tr("食物"), tr("/日")),
        ("SecurityDeltaPerDay",    tr("治安"), tr("/日")),
        ("LoyaltyDeltaPerDay",     tr("忠誠"), tr("/日")),
    ]
    for field, label, unit in fields:
        val = ext.get(field, 0.0)
        disp = _delta(val, unit)
        if not disp:
            continue
        tag = "eco_good" if float(val) > 0 else "eco_bad"
        t.insert("end", f"      {label}: {disp}\n", tag)
    income_mult = ext.get("IncomeMultiplier", 1.0)
    try:
        if abs(float(income_mult) - 1.0) > 1e-9:
            disp = _delta(income_mult, "%")
            tag  = "eco_good" if float(income_mult) > 1 else "eco_bad"
            t.insert("end", f"      {tr('收入倍率')}: {disp}\n", tag)
    except (TypeError, ValueError):
        pass


# ── Editor entry point ────────────────────────────────────────────────
# (The legacy inline editor was replaced in 0.5.3 by a popup dialog —
#  see :mod:`dialogs.dynamic_event_editor_dialog`.)




# ── Edit-mode toggle ──────────────────────────────────────────────────

def _toggle_edit_mode(app) -> None:
    """Checkbox command: pending-changes guard only — UI sync runs via trace."""
    editing = app._dyn_edit_var.get()
    # Guard: leaving edit mode while pending changes exist
    if not editing:
        n = _pending_total(app)
        if n > 0:
            choice = _ask_save_discard_cancel(
                app,
                tr("有未儲存的變更"),
                tr("目前有 {n} 個尚未儲存的事件變更。\n\n離開編輯模式前要如何處理？").format(n=n),
            )
            if choice == "cancel":
                app._dyn_edit_var.set(True)   # trace re-syncs UI
                return
            elif choice == "save":
                if not app._dyn_commit(confirm=False):   # user already chose save
                    app._dyn_edit_var.set(True)
                    return
            elif choice == "discard":
                app._dyn_discard(skip_confirm=True)
    _apply_edit_ui(app)


def _apply_edit_ui(app) -> None:
    """Idempotent panel sync for the current edit-mode state (no prompts)."""
    if not hasattr(app, "_dyn_lb_map"):
        return  # tab not fully built yet
    cur = None
    if app._dyn_selected_event_id:
        cur = next((e for e in app._dyn_lb_map
                    if str(e.get("id", "")) == app._dyn_selected_event_id), None)
    _render_panel_for_event(app, cur)


def _ask_save_discard_cancel(app, title: str, message: str) -> str:
    dlg = tk.Toplevel(app.root)
    dlg.title(title)
    dlg.transient(app.root)
    dlg.resizable(False, False)
    dlg.grab_set()
    ttk.Label(dlg, text=message, padding=14, justify="left",
              wraplength=440).pack()
    result = {"choice": "cancel"}
    def _set(v):
        result["choice"] = v
        dlg.destroy()
    btn = ttk.Frame(dlg)
    btn.pack(pady=(0, 12))
    ttk.Button(btn, text=tr("💾 儲存"), command=lambda: _set("save"),
               style="success.TButton").pack(side=tk.LEFT, padx=4)
    ttk.Button(btn, text=tr("🗑 丟棄"), command=lambda: _set("discard"),
               style="danger.TButton").pack(side=tk.LEFT, padx=4)
    ttk.Button(btn, text=tr("↩ 回去"), command=lambda: _set("cancel"),
               style="secondary.TButton").pack(side=tk.LEFT, padx=4)
    dlg.update_idletasks()
    x = app.root.winfo_x() + (app.root.winfo_width()  - dlg.winfo_width())  // 2
    y = app.root.winfo_y() + (app.root.winfo_height() - dlg.winfo_height()) // 2
    dlg.geometry(f"+{x}+{y}")
    dlg.wait_window()
    return result["choice"]


# ── Pending widget visibility ─────────────────────────────────────────

def _pending_total(app) -> int:
    # Delegate to the app's canonical counter so this never diverges from it.
    # (It also counts a staged response-pressure block, which an earlier inline
    # copy here missed — that made the 💾 儲存 / ↩ 取消 buttons stay hidden after a
    # pressure-only edit on the 外交狀態 sub-tab.)
    if hasattr(app, "_dyn_pending_count"):
        try:
            return app._dyn_pending_count()
        except Exception:
            pass
    pending = getattr(app, "dyn_events_pending", None) or {}
    return (len(pending.get("delete_ids", set())) + len(pending.get("edits", {}))
            + len(pending.get("new_events", []))
            + len(pending.get("stmt_deletes", set())) + len(pending.get("stmt_edits", {}))
            + len(pending.get("stmt_new", []))
            + (1 if pending.get("pressure") is not None else 0))


def _refresh_pending_widgets(app) -> None:
    n = _pending_total(app)
    if not hasattr(app, "_dyn_pending_var"):
        return
    app._dyn_pending_var.set(f" {n} {tr('暫存')} " if n > 0 else "")
    # Pack order for a side=RIGHT cluster (first packed = rightmost): save,
    # cancel, label → renders left→right as [label] [取消] [儲存] (status left,
    # confirm right), matching the tool-wide convention.
    for widget, kwargs_attr in (
        (app._dyn_save_btn,    "_dyn_save_btn_pack_kwargs"),
        (app._dyn_cancel_btn,  "_dyn_cancel_btn_pack_kwargs"),
        (app._dyn_pending_lbl, "_dyn_pending_lbl_pack_kwargs"),
    ):
        try:
            if n > 0:
                widget.pack(**getattr(app, kwargs_attr, {"side": "right"}))
            else:
                widget.pack_forget()
        except Exception:
            pass
