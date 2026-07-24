from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from services.settings_service import sort_display_options
from ui.theme import labeled_frame
from widgets.world_item_summary import WorldItemSummary
from i18n import tr
from ui.theme import tcol


def build_world_tab(app, notebook: ttk.Notebook) -> None:
    info_tab = ttk.Frame(notebook)
    notebook.add(info_tab, text=tr("🧠 訊息與秘密"))

    info_root = ttk.Frame(info_tab)
    info_root.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # ── Top toolbar ───────────────────────────────────────────────────────
    info_topbar = ttk.Frame(info_root)
    info_topbar.pack(fill=tk.X, pady=(0, 6))

    # LEFT cluster: edit mode + reload + validity check  (matches Dynamic Events tab)
    ttk.Checkbutton(
        info_topbar, text=tr("編輯模式"),
        variable=app.world_edit_mode_var, command=app._apply_world_edit_mode,
    ).pack(side=tk.LEFT)
    ttk.Button(
        info_topbar, text=tr("🔄 重新載入"),
        command=app.cancel_world_changes,
        style="info.TButton",
    ).pack(side=tk.LEFT, padx=(8, 2))
    ttk.Button(
        info_topbar, text=tr("🔍 有效檢查"),
        command=app.validate_world_files,
        style="info.TButton",
    ).pack(side=tk.LEFT, padx=2)

    # RIGHT cluster: dirty indicator + 取消 / 儲存, laid out left→right inside a
    # dedicated sub-frame so the order is stable (status · 取消 · 儲存 — cancel
    # left, confirm right, per the tool-wide button convention).
    save_cluster = ttk.Frame(info_topbar)
    save_cluster.pack(side=tk.RIGHT, padx=10)
    app.world_dirty_var = tk.StringVar(value="")
    ttk.Label(save_cluster, textvariable=app.world_dirty_var,
              foreground=tcol("#b36b00")).pack(side=tk.LEFT, padx=(0, 8))
    # 取消/儲存: shown only when there are unsaved changes (see
    # _refresh_world_save_buttons, driven by _mark_world_dirty).
    app.btn_world_cancel = ttk.Button(save_cluster, text=tr("↩ 取消"),
                                      command=app.cancel_world_changes, style="secondary.TButton")
    app.btn_world_save = ttk.Button(save_cluster, text=tr("💾 儲存"),
                                    command=app.save_world_changes, style="success.TButton")
    app._world_save_pack = dict(side=tk.LEFT, padx=2)
    if hasattr(app, "_refresh_world_save_buttons"):
        app._refresh_world_save_buttons()

    # Sort-toggle is no longer a separate widget — folded into edit mode.
    # Keep attribute for backward compatibility with code that checks it.
    app.world_sort_toggle = None

    # ── Three columns (draggable) ─────────────────────────────────────────
    # Panedwindow so the user can drag the sashes (e.g. widen the lists for long
    # English titles / NPC names).  Initial split is 3:4:3 (30/40/30):
    # Panedwindow ``weight`` only distributes *extra* space, so we set the sash
    # positions once the pane first has a real width, then leave them adjustable.
    panes = ttk.Panedwindow(info_root, orient=tk.HORIZONTAL)
    panes.pack(fill=tk.BOTH, expand=True)

    left_col = ttk.Frame(panes)
    right_col = ttk.Frame(panes)
    panes.add(left_col, weight=1)
    panes.add(right_col, weight=1)

    # ── Info list ─────────────────────────────────────────────────────────
    info_box = labeled_frame(left_col, text=tr("公開訊息 world_info.json"))
    info_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    info_filter_row = ttk.Frame(info_box)
    info_filter_row.pack(fill=tk.X, padx=6, pady=(4, 2))
    ttk.Label(info_filter_row, text="🔍").pack(side=tk.LEFT)
    app.world_info_filter_var = tk.StringVar(value="")
    ttk.Entry(info_filter_row, textvariable=app.world_info_filter_var).pack(
        side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0)
    )
    app.world_info_filter_var.trace_add("write", lambda *_: app._refresh_world_lists())

    info_tools = ttk.Frame(info_box)
    info_tools.pack(fill=tk.X, padx=6, pady=(0, 4))
    btn_info_new = ttk.Button(info_tools, text=tr("新增"), command=lambda: app.create_world_item("info"), style="secondary.TButton")
    btn_info_new.pack(side=tk.LEFT, padx=2)
    app.world_edit_buttons.append(btn_info_new)
    btn_info_edit = ttk.Button(info_tools, text=tr("編輯"), command=lambda: app.edit_world_item("info"), style="secondary.TButton")
    btn_info_edit.pack(side=tk.LEFT, padx=2)
    app.world_edit_buttons.append(btn_info_edit)
    btn_info_del = ttk.Button(info_tools, text=tr("移除"), command=lambda: app.delete_world_item("info"), style="danger.TButton")
    btn_info_del.pack(side=tk.LEFT, padx=2)
    app.world_edit_buttons.append(btn_info_del)

    app.info_list = tk.Listbox(info_box, exportselection=False)
    app.info_list.pack(fill=tk.BOTH, expand=True, padx=6)
    app.info_list.bind("<<ListboxSelect>>", lambda e: app._on_world_item_select("info"))
    app.info_move_frame = ttk.Frame(info_box)
    app.info_move_frame.pack(fill=tk.X, padx=6, pady=(4, 6))
    ttk.Button(app.info_move_frame, text="↑↑", command=lambda: app._move_world_item("info", -10), style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(app.info_move_frame, text="↑", command=lambda: app._move_world_item("info", -1), style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(app.info_move_frame, text="↓", command=lambda: app._move_world_item("info", 1), style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(app.info_move_frame, text="↓↓", command=lambda: app._move_world_item("info", 10), style="secondary.TButton").pack(side=tk.LEFT, padx=1)

    # ── Secrets list ──────────────────────────────────────────────────────
    sec_box = labeled_frame(left_col, text=tr("秘密 world_secrets.json"))
    sec_box.pack(fill=tk.BOTH, expand=True)

    sec_filter_row = ttk.Frame(sec_box)
    sec_filter_row.pack(fill=tk.X, padx=6, pady=(4, 2))
    ttk.Label(sec_filter_row, text="🔍").pack(side=tk.LEFT)
    app.world_secret_filter_var = tk.StringVar(value="")
    ttk.Entry(sec_filter_row, textvariable=app.world_secret_filter_var).pack(
        side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0)
    )
    app.world_secret_filter_var.trace_add("write", lambda *_: app._refresh_world_lists())

    sec_tools = ttk.Frame(sec_box)
    sec_tools.pack(fill=tk.X, padx=6, pady=(0, 4))
    btn_sec_new = ttk.Button(sec_tools, text=tr("新增"), command=lambda: app.create_world_item("secret"), style="secondary.TButton")
    btn_sec_new.pack(side=tk.LEFT, padx=2)
    app.world_edit_buttons.append(btn_sec_new)
    btn_sec_edit = ttk.Button(sec_tools, text=tr("編輯"), command=lambda: app.edit_world_item("secret"), style="secondary.TButton")
    btn_sec_edit.pack(side=tk.LEFT, padx=2)
    app.world_edit_buttons.append(btn_sec_edit)
    btn_sec_del = ttk.Button(sec_tools, text=tr("移除"), command=lambda: app.delete_world_item("secret"), style="danger.TButton")
    btn_sec_del.pack(side=tk.LEFT, padx=2)
    app.world_edit_buttons.append(btn_sec_del)

    app.secret_list = tk.Listbox(sec_box, exportselection=False)
    app.secret_list.pack(fill=tk.BOTH, expand=True, padx=6)
    app.secret_list.bind("<<ListboxSelect>>", lambda e: app._on_world_item_select("secret"))
    app.secret_move_frame = ttk.Frame(sec_box)
    app.secret_move_frame.pack(fill=tk.X, padx=6, pady=(4, 6))
    ttk.Button(app.secret_move_frame, text="↑↑", command=lambda: app._move_world_item("secret", -10), style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(app.secret_move_frame, text="↑", command=lambda: app._move_world_item("secret", -1), style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(app.secret_move_frame, text="↓", command=lambda: app._move_world_item("secret", 1), style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(app.secret_move_frame, text="↓↓", command=lambda: app._move_world_item("secret", 10), style="secondary.TButton").pack(side=tk.LEFT, padx=1)

    # ── Preview panes ─────────────────────────────────────────────────────
    # Read-only summary cards (屬性 + 內文) — editing happens through the
    # 新增/編輯 dialog.  The two boxes share the column height equally.
    right_col.columnconfigure(0, weight=1)
    right_col.rowconfigure(0, weight=1, uniform="prev")
    right_col.rowconfigure(1, weight=1, uniform="prev")

    preview_info_box = labeled_frame(right_col, text=tr("公開訊息預覽"))
    preview_info_box.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
    app.world_info_preview = WorldItemSummary(preview_info_box)
    app.world_info_preview.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    preview_sec_box = labeled_frame(right_col, text=tr("秘密預覽"))
    preview_sec_box.grid(row=1, column=0, sticky="nsew")
    app.world_secret_preview = WorldItemSummary(preview_sec_box)
    app.world_secret_preview.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    # ── Owner column ──────────────────────────────────────────────────────
    owner_col = ttk.Frame(panes)
    panes.add(owner_col, weight=1)

    # Set the initial 3:4:3 (30% / 40% / 30%) sash positions once the pane has a
    # real width, then leave them user-draggable (the flag prevents re-snapping
    # on later resizes).
    app._world_sash_init = False

    def _init_world_sash(_event=None):
        if app._world_sash_init:
            return
        w = panes.winfo_width()
        if w <= 1:
            return
        app._world_sash_init = True
        try:
            panes.sashpos(0, (w * 3) // 10)   # 30%
            panes.sashpos(1, (w * 7) // 10)   # 70%  → 30/40/30
        except Exception:
            pass

    panes.bind("<Configure>", _init_world_sash)
    panes.after(80, _init_world_sash)

    owner_box = labeled_frame(owner_col, text=tr("擁有者"))
    owner_box.pack(fill=tk.BOTH, expand=True)

    top_line = ttk.Frame(owner_box)
    top_line.pack(fill=tk.X, padx=6, pady=(4, 2))
    ttk.Label(top_line, text=tr("排序")).pack(side=tk.LEFT)
    app.owner_sort_var = tk.StringVar(value=app.main_sort_var.get())
    app.owner_sort_combo = ttk.Combobox(
        top_line, width=10, textvariable=app.owner_sort_var,
        values=sort_display_options(), state="readonly",
    )
    app.owner_sort_combo.pack(side=tk.LEFT, padx=4)
    app.owner_sort_combo.bind("<<ComboboxSelected>>", lambda e: app._refresh_owned_lists())

    app.btn_owner_remove = ttk.Button(top_line, text=tr("移除"), command=app.remove_owner_from_selected_item, style="danger.TButton")
    app.btn_owner_remove.pack(side=tk.RIGHT, padx=(4, 0))
    app.btn_owner_clear = ttk.Button(top_line, text=tr("清空"), command=app.clear_owners_from_selected_item, style="danger.TButton")
    app.btn_owner_clear.pack(side=tk.RIGHT, padx=(4, 0))

    source_line = ttk.Frame(owner_box)
    source_line.pack(fill=tk.X, padx=6, pady=(0, 2))
    app.owner_source_var = tk.StringVar(value=tr("清單來源：未選擇"))
    ttk.Label(source_line, textvariable=app.owner_source_var).pack(side=tk.LEFT)

    clone_line = ttk.Frame(owner_box)
    clone_line.pack(fill=tk.X, padx=6, pady=(0, 4))
    app.owner_clone_source_var = tk.StringVar(value=tr("仿製來源：未設定"))
    ttk.Label(clone_line, textvariable=app.owner_clone_source_var).pack(side=tk.LEFT)

    action_line = ttk.Frame(owner_box)
    action_line.pack(fill=tk.X, padx=6, pady=(0, 4))
    app.btn_owner_clone = ttk.Button(action_line, text=tr("仿製清單"), command=app.clone_owner_list_from_selected_item, style="secondary.TButton")
    app.btn_owner_clone.pack(side=tk.LEFT)
    app.btn_owner_apply_clone = ttk.Button(action_line, text=tr("套用清單"), command=app.apply_cloned_owner_list_to_selected_item, style="warning.TButton")
    app.btn_owner_apply_clone.pack(side=tk.LEFT, padx=(6, 0))

    app.world_owner_list = tk.Listbox(owner_box, exportselection=False, selectmode=tk.EXTENDED)
    app.world_owner_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    app.world_edit_buttons.extend([
        app.btn_owner_remove, app.btn_owner_clear,
        app.btn_owner_clone, app.btn_owner_apply_clone,
        app.btn_world_save, app.btn_world_cancel,
    ])
    app.world_edit_buttons = [b for b in app.world_edit_buttons if b is not None]
