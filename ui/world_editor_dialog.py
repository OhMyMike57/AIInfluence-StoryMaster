from __future__ import annotations

from i18n import tr

from typing import List, Optional, Set, Tuple
import threading
import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox

from services.settings_service import sort_display_options, sort_key_from_label
from services import world_filter as wf
from ui.theme import labeled_frame
from ui.theme import tcol


# ── Filter-scope (篩選範圍) types — single-select, ordered per the design ──────
# Canonical filter-type keys — compared in logic, kept language-independent.
# The combobox shows localized labels (see ``_ft_display_options``); UI code
# stores the label in its StringVar and converts back with ``_ft_key``.
FT_ALL = "全部"              # noqa: cjk
FT_FACTION = "陣營"          # noqa: cjk
FT_GROUP = "群組"            # noqa: cjk
FT_INFO = "公開訊息擁有者"    # noqa: cjk
FT_SECRET = "秘密擁有者"      # noqa: cjk
FILTER_TYPES = [FT_ALL, FT_FACTION, FT_GROUP, FT_INFO, FT_SECRET]
MINOR_KEY = wf.MINOR_KEY   # 無陣營 bucket (clanless / kingdomless heroes)


def _ft_labels() -> dict:
    """Canonical filter-type key → localized label (built at call time)."""
    return {
        FT_ALL:     tr("全部"),
        FT_FACTION: tr("陣營"),
        FT_GROUP:   tr("群組"),
        FT_INFO:    tr("公開訊息擁有者"),
        FT_SECRET:  tr("秘密擁有者"),
    }


def _ft_display_options() -> List[str]:
    return [_ft_labels()[t] for t in FILTER_TYPES]


def _ft_key(label: str) -> str:
    """Localized label (or an already-canonical value) → canonical FT key."""
    label = (label or "").strip()
    for k, v in _ft_labels().items():
        if k == label or v == label:
            return k
    return FT_ALL


def _listbox_with_scroll(parent, **kw) -> tk.Listbox:
    """A Listbox paired with a vertical scrollbar, packed to fill *parent*."""
    wrap = ttk.Frame(parent)
    wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
    lb = tk.Listbox(wrap, **kw)
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=vsb.set)
    lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    return lb


