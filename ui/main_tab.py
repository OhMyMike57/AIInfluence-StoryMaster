from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from services.settings_service import sort_display_options
from ui.theme import labeled_frame
from widgets.summary_card import SummaryCard
from widgets.conversation_history_page import ConversationHistoryPage
from widgets.memory_page import MemoryPage
from widgets.observations_page import ObservationsPage
from widgets.json_preview import JsonPreview
from widgets.owned_items_viewer import OwnedItemsViewer
from widgets.recent_events_viewer import RecentEventsViewer
from widgets.game_status_banner import GameStatusBanner
from widgets.popover_menu import attach_menu
from i18n import tr
from ui.theme import tcol


def build_main_tab(app, notebook: ttk.Notebook) -> None:
    main_tab = ttk.Frame(notebook)
    notebook.add(main_tab, text=tr("📋 主工作區"))

    # ── Campaign header ───────────────────────────────────────────────────
    campaign_frame = labeled_frame(main_tab, text=tr("戰役設定"))
    campaign_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

    camp_row = ttk.Frame(campaign_frame)
    camp_row.pack(fill=tk.X, padx=8, pady=(2, 8))
    ttk.Label(camp_row, text=tr("當前戰役:"), font=("", 10, "bold")).pack(side=tk.LEFT)
    app.campaign_combo = ttk.Combobox(camp_row, state="readonly", width=30)
    app.campaign_combo.pack(side=tk.LEFT, padx=(8, 6))
    app.campaign_combo.bind("<<ComboboxSelected>>", lambda e: app._on_campaign_change())

    # Rename campaign display-name (icon-only, compact). The game↔tool campaign
    # match indicator now lives in the game-status banner (see GameStatusBanner).
    ttk.Button(camp_row, text="✏", width=3, command=app._rename_campaign,
               style="secondary.TButton").pack(side=tk.LEFT, padx=(0, 2))
    ttk.Label(camp_row, text="｜", foreground=tcol("#AAAAAA")).pack(side=tk.LEFT, padx=2)
    ttk.Button(camp_row, text=tr("🔄 重新載入"), command=app.refresh, style="info.TButton").pack(side=tk.LEFT, padx=2)
    # (ProemConfig-era「載入名詞」manual-import button removed in v0.29.0 — the
    #  Story Master companion mod now supplies terminology automatically.)
    ttk.Button(camp_row, text=tr("💾 備份戰役"), command=app.backup_campaign, style="info.TButton").pack(side=tk.LEFT, padx=2)
    # 開啟檔案 ▾ — dropdown (tool's own popover-menu framework) for opening the
    # backup root or the game's AIInfluence/save_data folder.
    open_btn = ttk.Button(camp_row, text=tr("📂 開啟檔案 ▾"), style="info.TButton")
    open_btn.pack(side=tk.LEFT, padx=2)
    attach_menu(open_btn, [
        (tr("開啟備份主目錄"), app.open_backup_dir),
        (tr("開啟戰役主目錄"), app.open_save_data_dir),
    ], direction="down")

    # ── Global staging bar (v0.36) ────────────────────────────────────────
    # Replaces the old「已選擇 X 位角色」status label: shows the pending-file
    # count with 儲存/取消 when the main workspace has staged (unsaved) edits.
    # Children are packed/hidden dynamically by app._staging_refresh_ui().
    staging_bar = ttk.Frame(camp_row)
    staging_bar.pack(side=tk.RIGHT, padx=10)
    app._staging_var = tk.StringVar(value="")
    app._staging_label = ttk.Label(staging_bar, textvariable=app._staging_var,
                                   foreground=tcol("#B26B00"),
                                   font=("Microsoft JhengHei", 10, "bold"))
    app._staging_save_btn = ttk.Button(staging_bar, text=tr("💾 儲存"),
                                       style="success.TButton",
                                       command=app._staging_commit_all)
    app._staging_discard_btn = ttk.Button(staging_bar, text=tr("↩ 取消"),
                                          style="secondary.TButton",
                                          command=app._staging_discard_all)

    # ── Game-status banner (G3) ───────────────────────────────────────────
    app.game_status_banner = GameStatusBanner(main_tab)
    app.game_status_banner.pack(fill=tk.X, padx=8, pady=(0, 2))

    # ── Workflow bar ──────────────────────────────────────────────────────
    wf_frame = ttk.Frame(main_tab)
    wf_frame.pack(fill=tk.X, padx=8, pady=(0, 6))
    ttk.Label(wf_frame, text=tr("Step 1 選角色"), foreground=tcol("#7B5B2E")).pack(side=tk.LEFT, padx=6)
    ttk.Label(wf_frame, text="→").pack(side=tk.LEFT, padx=2)
    ttk.Label(wf_frame, text=tr("Step 2 選操作對象"), foreground=tcol("#7B5B2E")).pack(side=tk.LEFT, padx=6)
    ttk.Label(wf_frame, text="→").pack(side=tk.LEFT, padx=2)
    ttk.Label(wf_frame, text=tr("Step 3 執行工具"), foreground=tcol("#7B5B2E")).pack(side=tk.LEFT, padx=6)

    # ── Main content area ─────────────────────────────────────────────────
    main_content = ttk.Frame(main_tab)
    main_content.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    # ── Red 1: Character list (left) ──────────────────────────────────────
    char_frame = labeled_frame(main_content, text=tr("🎭 角色清單"))
    char_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 4))
    char_frame.configure(width=320)

    # Two-level faction → clan filter (companion-mod data). Above 群組 per request.
    faction_row = ttk.Frame(char_frame)
    faction_row.pack(fill=tk.X, padx=6, pady=(4, 0))
    ttk.Label(faction_row, text=tr("陣營")).pack(side=tk.LEFT)
    app._faction_var = tk.StringVar(value=tr("全部陣營"))
    app._faction_combo = ttk.Combobox(faction_row, textvariable=app._faction_var,
                                       values=[tr("全部陣營")], state="readonly", width=9)
    app._faction_combo.pack(side=tk.LEFT, padx=(2, 4))
    app._faction_combo.bind("<<ComboboxSelected>>", lambda e: app._on_faction_filter_change())
    ttk.Label(faction_row, text=tr("氏族")).pack(side=tk.LEFT)
    app._clan_var = tk.StringVar(value=tr("全部氏族"))
    app._clan_combo = ttk.Combobox(faction_row, textvariable=app._clan_var,
                                    values=[tr("全部氏族")], state="readonly", width=9)
    app._clan_combo.pack(side=tk.LEFT, padx=(2, 4))
    app._clan_combo.bind("<<ComboboxSelected>>", lambda e: app._on_clan_filter_change())
    ttk.Button(faction_row, text="✕", width=2,
               command=app._reset_faction_clan_filter, style="secondary.TButton").pack(side=tk.LEFT)

    # Preset toolbar
    preset_row = ttk.Frame(char_frame)
    preset_row.pack(fill=tk.X, padx=6, pady=(2, 2))
    ttk.Label(preset_row, text=tr("群組:")).pack(side=tk.LEFT)
    app.preset_combo = ttk.Combobox(preset_row, width=12, state="readonly")
    app.preset_combo.pack(side=tk.LEFT, padx=(4, 4))
    ttk.Button(preset_row, text=tr("載入"), command=app._load_preset, style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(preset_row, text=tr("保存"), command=app._save_preset, style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(preset_row, text=tr("刪除"), command=app._delete_preset, style="danger.TButton").pack(side=tk.LEFT, padx=1)

    # Search bar
    filter_row = ttk.Frame(char_frame)
    filter_row.pack(fill=tk.X, padx=6, pady=(0, 2))
    ttk.Label(filter_row, text="🔍").pack(side=tk.LEFT)
    filter_entry = ttk.Entry(filter_row, textvariable=app.filter_var)
    filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
    filter_entry.bind("<KeyRelease>", lambda e: app._debounce_rebuild_list())

    # Sort controls
    sort_row = ttk.Frame(char_frame)
    sort_row.pack(fill=tk.X, padx=6, pady=(0, 2))
    ttk.Label(sort_row, text=tr("排序:")).pack(side=tk.LEFT)
    app.sort_combo = ttk.Combobox(
        sort_row, values=sort_display_options(),
        textvariable=app.main_sort_var, state="readonly", width=8,
    )
    app.sort_combo.pack(side=tk.LEFT, padx=(4, 4))
    app.sort_combo.bind("<<ComboboxSelected>>", lambda e: app._rebuild_list())
    ttk.Checkbutton(sort_row, text=tr("反轉"), variable=app.main_sort_reverse_var,
                    command=app._rebuild_list).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Checkbutton(sort_row, text=tr("僅互動"), variable=app.exclude_uninteracted_var,
                    command=app._rebuild_list).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Checkbutton(sort_row, text=tr("僅隊伍"), variable=app.party_only_var,
                    command=app._rebuild_list).pack(side=tk.LEFT)

    # Role display toggles — uncheck to hide that role (參考摘要卡的區塊顯示)
    type_row = ttk.Frame(char_frame)
    type_row.pack(fill=tk.X, padx=6, pady=(0, 2))
    ttk.Label(type_row, text=tr("顯示:")).pack(side=tk.LEFT)
    for _txt, _var in ((tr("貴族"), app.type_lord_var),
                       (tr("浪人"), app.type_wanderer_var),
                       (tr("顯要"), app.type_notable_var),
                       (tr("領袖"), app.type_leader_var)):
        ttk.Checkbutton(type_row, text=_txt, variable=_var,
                        command=app._rebuild_list).pack(side=tk.LEFT, padx=(0, 2))

    # Quick select buttons
    quick_row = ttk.Frame(char_frame)
    quick_row.pack(fill=tk.X, padx=6, pady=(0, 4))
    ttk.Button(quick_row, text=tr("✓全選"), command=app._select_all_visible, style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    ttk.Button(quick_row, text=tr("✗清除"), command=app._select_none_visible, style="secondary.TButton").pack(side=tk.LEFT, padx=1)
    # 載入群聊 — detect group-chat participants, curate, replace+lock selection.
    ttk.Button(quick_row, text=tr("👥 載入群聊"), command=app._load_group_chat,
               style="info.TButton").pack(side=tk.RIGHT, padx=1)

    # Character Listbox (MULTIPLE = click toggles, no Ctrl/Shift needed)
    char_list_frame = ttk.Frame(char_frame)
    char_list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 2))
    app.char_list = tk.Listbox(char_list_frame, selectmode=tk.MULTIPLE, exportselection=False, activestyle="dotbox")
    char_vsb = ttk.Scrollbar(char_list_frame, orient="vertical", command=app.char_list.yview)
    app.char_list.configure(yscrollcommand=char_vsb.set)
    app.char_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    char_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    app.char_list.bind("<<ListboxSelect>>", app._on_char_list_select)
    app.char_list.bind("<Button-3>", app._on_char_list_right_click)

    # Batch operations (bottom of left panel)
    tools_frame = labeled_frame(char_frame, text=tr("🛠️ 批量操作"))
    tools_frame.pack(fill=tk.X, padx=0, pady=(2, 4))

    # The operation target is now indicated directly in the 已選角色 list, so the
    # dedicated 操作對象 label was removed. Keep the StringVar (written elsewhere
    # via hasattr-guards) so target tracking stays intact without rendering it.
    app.current_target_var = tk.StringVar(value=tr("（請先在左側選取角色）"))

    btn_grid = ttk.Frame(tools_frame)
    btn_grid.pack(fill=tk.X, padx=8, pady=(6, 8))
    buttons_data = [
        (tr("📝 同步對話"), app.sync_dialogue),
        (tr("✍ 寫入劇情"), app.insert_plot),
        (tr("✅ 驗證檔案"), app.validate_json),
        (tr("♻ 重置角色"), app.reset_character),
        (tr("🔄 清空回應"), app.quick_reset),
        (tr("🚑 移除疾病"), app.bulk_clear_diseases),
    ]
    for i, (text, cmd) in enumerate(buttons_data):
        ttk.Button(btn_grid, text=text, command=cmd, style="warning.TButton").grid(
            row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew",
        )
    btn_grid.columnconfigure(0, weight=1)
    btn_grid.columnconfigure(1, weight=1)

    # ── Blue 2: Selected characters list (middle) ─────────────────────────
    sel_frame = labeled_frame(main_content, text=tr("✅ 已選角色"))
    sel_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 4))
    sel_frame.configure(width=200)

    # ── Lock toolbar ──────────────────────────────────────────────────────
    sel_lock_bar = ttk.Frame(sel_frame)
    sel_lock_bar.pack(fill=tk.X, padx=6, pady=(2, 0))
    ttk.Button(sel_lock_bar, text=tr("🔒 全鎖"), command=app._lock_all_selected,
               style="secondary.TButton").pack(side=tk.LEFT, padx=(0, 2))
    ttk.Button(sel_lock_bar, text=tr("🔓 全解"), command=app._unlock_all_selected,
               style="secondary.TButton").pack(side=tk.LEFT)

    sel_list_frame = ttk.Frame(sel_frame)
    sel_list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 6))
    app.selected_listbox = tk.Listbox(sel_list_frame, exportselection=False, activestyle="dotbox")
    sel_vsb = ttk.Scrollbar(sel_list_frame, orient="vertical", command=app.selected_listbox.yview)
    app.selected_listbox.configure(yscrollcommand=sel_vsb.set)
    app.selected_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sel_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    # Use <Button-1> + nearest() instead of <<ListboxSelect>> + curselection().
    # <<ListboxSelect>> can fire with stale curselection when the listbox is
    # programmatically rebuilt, causing the wrong character to be selected.
    app.selected_listbox.bind("<Button-1>", app._on_selected_list_click)
    app.selected_listbox.bind("<Button-3>", app._on_selected_list_right_click)
    # During click-drag, tkinter's Listbox natively highlights rows under the
    # cursor in the selection colour.  Since we manage all highlighting ourselves
    # via itemconfig, suppress this by clearing native selection on every motion
    # and on button-release.
    _slb = app.selected_listbox
    _slb.bind("<B1-Motion>",       lambda e: _slb.selection_clear(0, tk.END))
    _slb.bind("<ButtonRelease-1>", lambda e: _slb.selection_clear(0, tk.END))

    # ── Right panel: detail tabs only ─────────────────────────────────────
    right_panel = ttk.Frame(main_content)
    right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    app.detail_notebook = ttk.Notebook(right_panel)
    app.detail_notebook.pack(fill=tk.BOTH, expand=True)

    tab_summary  = ttk.Frame(app.detail_notebook)
    tab_conv     = ttk.Frame(app.detail_notebook)
    tab_recent   = ttk.Frame(app.detail_notebook)
    tab_info     = ttk.Frame(app.detail_notebook)
    tab_secrets  = ttk.Frame(app.detail_notebook)
    tab_events   = ttk.Frame(app.detail_notebook)
    tab_json     = ttk.Frame(app.detail_notebook)
    tab_log      = ttk.Frame(app.detail_notebook)
    app.detail_notebook.add(tab_summary, text=tr("📋 摘要"))
    app.detail_notebook.add(tab_conv,    text=tr("💬 對話"))
    app.detail_notebook.add(tab_recent,  text=tr("🗂 近期"))
    app.detail_notebook.add(tab_info,    text=tr("📖 訊息"))
    app.detail_notebook.add(tab_secrets, text=tr("🔒 秘密"))
    app.detail_notebook.add(tab_events,  text=tr("🎭 事件"))
    app.detail_notebook.add(tab_json,    text=tr("{ } JSON"))
    app.detail_notebook.add(tab_log,     text=tr("📝 記錄"))

    app.summary_card = SummaryCard(
        tab_summary,
        on_field_save=app._summary_field_save,
        on_quick_clear=app._summary_quick_clear,
        on_attr_edit=app._summary_attr_edit,
        resolve_character_name=app._resolve_char_name_by_sid,
        on_persona_edit=app._persona_open_editor,
        on_persona_export=app._persona_export,
        on_persona_import=app._persona_import,
        edit_variable=app.edit_mode_var,
    )
    app.summary_card.pack(fill=tk.BOTH, expand=True)

    # 對話 hosts everything derived from what this character said and heard:
    # the history itself, the observation log behind it, and the memories the
    # game distilled from it.
    conv_nb = ttk.Notebook(tab_conv)
    conv_nb.pack(fill=tk.BOTH, expand=True)
    sub_history = ttk.Frame(conv_nb)
    sub_observe = ttk.Frame(conv_nb)
    sub_memory  = ttk.Frame(conv_nb)
    conv_nb.add(sub_history, text=tr("💬 對話歷史"))
    conv_nb.add(sub_observe, text=tr("👂 對話觀察"))
    conv_nb.add(sub_memory,  text=tr("📖 記憶之書"))

    app.conversation_viewer = ConversationHistoryPage(
        sub_history,
        on_delete=app._conv_edit_delete,
        on_sync_menu=app._conv_edit_sync_menu,
        on_sync_all=app._conv_edit_sync_all,
        on_insert=app._conv_edit_insert,
        on_edit_line=app._conv_edit_apply_line,
        on_replace_all=app._conv_edit_replace_all,
        on_patch_lines=app._conv_edit_patch_lines,
        on_view_eavesdroppers=app._conv_view_eavesdroppers,
        on_view_sharers=app._conv_view_sharers,
        on_clear_eavesdroppers=app._conv_clear_eavesdroppers,
        edit_variable=app.edit_mode_var,
        app=app,
    )
    app.conversation_viewer.pack(fill=tk.BOTH, expand=True)

    app.observations_page = ObservationsPage(
        sub_observe,
        on_delete=app._observation_delete,
        edit_variable=app.edit_mode_var,
        resolve_name=app._resolve_char_name_by_sid,
    )
    app.observations_page.pack(fill=tk.BOTH, expand=True)

    app.memory_page = MemoryPage(
        sub_memory,
        on_entry_save=app._memory_entry_save,
        on_entry_delete=app._memory_entry_delete,
        edit_variable=app.edit_mode_var,
        resolve_name=app._resolve_char_name_by_sid,
    )
    app.memory_page.pack(fill=tk.BOTH, expand=True)

    app.json_preview = JsonPreview(
        tab_json,
        on_save=app._json_edit_save,
        on_revert=app._json_edit_revert,
        edit_variable=app.edit_mode_var,
    )
    app.json_preview.pack(fill=tk.BOTH, expand=True)

    # Log tab (replaces quick_log panel)
    log_toolbar = ttk.Frame(tab_log)
    log_toolbar.pack(fill=tk.X, padx=6, pady=4)
    ttk.Button(log_toolbar, text=tr("清除"), command=app.clear_quick_log, style="secondary.TButton").pack(side=tk.LEFT)
    ttk.Label(log_toolbar, text=tr("(最近10條)")).pack(side=tk.LEFT, padx=8)

    log_container = ttk.Frame(tab_log)
    log_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
    app.quick_log_text = tk.Text(log_container, wrap="word", height=6, state="disabled")
    app.quick_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    quick_log_scroll = ttk.Scrollbar(log_container, command=app.quick_log_text.yview)
    quick_log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    app.quick_log_text.configure(yscrollcommand=quick_log_scroll.set)

    # ── 近期事件 tab ──────────────────────────────────────────────────────
    app.recent_events_viewer = RecentEventsViewer(
        tab_recent,
        on_delete=app._recent_event_delete,
        on_clear=app._recent_event_clear,
        edit_variable=app.edit_mode_var,
    )
    app.recent_events_viewer.pack(fill=tk.BOTH, expand=True)

    # ── 擁有訊息 tab ──────────────────────────────────────────────────────
    app.owned_info_viewer = OwnedItemsViewer(
        tab_info,
        kind="info",
        kind_label=tr("訊息"),
        on_stage_add    = app._owned_stage_add,
        on_stage_remove = app._owned_stage_remove,
        get_pending     = app._owned_get_pending,
        edit_variable   = app.edit_mode_var,
    )
    app.owned_info_viewer.pack(fill=tk.BOTH, expand=True)

    # ── 擁有秘密 tab ──────────────────────────────────────────────────────
    app.owned_secrets_viewer = OwnedItemsViewer(
        tab_secrets,
        kind="secrets",
        kind_label=tr("秘密"),
        on_stage_add    = app._owned_stage_add,
        on_stage_remove = app._owned_stage_remove,
        get_pending     = app._owned_get_pending,
        edit_variable   = app.edit_mode_var,
    )
    app.owned_secrets_viewer.pack(fill=tk.BOTH, expand=True)

    # ── 世界事件 tab ──────────────────────────────────────────────────────
    app.owned_events_viewer = OwnedItemsViewer(
        tab_events,
        kind="dynamic_events",
        kind_label=tr("事件"),
        on_stage_add    = app._owned_stage_add,
        on_stage_remove = app._owned_stage_remove,
        get_pending     = app._owned_get_pending,
        edit_variable   = app.edit_mode_var,
    )
    app.owned_events_viewer.pack(fill=tk.BOTH, expand=True)