def open_world_item_editor_dialog(app, kind: str, mode: str, idx: Optional[int] = None):
    is_info = kind == "info"
    items = app.world_info_items if is_info else app.world_secrets_items

    if mode == "edit":
        if idx is None or idx >= len(items):
            messagebox.showwarning(tr("編輯"), tr("請先選擇條目"))
            return
        item = dict(items[idx])
    else:
        item = {
            "id": "",
            "description": "",
            "applicableNPCs": ["all"],
        }
        if is_info:
            item.update({"usageChance": 70, "category": "world"})
        else:
            item.update({"knowledgeChance": 50, "accessLevel": "medium", "tags": []})

    title_mode = tr("編輯") if mode == "edit" else tr("新增")
    win = tk.Toplevel(app.root)
    win.title(f"{title_mode} {tr('公開訊息') if is_info else tr('秘密')}")
    W, H = 1500, 860
    win.geometry(f"{W}x{H}")
    app._center_window(win, W, H)
    win.transient(app.root)

    # ── Footer (packed first so the body can't squeeze it off-screen) ─────────
    foot = ttk.Frame(win)
    foot.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)

    body = ttk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 0))
    # 4 zones: [屬性+內容] [已擁有] [未擁有] [篩選+延伸].  The attribute column is
    # the widest (its fields/toggles need room); the filter column is the
    # narrowest (just a type picker + searches).
    body.columnconfigure(0, weight=17, uniform="col")
    body.columnconfigure(1, weight=12, uniform="col")
    body.columnconfigure(2, weight=12, uniform="col")
    body.columnconfigure(3, weight=8,  uniform="col")
    body.rowconfigure(0, weight=1)

    col_left   = ttk.Frame(body)
    col_owned  = ttk.Frame(body)
    col_unown  = ttk.Frame(body)
    col_filter = ttk.Frame(body)
    col_left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
    col_owned.grid(row=0, column=1, sticky="nsew", padx=5)
    col_unown.grid(row=0, column=2, sticky="nsew", padx=5)
    col_filter.grid(row=0, column=3, sticky="nsew", padx=(5, 0))

    # ── 屬性設定 (left, roomy) ────────────────────────────────────────────────
    attr_box = labeled_frame(col_left, text=tr("屬性設定"))
    attr_box.pack(fill=tk.X)
    attr_inner = ttk.Frame(attr_box)
    attr_inner.pack(fill=tk.X, padx=12, pady=(4, 12))
    attr_inner.grid_columnconfigure(1, weight=1)
    PADY = (10, 0)   # generous vertical rhythm so nothing feels squeezed

    ttk.Label(attr_inner, text="ID").grid(row=0, column=0, sticky="w", pady=(2, 0))
    id_row = ttk.Frame(attr_inner)
    id_row.grid(row=0, column=1, sticky="ew", padx=6, pady=(2, 0))
    id_var = tk.StringVar(value=str(item.get("id", "")))
    id_entry = ttk.Entry(id_row, textvariable=id_var)
    id_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    edit_id_var = tk.BooleanVar(value=(mode != "edit"))
    if mode == "edit":
        id_entry.configure(state="readonly")
        ttk.Checkbutton(
            id_row, text=tr("編輯ID"), variable=edit_id_var,
            command=lambda: id_entry.configure(state=("normal" if edit_id_var.get() else "readonly")),
        ).pack(side=tk.LEFT, padx=(8, 0))

    chance_key = "usageChance" if is_info else "knowledgeChance"
    chance_label = tr("使用機率") if is_info else tr("知悉機率")
    chance_var = tk.StringVar(value=str(item.get(chance_key, "")))
    ttk.Label(attr_inner, text=chance_label).grid(row=1, column=0, sticky="w", pady=PADY)
    ttk.Entry(attr_inner, textvariable=chance_var, width=12).grid(row=1, column=1, sticky="w", padx=6, pady=PADY)

    if is_info:
        ttk.Label(attr_inner, text=tr("分類")).grid(row=2, column=0, sticky="w", pady=PADY)
        category_labels = {tr("世界"): "world", tr("事件"): "event", tr("個人"): "personal"}
        category_reverse = {v: k for k, v in category_labels.items()}
        category_var = tk.StringVar(value=category_reverse.get(str(item.get("category", "world")), tr("世界")))
        ttk.Combobox(attr_inner, textvariable=category_var,
                     values=list(category_labels.keys()), width=14, state="readonly").grid(
            row=2, column=1, sticky="w", padx=6, pady=PADY)
        access_var = None
        tags_var = None
        access_labels = None
    else:
        ttk.Label(attr_inner, text=tr("存取等級")).grid(row=2, column=0, sticky="w", pady=PADY)
        access_labels = {tr("低"): "low", tr("中"): "medium", tr("高"): "high"}
        access_reverse = {v: k for k, v in access_labels.items()}
        access_var = tk.StringVar(value=access_reverse.get(str(item.get("accessLevel", "medium")), tr("中")))
        ttk.Combobox(attr_inner, textvariable=access_var,
                     values=list(access_labels.keys()), width=14, state="readonly").grid(
            row=2, column=1, sticky="w", padx=6, pady=PADY)
        ttk.Label(attr_inner, text=tr("標籤（逗號分隔）")).grid(row=3, column=0, sticky="w", pady=PADY)
        tags_var = tk.StringVar(value=", ".join(item.get("tags", []) if isinstance(item.get("tags"), list) else []))
        ttk.Entry(attr_inner, textvariable=tags_var).grid(
            row=3, column=1, sticky="ew", padx=6, pady=PADY)
        category_labels = None

    npc_row = 3 if is_info else 4
    ttk.Label(attr_inner, text=tr("適用NPC")).grid(row=npc_row, column=0, sticky="nw", pady=PADY)
    # per_row=3 wraps the six toggles to two rows; the column is wide enough.
    npc_vars = app._applicable_npc_picker(attr_inner, item.get("applicableNPCs", []),
                                          grid_row=npc_row, grid_col=1, per_row=3)

    # ── 主要內容 (left, fills remaining height) ───────────────────────────────
    content_box = labeled_frame(col_left, text=tr("主要內容"))
    content_box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
    desc_text = tk.Text(content_box, wrap="word", height=10)
    desc_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
    desc_text.insert("1.0", str(item.get("description", "")))

    # ── Shared state vars ─────────────────────────────────────────────────────
    owned_title_var = tk.StringVar(value=tr("已擁有 0"))
    selectable_title_var = tk.StringVar(value=tr("未擁有 0"))
    action_preview_var = tk.StringVar(value=tr("本次動作：尚未選取"))
    action_result_var = tk.StringVar(value="")

    # ── 已擁有 (middle) ───────────────────────────────────────────────────────
    owned_box = labeled_frame(col_owned, text=tr("已擁有"))
    owned_box.pack(fill=tk.BOTH, expand=True)
    own_toolbar = ttk.Frame(owned_box)
    own_toolbar.pack(fill=tk.X, padx=8, pady=(2, 4))
    ttk.Label(own_toolbar, textvariable=owned_title_var).pack(side=tk.RIGHT)
    have_list = _listbox_with_scroll(owned_box, selectmode=tk.EXTENDED, exportselection=False)

    # ── 未擁有 (middle-right) ─────────────────────────────────────────────────
    unown_box = labeled_frame(col_unown, text=tr("未擁有"))
    unown_box.pack(fill=tk.BOTH, expand=True)
    unown_toolbar = ttk.Frame(unown_box)
    unown_toolbar.pack(fill=tk.X, padx=8, pady=(2, 4))
    ttk.Label(unown_toolbar, textvariable=selectable_title_var).pack(side=tk.RIGHT)

    ctrl_row = ttk.Frame(unown_box)
    ctrl_row.pack(fill=tk.X, padx=8, pady=(0, 4))
    ttk.Label(ctrl_row, text=tr("排序")).pack(side=tk.LEFT)
    sort_mode_var = tk.StringVar(value=app.main_sort_var.get() or tr("收藏"))
    sort_combo = ttk.Combobox(ctrl_row, textvariable=sort_mode_var,
                              values=sort_display_options(), width=8, state="readonly")
    sort_combo.pack(side=tk.LEFT, padx=4)
    sort_reverse_var = tk.BooleanVar(value=False)
    exclude_uninteractive_var = tk.BooleanVar(value=app.exclude_uninteracted_var.get())
    ttk.Checkbutton(ctrl_row, text=tr("反轉"), variable=sort_reverse_var,
                    command=lambda: (refresh_have(), refresh_selectable(), update_action_preview())).pack(side=tk.LEFT, padx=(6, 0))
    ttk.Checkbutton(ctrl_row, text=tr("僅互動"), variable=exclude_uninteractive_var,
                    command=lambda: (refresh_selectable(), update_action_preview())).pack(side=tk.LEFT, padx=(6, 0))

    search_row = ttk.Frame(unown_box)
    search_row.pack(fill=tk.X, padx=8, pady=(0, 4))
    ttk.Label(search_row, text="🔍").pack(side=tk.LEFT)
    search_var = tk.StringVar(value="")
    ttk.Entry(search_row, textvariable=search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

    selectable_list = _listbox_with_scroll(unown_box, selectmode=tk.EXTENDED, exportselection=False)
    ttk.Label(unown_box, textvariable=action_preview_var).pack(anchor="w", padx=8, pady=(0, 1))
    ttk.Label(unown_box, textvariable=action_result_var, foreground=tcol("#0b5ed7")).pack(anchor="w", padx=8, pady=(0, 2))

    # Undo/redo — scoped strictly to 已擁有/未擁有 加入/移除 (not the form fields).
    undo_row = ttk.Frame(unown_box)
    undo_row.pack(fill=tk.X, padx=8, pady=(0, 2))
    undo_btn = ttk.Button(undo_row, text=tr("↩ 復原"), style="secondary.TButton",
                          command=lambda: _undo_transfer())
    undo_btn.pack(side=tk.LEFT, padx=(0, 4))
    redo_btn = ttk.Button(undo_row, text=tr("↪ 重做"), style="secondary.TButton",
                          command=lambda: _redo_transfer())
    redo_btn.pack(side=tk.LEFT)
    ttk.Label(unown_box, text=tr("復原／重做僅適用「已擁有／未擁有」的加入與移除"),
              foreground=tcol("#999999")).pack(anchor="w", padx=8, pady=(0, 6))

    # ── 篩選範圍 + 延伸範圍 (right, stacked) ──────────────────────────────────
    filter_box = labeled_frame(col_filter, text=tr("篩選範圍"))
    filter_box.pack(fill=tk.BOTH, expand=True)
    ftype_row = ttk.Frame(filter_box)
    ftype_row.pack(fill=tk.X, padx=8, pady=(2, 4))
    ttk.Label(ftype_row, text=tr("類型")).pack(side=tk.LEFT)
    filter_type_var = tk.StringVar(value=tr("全部"))
    filter_type_combo = ttk.Combobox(ftype_row, textvariable=filter_type_var,
                                     values=_ft_display_options(), width=14, state="readonly")
    filter_type_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

    fsearch_row = ttk.Frame(filter_box)
    fsearch_row.pack(fill=tk.X, padx=8, pady=(0, 4))
    ttk.Label(fsearch_row, text="🔍").pack(side=tk.LEFT)
    filter_search_var = tk.StringVar(value="")
    ttk.Entry(fsearch_row, textvariable=filter_search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
    filter_list = _listbox_with_scroll(filter_box, selectmode=tk.EXTENDED, exportselection=False)

    ext_box = labeled_frame(col_filter, text=tr("延伸範圍"))
    ext_box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
    # The 陣營-specific hint only appears when 陣營 is active; 延伸範圍 may host
    # other strategies in future, so the inactive hint stays generic.
    ext_hint_var = tk.StringVar(value=tr("（類型選「陣營」後啟用）"))
    ext_hint = ttk.Label(ext_box, textvariable=ext_hint_var, foreground=tcol("#999999"))
    ext_hint.pack(anchor="w", padx=8, pady=(2, 0))
    esearch_row = ttk.Frame(ext_box)
    esearch_row.pack(fill=tk.X, padx=8, pady=(2, 4))
    ttk.Label(esearch_row, text="🔍").pack(side=tk.LEFT)
    ext_search_var = tk.StringVar(value="")
    ext_search_entry = ttk.Entry(esearch_row, textvariable=ext_search_var)
    ext_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
    ext_list = _listbox_with_scroll(ext_box, selectmode=tk.EXTENDED, exportselection=False)

    # ── Data ──────────────────────────────────────────────────────────────────
    field = "KnownInfo" if is_info else "KnownSecrets"
    current_id = str(item.get("id", "")).strip()
    char_items = list(app.characters)
    owned_set: Set[str] = set()
    if current_id:
        for display, pth in char_items:
            d = app._safe_load_json(pth) or {}
            arr = d.get(field, [])
            if isinstance(arr, list) and current_id in arr:
                owned_set.add(display)

    all_names = {d for d, _ in char_items}
    candidate_base: Set[str] = set(all_names) - owned_set

    kingdom_names = (app.terminology_campaign or {}).get("kingdoms") or {}
    clan_names = (app.terminology_campaign or {}).get("clans") or {}

    have_map: List[str] = []
    selectable_map: List[str] = []
    filter_map: List[Tuple[str, str]] = []   # region ⑤: (kind, key)
    ext_map: List[str] = []                    # region ⑥: clan id

    def decor(label: str) -> str:
        return app._display_label(label, star=True)

    def sort_names(values: List[str]) -> List[str]:
        mode = sort_key_from_label(sort_mode_var.get())
        return app._sorted_character_displays(mode, sort_reverse_var.get(), list(values))

    def selected_raw(lb: tk.Listbox, mapping: List[str]) -> List[str]:
        return [mapping[i] for i in lb.curselection() if i < len(mapping)]

    def update_counts():
        owned_title_var.set(tr("已擁有 {n}").format(n=len(owned_set)))
        selectable_title_var.set(tr("未擁有 {n}").format(n=len(candidate_base)))

    def update_action_preview(*_):
        add_n = len(selectable_list.curselection())
        rm_n = len(have_list.curselection())
        action_preview_var.set(tr("本次動作：可加入 {add} / 可移除 {rm}").format(add=add_n, rm=rm_n))

    def refresh_have():
        top = have_list.yview()[0]   # preserve scroll position across rebuild
        have_map.clear()
        have_list.delete(0, tk.END)
        for n in sort_names(list(owned_set)):
            have_map.append(n)
            have_list.insert(tk.END, decor(n))
        have_list.yview_moveto(top)

    def refresh_selectable():
        top = selectable_list.yview()[0]   # preserve scroll position across rebuild
        selectable_map.clear()
        selectable_list.delete(0, tk.END)
        term = search_var.get().strip().lower()
        vals = list(candidate_base)
        if exclude_uninteractive_var.get():
            # NeverInteracted (LastInteractionTimeDays<0) is reliable across
            # 4.1.0 and 5.0.x (5.0.x may set interaction_count=1 on encounter).
            vals = [n for n in vals if not app.character_meta.get(n, {}).get("NeverInteracted", False)]
        if term:
            vals = [n for n in vals
                    if term in n.lower()
                    or term in str(app.character_meta.get(n, {}).get("StringId", "")).lower()]
        for n in sort_names(vals):
            selectable_map.append(n)
            selectable_list.insert(tk.END, decor(n))
        selectable_list.yview_moveto(top)

    # ── Filter-scope population (⑤) ──────────────────────────────────────────
    def refresh_filter_items(*_):
        filter_map.clear()
        filter_list.delete(0, tk.END)
        t = _ft_key(filter_type_var.get())
        if t == FT_ALL:
            filter_list.insert(tk.END, tr("（全部角色，免篩選）"))
            return
        rows: List[Tuple[str, str, str]] = []
        if t == FT_FACTION:
            rows = wf.faction_rows(app.character_meta, kingdom_names)
        elif t == FT_GROUP:
            for name, members in sorted(app.presets.items()):
                cnt = len([m for m in members if isinstance(m, str)]) if isinstance(members, list) else 0
                rows.append(("group", name, f"{name} ({cnt})"))
        elif t == FT_INFO:
            for it in app.world_info_items:
                iid = str(it.get("id", "")).strip()
                if not iid or (is_info and iid == current_id):
                    continue
                cnt = len(app.known_info_owners.get(iid, []))
                rows.append(("info", iid, f"{iid} ({cnt})"))
        elif t == FT_SECRET:
            for it in app.world_secrets_items:
                sid = str(it.get("id", "")).strip()
                if not sid or ((not is_info) and sid == current_id):
                    continue
                cnt = len(app.known_secret_owners.get(sid, []))
                rows.append(("secret", sid, f"{sid} ({cnt})"))

        term = filter_search_var.get().strip().lower()
        for kind, key, disp in rows:
            if term and term not in disp.lower() and term not in str(key).lower():
                continue
            filter_map.append((kind, key))
            filter_list.insert(tk.END, disp)

    def selected_kingdom_ids() -> Set[str]:
        out: Set[str] = set()
        for i in filter_list.curselection():
            if i < len(filter_map):
                kind, key = filter_map[i]
                if kind == "kingdom":
                    out.add(key)
        return out

    def selected_clan_ids() -> Set[str]:
        return {ext_map[i] for i in ext_list.curselection() if i < len(ext_map)}

    def _set_ext_enabled(enabled: bool):
        state = "normal" if enabled else "disabled"
        ext_search_entry.configure(state=state)
        ext_list.configure(state=("normal" if enabled else "disabled"))
        # 陣營-specific hint only while active; generic prompt otherwise.
        ext_hint_var.set(tr("依所選陣營列出氏族（可多選）") if enabled else tr("（類型選「陣營」後啟用）"))

    # ── Extension-scope population (⑥ clans, scoped to ⑤ kingdoms) ───────────
    def refresh_extension_items(*_):
        ext_map.clear()
        ext_list.delete(0, tk.END)
        active = (_ft_key(filter_type_var.get()) == FT_FACTION)
        _set_ext_enabled(active)
        if not active:
            return
        ksel = selected_kingdom_ids()
        term = ext_search_var.get().strip().lower()
        for cid, disp in wf.clan_rows(app.character_meta, clan_names, ksel):
            if term and term not in disp.lower() and term not in str(cid).lower():
                continue
            ext_map.append(cid)
            ext_list.insert(tk.END, disp)

    def compute_candidate_base() -> Set[str]:
        t = _ft_key(filter_type_var.get())
        if t == FT_ALL:
            base = set(all_names)
        elif t == FT_FACTION:
            base = wf.faction_candidates(all_names, app.character_meta,
                                         selected_kingdom_ids(), selected_clan_ids())
        else:
            items_sel = [filter_map[i] for i in filter_list.curselection() if i < len(filter_map)]
            base = wf.ref_candidates(items_sel, app.presets, app.known_info_owners,
                                     app.known_secret_owners, all_names)
        return base - owned_set

    def apply_filter(*_):
        nonlocal candidate_base
        candidate_base = compute_candidate_base()
        refresh_selectable()
        update_counts()
        update_action_preview()

    def on_filter_type_change(*_):
        refresh_filter_items()
        refresh_extension_items()
        apply_filter()

    def on_filter_select(*_):
        # Kingdom selection changed → rescope the clan list, then recompute.
        if _ft_key(filter_type_var.get()) == FT_FACTION:
            refresh_extension_items()
        apply_filter()

    # ── Transfer actions (with undo/redo, scoped to owned/unowned moves) ──────
    undo_stack: List[Set[str]] = []   # snapshots of owned_set BEFORE each change
    redo_stack: List[Set[str]] = []

    def _refresh_undo_buttons():
        undo_btn.configure(state=("normal" if undo_stack else "disabled"))
        redo_btn.configure(state=("normal" if redo_stack else "disabled"))

    def _restore_owned(snapshot: Set[str]):
        owned_set.clear()
        owned_set.update(snapshot)
        refresh_have()
        apply_filter()

    def _undo_transfer():
        if not undo_stack:
            return
        redo_stack.append(set(owned_set))
        _restore_owned(undo_stack.pop())
        action_result_var.set(tr("已復原一步"))
        _refresh_undo_buttons()

    def _redo_transfer():
        if not redo_stack:
            return
        undo_stack.append(set(owned_set))
        _restore_owned(redo_stack.pop())
        action_result_var.set(tr("已重做一步"))
        _refresh_undo_buttons()

    def add_owned(names: List[str]):
        before = set(owned_set)
        moved = 0
        for n in names:
            if n in candidate_base and n not in owned_set:
                owned_set.add(n)
                moved += 1
        if moved:
            undo_stack.append(before)
            redo_stack.clear()
            action_result_var.set(tr("已加入 {n} 位 NPC").format(n=moved))
            _refresh_undo_buttons()
        refresh_have()
        apply_filter()

    def remove_owned(names: List[str]):
        before = set(owned_set)
        moved = 0
        for n in names:
            if n in owned_set:
                owned_set.discard(n)
                moved += 1
        if moved:
            undo_stack.append(before)
            redo_stack.clear()
            action_result_var.set(tr("已移除 {n} 位 NPC").format(n=moved))
            _refresh_undo_buttons()
        refresh_have()
        apply_filter()

    # Action buttons — both panels keep their buttons ABOVE the list (consistent).
    ttk.Button(own_toolbar, text=tr("移除"),
               command=lambda: remove_owned(selected_raw(have_list, have_map))).pack(side=tk.LEFT, padx=2)
    ttk.Button(own_toolbar, text=tr("全部移除"),
               command=lambda: remove_owned(list(owned_set))).pack(side=tk.LEFT, padx=2)
    ttk.Button(unown_toolbar, text=tr("加入"),
               command=lambda: add_owned(selected_raw(selectable_list, selectable_map))).pack(side=tk.LEFT, padx=2)
    ttk.Button(unown_toolbar, text=tr("全部加入"),
               command=lambda: add_owned(list(selectable_map))).pack(side=tk.LEFT, padx=2)

    selectable_list.bind("<Return>", lambda e: (add_owned(selected_raw(selectable_list, selectable_map)), "break")[1])
    have_list.bind("<Delete>", lambda e: (remove_owned(selected_raw(have_list, have_map)), "break")[1])
    have_list.bind("<BackSpace>", lambda e: (remove_owned(selected_raw(have_list, have_map)), "break")[1])

    for lb in (selectable_list, have_list):
        lb.bind("<<ListboxSelect>>", update_action_preview)

    sort_combo.bind("<<ComboboxSelected>>", lambda e: (refresh_have(), refresh_selectable(), update_action_preview()))
    search_var.trace_add("write", lambda *_: (refresh_selectable(), update_action_preview()))

    filter_type_combo.bind("<<ComboboxSelected>>", on_filter_type_change)
    filter_list.bind("<<ListboxSelect>>", on_filter_select)
    ext_list.bind("<<ListboxSelect>>", apply_filter)
    filter_search_var.trace_add("write", lambda *_: refresh_filter_items())
    ext_search_var.trace_add("write", lambda *_: refresh_extension_items())

    # Initial paint
    refresh_filter_items()
    refresh_extension_items()
    refresh_have()
    apply_filter()
    _refresh_undo_buttons()

    # ── Save ──────────────────────────────────────────────────────────────────
    def save_item():
        # 1. Validate
        old_id = items[idx].get("id", "") if mode == "edit" else None
        if mode == "edit" and not edit_id_var.get() and old_id:
            id_var.set(str(old_id))
        item_id = id_var.get().strip()
        if not item_id:
            messagebox.showwarning(title_mode, tr("ID 不可為空"))
            return
        try:
            chance = int(chance_var.get().strip())
        except Exception:
            messagebox.showwarning(title_mode, tr("{chance_label}需為整數").format(chance_label=chance_label))
            return

        description_raw = desc_text.get("1.0", "end").strip()
        description = " ".join(seg.strip() for seg in description_raw.splitlines() if seg.strip())
        selected_npcs = [k for k, v in npc_vars.items() if v.get()] or ["all"]

        new_item: dict = {
            "id": item_id,
            "description": description,
            chance_key: chance,
            "applicableNPCs": selected_npcs,
        }
        if is_info:
            new_item["category"] = category_labels.get(category_var.get().strip(), "world")
        else:
            picked_access = access_var.get().strip() if access_var else tr("中")
            new_item["accessLevel"] = (
                access_labels.get(picked_access, "medium") if access_labels else "medium"
            )
            new_item["tags"] = [
                s.strip() for s in (tags_var.get() if tags_var else "").split(",") if s.strip()
            ]

        # 2. Count ownership changes (in-memory — owner maps are authoritative)
        target_map: dict = (
            app.known_info_owners if field == "KnownInfo" else app.known_secret_owners
        )
        before_key = old_id if (mode == "edit" and old_id) else item_id
        before_owners: set = set(target_map.get(before_key, []))
        changed_npc = len(before_owners.symmetric_difference(owned_set))

        id_change_notice = ""
        if mode == "edit" and old_id and old_id != item_id:
            id_change_notice = tr("\n將同步更新已擁有 NPC 的 Json 內對應 ID。")
        if not messagebox.askyesno(
            tr("確認變更"),
            tr("條目：{item_id}\n將更新 NPC 關聯數：{changed_npc} 位{id_change_notice}\n確定變更嗎？").format(item_id=item_id, changed_npc=changed_npc, id_change_notice=id_change_notice),
        ):
            return

        # 3. Apply item change to world list
        if mode == "edit":
            items[idx] = new_item
        else:
            old_id = None
            items.append(new_item)

        # 4. Disable buttons while saving
        save_btn.configure(state="disabled")
        cancel_btn.configure(state="disabled")
        total = max(len(char_items), 1)
        progress_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        save_progress.configure(maximum=total, value=0)
        save_progress_var.set(f"0 / {total}")

        # 5. Background worker — owner-map update (pure in-memory)
        def _worker() -> None:
            if old_id and old_id != item_id:
                target_map.pop(old_id, None)
            if owned_set:
                target_map[item_id] = sorted(owned_set)
            elif item_id in target_map:
                target_map.pop(item_id, None)
            for i in range(1, total + 1):
                win.after(0, lambda v=i: _on_progress(v))
            win.after(0, _on_complete)

        def _on_progress(value: int) -> None:
            if not win.winfo_exists():
                return
            save_progress.configure(value=value)
            save_progress_var.set(f"{value} / {total}")

        def _on_complete() -> None:
            if not win.winfo_exists():
                return
            app._mark_world_dirty(True)
            progress_wrap.pack_forget()
            app.log(tr("{title_mode}完成：{item_id}（待儲存）").format(title_mode=title_mode, item_id=item_id), "SUCCESS")
            app._refresh_world_lists()
            win.destroy()

        threading.Thread(target=_worker, daemon=True).start()

    progress_wrap = ttk.Frame(foot)
    save_progress_var = tk.StringVar(value="")
    save_progress = ttk.Progressbar(progress_wrap, orient="horizontal", mode="determinate")
    save_progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(progress_wrap, textvariable=save_progress_var).pack(side=tk.LEFT, padx=(8, 0))
    save_btn = ttk.Button(foot, text=tr("完成"), command=save_item)
    save_btn.pack(side=tk.RIGHT, padx=4)
    cancel_btn = ttk.Button(foot, text=tr("取消"), command=win.destroy)
    cancel_btn.pack(side=tk.RIGHT, padx=4)
