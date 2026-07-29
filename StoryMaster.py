from __future__ import annotations
import json
import os
import tkinter.font as _tkfont
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import threading

from services.json_utils import (
    entry_speaker,
    entry_hash,
    safe_load_json,
    safe_write_json,
    load_json_file as load_presets,
    save_json_file as save_presets,
    append_conversation_entries,
    convert_line_perspective,
    speaker_color,
)
from services.path_service import (
    find_save_data,
    find_proemconfig_exports_dir,
)
import services.app_paths as app_paths
from services.game_status_service import (
    check_game_status as svc_check_game_status,
    detect_bannerlord_running as svc_detect_bannerlord_running,
)
from services.validation_service import (
    validate_character_files,
    validate_world_files as svc_validate_world_files,
    validate_world_items_content as svc_validate_world_items_content,
    find_orphan_world_refs as svc_find_orphan_world_refs,
)
from services.settings_service import (
    AVAILABLE_LANGUAGES,
    AVAILABLE_THEMES,
    SortKey,
    build_settings,
    detect_default_language,
    normalize_default_sort,
    save_json_dict,
    sort_key_from_label,
    sort_label,
)
from i18n import set_lang, tr
from services.backup_service import (
    backup_campaign_dir,
    backup_snapshots,
    backup_tool_config,
)
from services.world_service import (
    world_paths_for_app,
    load_world_items,
    dump_world_items,
    clone_items,
    move_item as svc_move_item,
    build_owner_index_from_characters,
    owners_for_item,
    reverse_owner_maps,
    dynamic_events_path_for_app,
    load_dynamic_events,
    economic_effects_path_for_app,
    load_economic_effects,
    disease_paths_for_app,
    load_disease_data,
    dump_disease_instances,
)
from services.disease_service import (
    instances_for_hero,
    remove_hero_disease as svc_remove_hero_disease,
    remove_disease_instance as svc_remove_disease_instance,
    remove_all_instances_of_disease as svc_remove_all_instances_of_disease,
    remove_disease_definition as svc_remove_disease_definition,
    instances_for_disease as svc_instances_for_disease,
    assign_hero_disease as svc_assign_hero_disease,
    sync_character_diseases as svc_sync_character_diseases,
    invalid_hero_instances,
    stale_disease_characters,
    disease_definition as svc_disease_def,
    hero_instances as svc_hero_instances,
)
from ui.disease_tab import build_disease_tab, refresh_disease_tab
from ui.dynamic_events_tab import build_dynamic_events_tab, refresh_dynamic_events_tab
from services.dynamic_event_service import (
    find_orphan_event_refs as svc_find_orphan_event_refs,
    clean_char_event_refs as svc_clean_char_event_refs,
    apply_event_edits as svc_apply_event_edits,
    write_dynamic_events as svc_write_dynamic_events,
    normalize_economic_effect as svc_normalize_eco_effect,
    new_event_template as svc_new_event_template,
    EDITABLE_EVENT_FIELDS as DYN_EDITABLE_FIELDS,
)
from services.diplomacy_service import (
    bundle_statements as svc_bundle_statements,
    statement_keys as svc_statement_keys,
    serialize_statement as svc_serialize_statement,
    apply_statement_changes as svc_apply_statement_changes,
    remove_events_cascade as svc_remove_events_cascade,
    write_bundle_update as svc_write_bundle_update,
    find_orphan_statements as svc_find_orphan_statements,
    find_unknown_kingdoms as svc_find_unknown_kingdoms,
    bundle_pressure as svc_bundle_pressure,
    replace_pressure as svc_replace_pressure,
)
from services.character_service import (
    build_characters_and_indexes,
    sorted_displays,
    display_label,
    is_visible_character,
    normalize_display_name,
    set_player_trust as svc_set_player_trust,
    set_player_romance as svc_set_player_romance,
    set_player_interaction as svc_set_player_interaction,
    pristine_character_template as svc_pristine_template,
    player_romance_level as svc_player_romance_level,
    player_trust_level as svc_player_trust_level,
    player_interaction_count as svc_player_interaction_count,
    is_never_interacted as svc_is_never_interacted,
)
from services import character_db_service as svc_chardb
from services import conversation_transfer as svc_transfer
from services import memory_service as svc_memory
from services import observation_service as svc_observation
from services import radiation_service as svc_radiation
from services import rag_service as svc_rag
from services import speaker_format as svc_speaker
from ui import preview_font
from services import snapshot_service as svc_snapshot
from services import group_chat_service as svc_group
from services import display_labels as svc_display
from services import persona_transfer as svc_persona
from services.staging_service import (
    queue_field_change as svc_queue_field_change,
    effective_data as svc_effective_data,
    build_diff_items as svc_build_diff_items,
    template_from_data as svc_template_from_data,
)
from services.doc_staging import DocStaging, list_delta as svc_list_delta

from services.terminology_service import (
    CAMPAIGN_CACHE_DIR_NAME as TERM_CAMPAIGN_CACHE_DIR_NAME,
    load_terminology_for as svc_load_terminology_for,
    load_fallback as svc_load_terminology_fallback,
    load_campaign_terminology as svc_load_campaign_terminology,
    load_storymaster_terminology as svc_load_storymaster_terminology,
    lookup_with_campaign as svc_lookup_with_campaign,
    resolve_character_name as svc_resolve_character_name_lib,
    merged_category as svc_merged_category,
    name_to_ids_index as svc_name_to_ids_index,
    resolve_name_or_id as svc_resolve_name_or_id,
    suggest_names as svc_suggest_names,
)

from services.world_owner_service import (
    remove_owners as svc_remove_owners,
    clear_owners as svc_clear_owners,
    clone_payload as svc_clone_payload,
    apply_clone as svc_apply_clone,
)
from controllers.campaign_controller import (
    list_campaigns as ctl_list_campaigns,
    choose_target_campaign as ctl_choose_target_campaign,
)
from controllers.world_controller import resolve_owner_context as ctl_resolve_owner_context
from controllers.main_workspace_controller import (
    build_selected_members_lines as ctl_build_selected_members_lines,
    resolve_character_name as ctl_resolve_character_name,
)
from controllers.selection_controller import (
    source_path_from_characters as ctl_source_path_from_characters,
)
from controllers.world_save_controller import (
    world_files_changed as ctl_world_files_changed,
    world_save_log_message as ctl_world_save_log_message,
)
from ui.world_editor_dialog import open_world_item_editor_dialog
from ui.about_tab import build_about_tab
from ui.world_tab import build_world_tab
from ui.log_tab import build_log_tab
from ui.backup_tab import build_backup_tab
from ui.settings_tab import build_settings_tab
from ui.main_tab import build_main_tab
from ui.database_tab import build_database_tab, refresh_database_tab
from widgets.game_status_banner import GameStatusBanner
from dialogs.plot_insert_dialog import open_plot_insert_dialog
from dialogs.field_picker_dialog import open_field_picker_dialog
from dialogs.field_editor_dialog import open_field_editor_dialog
from dialogs.diff_submit_dialog import open_diff_submit_dialog
from dialogs.sync_dialog import open_sync_dialog
from dialogs.trim_dialog import open_trim_dialog
from dialogs.reset_character_dialog import open_reset_character_dialog
import tkinter as tk
from tkinter import ttk, filedialog
from ui import msgbox as messagebox
import ttkbootstrap as ttk_boot
from ui.theme import tcol

APP_TITLE = "AI Influence: Story Master"

PRESET_FILE = "story_tools_presets.json"
FAVORITES_FILE = "story_tools_favorites.json"
LOG_FILE = "story_tools_log.txt"
TEMPLATES_FILE = "story_tools_templates.json"
NPC_GROUPS_FILE = "story_tools_npc_groups.json"
SETTINGS_FILE = "story_tools_settings.json"
CAMPAIGN_ALIASES_FILE = "story_tools_campaign_aliases.json"  # id → display name

# The player's hero is referenced as ``main_hero`` in dynamic_events but
# never has its own character JSON file.  Listing it here keeps the
# reverse validity check (and similar scans) from flagging it as dangling.
VIRTUAL_CHARACTER_SIDS: frozenset = frozenset({"main_hero"})
CONFIG_DIR_NAME = "config"
LOG_DIR_NAME = "logs"

EDITABLE_TEXT_FIELDS = [
    "CharacterDescription",
    "AIGeneratedPersonality",
    "AIGeneratedBackstory",
    "AIGeneratedSpeechQuirks",
    "AIGeneratedCognitiveStyle",
]

class AIInfluenceStoryToolsApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        # Default window: the workspace grew a lot (sub-tabbed 對話 page, list +
        # preview + action row), and 1400x850 left several panes cramped.  Ask
        # for more, but never more than the screen can show — a window taller
        # than the desktop hides its own bottom action rows.
        try:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        except tk.TclError:
            sw, sh = 1920, 1080
        root.geometry(f"{min(1680, int(sw * 0.92))}x{min(1000, int(sh * 0.90))}")
        root.minsize(1100, 700)

        # Slightly increase the default UI font size (Windows default is 9pt → 10pt)
        for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkTooltipFont"):
            try:
                f = _tkfont.nametofont(fname)
                current = f.cget("size")
                if abs(current) < 10:
                    f.configure(size=10)
            except Exception:
                pass

        # Read-only bundled assets (locales / companion_mod / docs); in a source
        # run this is the repo root, in a frozen build it is PyInstaller's bundle.
        self.script_dir = app_paths.resource_dir()
        # Folder the program runs from — used for game auto-detection / legacy
        # migration (walking up the filesystem, which the bundle dir can't do).
        self.app_base = app_paths.exe_dir()
        # Writable user data root (config / logs / cache / backups). Default
        # %APPDATA%\AIInfluenceStoryTools for a shipped EXE; repo root in dev;
        # user-overridable from Settings (pointer file).
        self.data_dir = app_paths.ensure_data_dir()
        self.save_data_dir: Optional[Path] = None
        self.campaign_dir: Optional[Path] = None

        self.characters: List[Tuple[str, Path]] = []
        self.plain_to_path: Dict[str, Path] = {}
        self.path_to_plain: Dict[Path, str] = {}
        self.selected_displays: Set[str] = set()
        self._locked_displays: Set[str] = set()   # locked characters stay selected regardless of filter/group
        # Campaign-wide eavesdropper index (utterance_id → listeners), cached and
        # rebuilt only when a DialogueObservations changes (clean / obs-delete /
        # reset / campaign switch) — ordinary CH edits never affect it.
        self._eaves_index: Optional[Dict[str, Any]] = None
        self._eaves_index_camp: Optional[str] = None
        self._list_rebuilding: bool = False        # guard: suppress _on_char_list_select during _rebuild_list
        self._char_display_list: List[str] = []
        self.character_meta: Dict[str, Dict[str, Any]] = {}
        self.known_info_owners: Dict[str, List[str]] = {}
        self.known_secret_owners: Dict[str, List[str]] = {}
        self.filter_var = tk.StringVar(value="")
        self.main_sort_var = tk.StringVar(value=sort_label(SortKey.FAVORITES))  # display label; canonical stored in settings
        self.main_sort_reverse_var = tk.BooleanVar(value=False)
        self.exclude_uninteracted_var = tk.BooleanVar(value=False)
        self.party_only_var = tk.BooleanVar(value=False)
        # Role display toggles (default all shown) + two-level faction/clan filter.
        self.type_lord_var     = tk.BooleanVar(value=True)
        self.type_wanderer_var = tk.BooleanVar(value=True)
        self.type_notable_var  = tk.BooleanVar(value=True)
        self.type_leader_var   = tk.BooleanVar(value=True)
        self._faction_filter_id = None   # None=全部, "__minor__"=在野, else kingdom id
        self._clan_filter_id = None      # None=全部, else clan id
        self.filter_after_id = None

        # 資料庫 tab — full game-character roster (from the companion-mod export)
        # joined with which heroes have a save JSON.
        self.db_rows: List[Dict[str, Any]] = []
        self.db_file_index: Dict[str, Path] = {}

        self.manual_source = tk.StringVar(value="")

        self.config_dir = self.data_dir / CONFIG_DIR_NAME
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.data_dir / LOG_DIR_NAME
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self._migrate_legacy_files()

        self.presets_path = self.config_dir / PRESET_FILE
        self.presets = load_presets(self.presets_path)

        self.favorites_path = self.config_dir / FAVORITES_FILE
        self.favorites = set(load_presets(self.favorites_path).get("favorites", []))

        self.templates_path = self.config_dir / TEMPLATES_FILE
        self.templates = load_presets(self.templates_path)

        self.npc_groups_path = self.config_dir / NPC_GROUPS_FILE
        self.npc_groups = load_presets(self.npc_groups_path).get("groups", {})

        # Campaign display-name aliases (id → user-chosen name). The combobox
        # shows "name (id)" while all logic keeps using the real folder id.
        self.aliases_path = self.config_dir / CAMPAIGN_ALIASES_FILE
        _aliases = load_presets(self.aliases_path)
        self.campaign_aliases = {str(k): str(v) for k, v in _aliases.items()} if isinstance(_aliases, dict) else {}
        self._campaign_ids: List[str] = []
        self._campaign_display_to_id: Dict[str, str] = {}

        self.settings_path, self.settings = build_settings(self.config_dir, SETTINGS_FILE)
        # Resolve + apply the UI language BEFORE any localized label is computed
        # (e.g. the sort-dropdown label below): sort_label() calls tr() at runtime,
        # so setting the language first ensures the initial label matches the
        # active language instead of leaking the default (zh_TW) after a switch.
        # First launch (no saved "language") → detect from the OS locale so an
        # international user doesn't open to Chinese; existing users keep their
        # saved choice.  Persisted once so the choice is explicit and the
        # settings-tab "restart to apply" diff compares against a real value.
        saved_lang = str(self.settings.get("language") or "").strip()
        if not saved_lang:
            saved_lang = detect_default_language()
            self.settings["language"] = saved_lang
            save_json_dict(self.settings_path, self.settings)
        self.language_var = tk.StringVar(value=saved_lang)
        set_lang(self.language_var.get())
        # Before any preview is constructed: registrations apply the delta as
        # they happen, so it has to be known first.
        preview_font.load(self)
        self.main_sort_var.set(sort_label(normalize_default_sort(str(self.settings.get("default_sort", "收藏")))))  # noqa: cjk
        # Holds the *display* string ("name (id)" or id); settings keep the raw id.
        self.default_campaign_var = tk.StringVar(
            value=self._campaign_display(str(self.settings.get("default_campaign", "")).strip()))
        # Localize the window title now that the language is set (it was given an
        # English fallback at construction, before language was known).  Language
        # changes require a restart, so this one-time set is sufficient.
        root.title(tr("AI效應：故事大師"))

        # Terminology now comes solely from the companion mod's per-campaign
        # export (no base files / ProemConfig).  primary/fallback are kept as
        # empty layers so the existing resolver chain stays campaign-only —
        # unknown ids simply render as the raw id.
        self.terminology_primary: Dict[str, Any] = {}
        self.terminology_fallback: Dict[str, Any] = {}
        # Per-campaign terminology cache (Phase 5.5).  Stays empty until a
        # campaign is loaded — see ``_reload_campaign_terminology``.
        # Cache of (id_to_name, name_index) per category for name↔ID resolution
        # (M3); cleared whenever terminology reloads.
        self._term_index_cache: Dict[str, Any] = {}
        self.terminology_cache_dir: Path = self.config_dir / TERM_CAMPAIGN_CACHE_DIR_NAME
        try:
            self.terminology_cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.terminology_campaign: Dict[str, Any] = {}

        self.pending_changes: Dict[Path, Dict[str, Any]] = {}
        self.undo_stack: List[Dict[Path, Dict[str, Any]]] = []
        # v0.36.0 — per-character staged working copies (主工作區暫存機制).
        # Every main-workspace edit mutates a working copy; the global 儲存/取消
        # (top-right) commits or discards.  Supersedes the Stage-C owned_pending
        # list-mutation buffer (owned adds/removes are now derived list deltas).
        self.doc_staging = DocStaging()
        # Stage C — disease assign/remove staging buffer
        # Each entry: {op: "assign"|"remove", hero_sid, disease_id, disease_name, hero_display, [disease_def, campaign_days]}
        self.disease_pending: List[Dict[str, Any]] = []
        # Diplomacy-bundle staging buffer (events + ruler statements).
        # events:     "edits" {event_id: {field: val}}, "delete_ids" set[str]
        # statements: "stmt_edits" {stmt_key: model}, "stmt_deletes" set[key],
        #             "stmt_new" [model]   (keys = diplomacy_service.statement_keys)
        self.dyn_events_pending: Dict[str, Any] = self._dyn_empty_pending()

        self.world_info_items: List[dict] = []
        self.world_secrets_items: List[dict] = []
        self.world_dynamic_events_items: List[dict] = []
        self.diplomacy_bundle: Optional[dict] = None  # full 5.0.x bundle (statements/pressure/tax)
        self.economic_effects: List[dict] = []
        self.diseases: List[dict] = []
        self.disease_instances: List[dict] = []
        self.selected_info_index: Optional[int] = None
        self.selected_secret_index: Optional[int] = None
        self.drag_payload: Optional[Tuple[tk.Listbox, str]] = None
        self.selected_list_mapping: List[str] = []
        self._detail_display: Optional[str] = None
        self._info_display_map: List[int] = []
        self._secret_display_map: List[int] = []
        # Global edit mode — ONE shared variable for every tab/widget. Toggling
        # the checkbox in any tab flips edit mode everywhere (widgets/tabs each
        # attach their own idempotent UI-sync trace; pending-changes guards stay
        # in the individual checkbox commands).
        self.edit_mode_var = tk.BooleanVar(value=False)
        self.edit_mode_var.trace_add("write", lambda *_: self._on_global_edit_mode_changed())
        self.world_edit_mode_var = self.edit_mode_var  # legacy alias (world tab)
        self.world_sort_edit_var = tk.BooleanVar(value=False)
        self.world_edit_buttons: list = []
        self.world_dirty = False
        self.world_info_original: List[dict] = []
        self.world_secrets_original: List[dict] = []
        self.world_preview_after_id = None
        self.character_load_seq = 0
        self.world_owner_focus_kind = "info"
        self.cloned_owner_source: Optional[Dict[str, Any]] = None

        self.log_file = self.logs_dir / LOG_FILE

        # File-location settings (檔案位置區塊)
        # Backups live under the data dir (single user-relocatable location).
        self.backup_dir_var   = tk.StringVar(value=str(self.data_dir / "backups"))
        self.game_dir_var     = tk.StringVar(value=str(self.settings.get("game_dir") or ""))
        self.save_data_var    = tk.StringVar(value=str(self.settings.get("save_data_dir") or ""))

        # Bannerlord install root (resolved by _init_paths(); user can override via settings).
        self.game_dir: Optional[Path] = None
        # ProemConfig / StoryToolsMod exports dir — resolved after _init_paths(); placeholder until then.
        self.exports_ids_dir: Optional[Path] = None

        # Game-status heartbeat (G3).
        self._game_status = None
        self._game_status_after_id: Optional[str] = None

        self._build_ui()
        self._init_paths()
        # Defer the first full load until the Tk event loop is actually running.
        # The character list loads on a background thread that signals the UI via
        # root.after(); when refresh() runs synchronously inside __init__ (before
        # mainloop, while the splash is being torn down) that cross-thread after()
        # post can be dropped, leaving the main work area empty until a manual
        # 重新載入. Scheduling refresh() as the first idle task fixes that.
        self.root.after(0, self.refresh)
        # Start heartbeat shortly after UI is ready.
        self.root.after(800, self._tick_game_status)

    def _migrate_legacy_files(self):
        legacy_to_new = {
            self.script_dir / PRESET_FILE: self.config_dir / PRESET_FILE,
            self.script_dir / FAVORITES_FILE: self.config_dir / FAVORITES_FILE,
            self.script_dir / TEMPLATES_FILE: self.config_dir / TEMPLATES_FILE,
            self.script_dir / NPC_GROUPS_FILE: self.config_dir / NPC_GROUPS_FILE,
            self.script_dir / SETTINGS_FILE: self.config_dir / SETTINGS_FILE,
            self.script_dir / LOG_FILE: self.logs_dir / LOG_FILE,
        }
        for old_path, new_path in legacy_to_new.items():
            try:
                if old_path.exists() and not new_path.exists():
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old_path, new_path)
            except Exception:
                pass

    def _center_window(self, win: tk.Toplevel, width: int = None, height: int = None):
        win.update_idletasks()
        if width is None:
            width = win.winfo_width()
        if height is None:
            height = win.winfo_height()
        x = (win.winfo_screenwidth() // 2) - (width // 2)
        y = (win.winfo_screenheight() // 2) - (height // 2) - 30
        win.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.notebook = notebook

        build_main_tab(self, notebook)
        build_world_tab(self, notebook)
        build_dynamic_events_tab(self, notebook)
        build_disease_tab(self, notebook)
        build_database_tab(self, notebook)
        build_backup_tab(self, notebook)
        build_log_tab(self, notebook)
        self._settings_tab_index = notebook.index("end")  # next tab added = settings
        build_settings_tab(self, notebook)
        build_about_tab(self, notebook)

        self._apply_tree_separators()
        self._apply_world_edit_mode()
        self._apply_world_sort_mode()
        self.refresh_backup_center()

        # Register close handler to cancel the heartbeat after() callback.
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        """Guard pending changes, then cancel heartbeat and destroy the window."""
        # Stage C — prompt about any unsaved staging buffers.
        if not self._confirm_discard_all_pending(tr("關閉工具")):
            return  # User chose 回去 — abort close
        if self._game_status_after_id is not None:
            try:
                self.root.after_cancel(self._game_status_after_id)
            except Exception:
                pass
            self._game_status_after_id = None
        self.root.destroy()

    def _bind_mousewheel(self, widget):
        pass

    def _init_paths(self):
        # Honour user-provided save_data override first.
        override_save_str = (self.settings.get("save_data_dir") or "").strip()
        if override_save_str and Path(override_save_str).is_dir():
            sd = Path(override_save_str)
        else:
            sd = find_save_data(self.app_base)

        if sd is None:
            messagebox.showerror(tr("找不到 AI Influence 資料"),
                                 tr("無法自動偵測到 AIInfluence 的 save_data 資料夾。\n\n"
                                 "請到「設定」分頁的「檔案位置」手動指定。"))
            return
        self.save_data_dir = sd
        self.save_data_var.set(str(sd))

        # Resolve game directory (BannerlordRoot).
        from services.path_service import find_bannerlord_root_from_save_data as _find_root
        override_game_str = (self.settings.get("game_dir") or "").strip()
        if override_game_str and Path(override_game_str).is_dir():
            self.game_dir = Path(override_game_str)
        else:
            self.game_dir = _find_root(sd)
        if self.game_dir is not None:
            self.game_dir_var.set(str(self.game_dir))

        # ProemConfig is no longer used — terminology comes from the companion
        # mod's per-campaign export only.
        self.exports_ids_dir = None

    def _confirm_discard_world_changes(self, action_name: str) -> bool:
        if not self.world_dirty:
            return True
        return messagebox.askyesno(
            tr("訊息與秘密尚未儲存"),
            tr("目前有未儲存變更，是否先放棄再{action_name}？").format(action_name=action_name)
        )

    def _sync_sort_preferences_to_ui(self):
        # Vars hold the *display label*; settings keep the canonical SortKey.
        preferred = sort_label(normalize_default_sort(str(self.settings.get("default_sort", "收藏"))))  # noqa: cjk
        self.main_sort_var.set(preferred)
        if hasattr(self, "default_sort_var"):
            self.default_sort_var.set(preferred)
        if hasattr(self, "owner_sort_var"):
            self.owner_sort_var.set(preferred)

    def _browse_save_data(self):
        if not self._confirm_discard_world_changes(tr("切換資料夾")):
            return
        d = filedialog.askdirectory(title=tr("請選擇 AIInfluence 的 save_data 資料夾"))
        if not d:
            return
        p = Path(d)
        if not p.is_dir():
            return
        self.save_data_dir = p
        self.refresh(ask_dirty=False)

    def _list_campaigns(self) -> List[str]:
        return ctl_list_campaigns(self.save_data_dir)

    # ── Campaign display-name (alias) mapping ───────────────────────────────
    # The campaign combobox shows "name (id)" when the user has set a display
    # name, else the raw id.  All logic keeps using the real folder id; these
    # helpers convert between the shown label and that id.
    def _campaign_display(self, cid: str) -> str:
        cid = (cid or "").strip()
        if not cid:
            return ""
        alias = self.campaign_aliases.get(cid)
        return f"{alias} ({cid})" if alias else cid

    def _campaign_id_from_display(self, disp: str) -> str:
        disp = (disp or "").strip()
        # Reverse map first; fall back to the raw text so a real id still works.
        return self._campaign_display_to_id.get(disp, disp)

    def _populate_campaign_values(self, camps: List[str]) -> None:
        """Set both campaign comboboxes' values to display strings and rebuild
        the display→id reverse map from the given real-id list."""
        self._campaign_ids = list(camps)
        displays = [self._campaign_display(c) for c in camps]
        self._campaign_display_to_id = {d: c for d, c in zip(displays, camps)}
        if hasattr(self, "campaign_combo"):
            self.campaign_combo.configure(values=displays)
        if hasattr(self, "default_campaign_combo"):
            self.default_campaign_combo.configure(values=displays)

    def _selected_campaign_id(self) -> str:
        combo = getattr(self, "campaign_combo", None)
        if combo is None:
            return ""
        try:
            return self._campaign_id_from_display(combo.get().strip())
        except Exception:
            return ""

    def _set_campaign_combo_by_id(self, cid: str) -> None:
        if hasattr(self, "campaign_combo"):
            self.campaign_combo.set(self._campaign_display((cid or "").strip()))

    def _on_campaign_change(self):
        if not self.save_data_dir:
            return
        if not self._confirm_discard_world_changes(tr("切換戰役")):
            if self.campaign_dir is not None:
                self._set_campaign_combo_by_id(self.campaign_dir.name)
            return
        if not self._staging_guard(tr("切換戰役")):
            if self.campaign_dir is not None:
                self._set_campaign_combo_by_id(self.campaign_dir.name)
            return
        name = self._selected_campaign_id()
        self.campaign_dir = self.save_data_dir / name
        # Campaign-level reset: turn off the app-wide edit mode when the data set
        # changes (viewers keep it sticky across character switches only).
        self.edit_mode_var.set(False)
        # Re-evaluate the game↔tool match pill right away against the new campaign
        # (don't make the user wait for the next ~10 s heartbeat tick).
        self._render_status_banner()
        self._reload_campaign_terminology()
        self._load_characters_in_thread()
        self.reload_world_data()

    def _rename_campaign(self):
        """Set/clear a display name for the selected campaign (folder id and the
        real data are untouched). The combobox then shows "name (id)"."""
        cid = self._selected_campaign_id()
        if not cid:
            self.log(tr("尚未選擇戰役"), "WARNING")
            return
        current = self.campaign_aliases.get(cid, "")
        new = messagebox.askstring(
            tr("重新命名戰役"),
            tr("為戰役「{cid}」設定顯示名稱（留空可清除）：").format(cid=cid),
            initialvalue=current,
        )
        if new is None:
            return  # cancelled
        new = new.strip()
        if new:
            self.campaign_aliases[cid] = new
        else:
            self.campaign_aliases.pop(cid, None)
        save_json_dict(self.aliases_path, self.campaign_aliases)
        # Rebuild the combobox display strings, keeping the current selection and
        # refreshing the default-campaign preference label if it points here.
        self._populate_campaign_values(self._campaign_ids)
        self._set_campaign_combo_by_id(cid)
        if hasattr(self, "default_campaign_var"):
            did = self._campaign_id_from_display(self.default_campaign_var.get().strip())
            self.default_campaign_var.set(self._campaign_display(did))
        self.log(tr("戰役顯示名稱已更新"), "SUCCESS")

    def refresh(self, ask_dirty: bool = True):
        if ask_dirty and not self._confirm_discard_world_changes(tr("重新載入")):
            return
        if ask_dirty and not self._staging_guard(tr("重新載入")):
            return
        # Campaign-level reset of the app-wide edit mode (see _on_campaign_change).
        self.edit_mode_var.set(False)
        camps = self._list_campaigns()
        self._populate_campaign_values(camps)

        # Priority: currently-selected campaign (if still valid) → default preference → first available.
        # This ensures that after a manual campaign switch, pressing 重新整理 stays on the
        # user-chosen campaign rather than jumping back to the saved default.  All
        # of these are real ids (display strings are mapped back first).
        current_campaign  = self._selected_campaign_id()
        preferred_campaign = self._campaign_id_from_display(self.default_campaign_var.get().strip())
        target_campaign = ctl_choose_target_campaign(camps, current_campaign, preferred_campaign)
        if target_campaign:
            self._set_campaign_combo_by_id(target_campaign)
            self.campaign_dir = self.save_data_dir / target_campaign
        self._reload_campaign_terminology()

        self._refresh_presets_ui()
        if hasattr(self, "default_campaign_combo"):
            if camps and not self._campaign_id_from_display(self.default_campaign_var.get().strip()):
                self.default_campaign_var.set(self._campaign_display(camps[0]))

        if camps:
            self._load_characters_in_thread()
        else:
            self.characters = []
            self.character_meta = {}
            self.known_info_owners = {}
            self.known_secret_owners = {}
            self._rebuild_list()

        self.reload_world_data()
        self.refresh_backup_center()

    def _load_characters_in_thread(self):
        self.character_load_seq += 1
        seq = self.character_load_seq
        threading.Thread(target=lambda: self._load_characters(seq), daemon=True).start()

    def _load_characters(self, seq: int):
        if seq != self.character_load_seq:
            return
        if not self.campaign_dir or not self.campaign_dir.is_dir():
            return
        campaign_dir = self.campaign_dir
        _term = getattr(self, "terminology_campaign", None)
        _term = _term if isinstance(_term, dict) else {}
        chars, meta, info_map, secret_map = build_characters_and_indexes(
            campaign_dir, safe_load_json,
            hero_attrs=_term.get("hero_attrs"),
            clan_attrs=_term.get("clan_attrs"))
        if seq != self.character_load_seq:
            return
        self.root.after(0, lambda: self._update_ui_after_load(seq, campaign_dir, chars, meta, info_map, secret_map))

    def _update_ui_after_load(
        self,
        seq: int,
        campaign_dir: Path,
        chars: List[Tuple[str, Path]],
        meta: Dict[str, Dict[str, Any]],
        info_map: Dict[str, List[str]],
        secret_map: Dict[str, List[str]],
    ):
        if seq != self.character_load_seq or self.campaign_dir != campaign_dir:
            return
        self.characters = chars
        self.character_meta = meta
        self.known_info_owners = info_map
        self.known_secret_owners = secret_map
        self.plain_to_path = {d: p for d, p in chars}
        self.path_to_plain = {p: d for d, p in chars}
        self._eaves_index = None            # new character set → rebuild lazily
        # Prune selected_displays to only current characters
        current_names = {d for d, _ in chars}
        self.selected_displays &= current_names
        if self.characters and not self.manual_source.get():
            self.manual_source.set(self.characters[0][0])
        # Refresh faction/clan dropdowns to match the freshly-loaded roster.
        try:
            self._refresh_faction_filter_options()
        except Exception:
            pass
        # Rebuild the 資料庫 roster (now that the file index is current).
        try:
            self._refresh_database()
        except Exception:
            pass
        self._rebuild_list()
        self._update_selected_listbox()
        self.log(tr("已載入 {v0} 位角色（{v1}）").format(v0=len(self.characters), v1=self.campaign_dir.name), "SUCCESS")
        self._set_status()
        if hasattr(self, "info_list"):
            self._refresh_world_lists()
        # Force-reload the currently-open detail tab so external JSON edits
        # become visible after pressing 🔄 重新整理, without needing to click
        # away and back. Must be here (not in refresh()) because that function
        # kicks off a background thread; by the time this runs, the main-thread
        # maps (plain_to_path, character_meta, ...) are fully updated.
        current_detail = getattr(self, "_detail_display", None)
        if current_detail and current_detail in self.plain_to_path:
            self._load_character_detail(current_detail)

    def _debounce_rebuild_list(self):
        if self.filter_after_id:
            self.root.after_cancel(self.filter_after_id)
        self.filter_after_id = self.root.after(300, self._rebuild_list)

    def _sorted_character_displays(self, mode: str, reverse: bool = False, displays: Optional[List[str]] = None) -> List[str]:
        values = displays if displays is not None else [d for d, _ in self.characters]
        return sorted_displays(values, mode, reverse, self.character_meta, self.favorites)

    def _display_label(self, display: str, star: bool = False) -> str:
        return display_label(display, self.character_meta, self.favorites, star=star)

    def _is_visible_character(self, display: str, term: str) -> bool:
        return is_visible_character(
            display, term, self.character_meta,
            self.exclude_uninteracted_var.get(),
            party_only=self.party_only_var.get(),
            type_filters=self._current_type_filters(),
            faction=self._current_faction_filter(),
            clan=self._current_clan_filter(),
        )

    # ── Role / faction / clan filter state (main-workspace list) ───────────
    def _current_type_filters(self) -> Dict[str, bool]:
        """Role display toggles; missing vars default to shown (True)."""
        def g(attr):
            v = getattr(self, attr, None)
            return bool(v.get()) if v is not None else True
        return {
            "lord":     g("type_lord_var"),
            "wanderer": g("type_wanderer_var"),
            "notable":  g("type_notable_var"),
            "leader":   g("type_leader_var"),
        }

    def _current_faction_filter(self):
        """Selected faction id, ``"__minor__"`` for 在野, or None for 全部."""
        return getattr(self, "_faction_filter_id", None)

    def _current_clan_filter(self):
        return getattr(self, "_clan_filter_id", None)

    def _refresh_faction_filter_options(self) -> None:
        """Rebuild the faction dropdown from the kingdoms present among characters
        that have companion-mod data (plus a 在野 bucket for clanless heroes)."""
        combo = getattr(self, "_faction_combo", None)
        if combo is None:
            return
        kdom_names = (self.terminology_campaign or {}).get("kingdoms") or {}
        present, has_minor = set(), False
        for m in self.character_meta.values():
            if not m.get("HasAttrs"):
                continue
            k = m.get("Kingdom")
            if k:
                present.add(k)
            else:
                has_minor = True
        all_label = tr("全部陣營")
        self._faction_display_to_id = {all_label: None}
        options = [all_label]
        for kid in sorted(present, key=lambda x: str(kdom_names.get(x, x))):
            label = str(kdom_names.get(kid, kid))
            disp = label if label not in self._faction_display_to_id else f"{label} [{kid}]"
            self._faction_display_to_id[disp] = kid
            options.append(disp)
        if has_minor:
            minor_label = tr("無陣營")
            self._faction_display_to_id[minor_label] = "__minor__"
            options.append(minor_label)
        combo.configure(values=options)
        if self._faction_var.get() not in self._faction_display_to_id:
            self._faction_var.set(all_label)
            self._faction_filter_id = None
        self._refresh_clan_filter_options()

    def _refresh_clan_filter_options(self) -> None:
        """Rebuild the clan dropdown for the currently-selected faction scope."""
        combo = getattr(self, "_clan_combo", None)
        if combo is None:
            return
        clan_names = (self.terminology_campaign or {}).get("clans") or {}
        fid = self._faction_filter_id
        present = set()
        for m in self.character_meta.values():
            if not m.get("HasAttrs"):
                continue
            cl = m.get("Clan")
            if not cl:
                continue
            k = m.get("Kingdom")
            if fid == "__minor__":
                if k:
                    continue
            elif fid is not None and k != fid:
                continue
            present.add(cl)
        all_label = tr("全部氏族")
        self._clan_display_to_id = {all_label: None}
        options = [all_label]
        for cid in sorted(present, key=lambda x: str(clan_names.get(x, x))):
            label = str(clan_names.get(cid, cid))
            disp = label if label not in self._clan_display_to_id else f"{label} [{cid}]"
            self._clan_display_to_id[disp] = cid
            options.append(disp)
        combo.configure(values=options)
        if self._clan_var.get() not in self._clan_display_to_id:
            self._clan_var.set(all_label)
            self._clan_filter_id = None

    def _on_faction_filter_change(self) -> None:
        disp = self._faction_var.get()
        self._faction_filter_id = (getattr(self, "_faction_display_to_id", {}) or {}).get(disp)
        # Picking a faction resets the clan filter and re-scopes the clan list.
        self._clan_filter_id = None
        if hasattr(self, "_clan_var"):
            self._clan_var.set(tr("全部氏族"))
        self._refresh_clan_filter_options()
        self._rebuild_list()

    def _on_clan_filter_change(self) -> None:
        disp = self._clan_var.get()
        self._clan_filter_id = (getattr(self, "_clan_display_to_id", {}) or {}).get(disp)
        self._rebuild_list()

    def _reset_faction_clan_filter(self) -> None:
        self._faction_filter_id = None
        self._clan_filter_id = None
        if hasattr(self, "_faction_var"):
            self._faction_var.set(tr("全部陣營"))
        if hasattr(self, "_clan_var"):
            self._clan_var.set(tr("全部氏族"))
        self._refresh_clan_filter_options()
        self._rebuild_list()

    # ── 資料庫 tab — roster + character-file management ─────────────────────
    def _database_available(self) -> bool:
        """The 資料庫 tab needs companion-mod hero data to be useful."""
        term = getattr(self, "terminology_campaign", None)
        return bool(isinstance(term, dict) and term.get("hero_attrs"))

    def _refresh_database(self) -> None:
        """Rebuild the database rows (roster ⋈ which heroes have a save file).

        The file index is derived from the already-loaded character list so no
        files are re-read; then the tab UI is refreshed if it has been built.
        """
        term = self.terminology_campaign if isinstance(self.terminology_campaign, dict) else {}
        file_index: Dict[str, Path] = {}
        for display, path in getattr(self, "characters", []):
            sid = self.character_meta.get(display, {}).get("StringId")
            if sid:
                file_index[str(sid)] = path
        self.db_file_index = file_index
        self.db_rows = svc_chardb.build_database_rows(
            term.get("hero_attrs"), term.get("clan_attrs"),
            kingdom_names=term.get("kingdoms"), clan_names=term.get("clans"),
            culture_names=term.get("cultures"), file_index=file_index,
            exclude_templates=True,
        )
        fn = getattr(self, "_db_refresh_ui", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _db_reload_after_change(self) -> None:
        """Files changed on disk → reload the roster (also refreshes the DB tab)."""
        self._load_characters_in_thread()

    def _db_generate_rows(self, rows: List[Dict[str, Any]]) -> None:
        rows = [r for r in rows if not r.get("HasFile")]
        if not self.campaign_dir or not rows:
            return
        ok = 0
        for r in rows:
            if svc_chardb.generate_character_file(self.campaign_dir, r, self.safe_write_json_with_backup):
                ok += 1
        self.log(tr("已生成 {n} 個角色檔").format(n=ok), "SUCCESS")
        self._db_reload_after_change()

    def _db_delete_rows(self, rows: List[Dict[str, Any]]) -> None:
        files = [r.get("File") for r in rows if r.get("HasFile") and r.get("File")]
        if not files:
            return
        if not messagebox.askyesno(
                tr("刪除角色檔"),
                tr("確定刪除選取的 {n} 個角色檔嗎？（刪除前會自動備份到角色備份資料夾）").format(n=len(files)),
                parent=self.root):
            return
        cid = self._current_campaign_id()
        backup_base = self.data_dir / "backups"
        ok = 0
        for f in files:
            svc_chardb.backup_character_file(f, backup_base, cid)
            if svc_chardb.delete_character_file(f):
                ok += 1
        self.log(tr("已刪除 {n} 個角色檔（已備份）").format(n=ok), "SUCCESS")
        self._db_reload_after_change()

    def _db_backup_rows(self, rows: List[Dict[str, Any]]) -> None:
        cid = self._current_campaign_id()
        backup_base = self.data_dir / "backups"
        ok = 0
        for r in rows:
            f = r.get("File")
            if f and svc_chardb.backup_character_file(f, backup_base, cid):
                ok += 1
        if ok:
            self.log(tr("已備份 {n} 個角色檔").format(n=ok), "SUCCESS")
            messagebox.showinfo(tr("備份"),
                                tr("已備份 {n} 個角色檔到 backups/character/{cid}/").format(n=ok, cid=cid),
                                parent=self.root)

    def _db_reset_rows(self, rows: List[Dict[str, Any]]) -> None:
        paths = [r.get("File") for r in rows if r.get("HasFile") and r.get("File")]
        if paths:
            open_reset_character_dialog(self, paths)

    def _db_edit_rows(self, rows: List[Dict[str, Any]]) -> None:
        """Send selected (with-file) characters to the main workspace — added to
        the selection and LOCKED so the main list's filters can't drop them."""
        displays: List[str] = []
        for r in rows:
            f = r.get("File")
            if not (r.get("HasFile") and f):
                continue
            disp = self.path_to_plain.get(f) or self.path_to_plain.get(Path(f))
            if disp:
                displays.append(disp)
        if not displays:
            messagebox.showinfo(tr("編輯"),
                                tr("選取的角色尚無存檔，請先「生成」再編輯。"), parent=self.root)
            return
        self.selected_displays |= set(displays)
        self._locked_displays |= set(displays)
        target = displays[0]
        self.manual_source.set(target)
        if hasattr(self, "current_target_var"):
            self.current_target_var.set(target)
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(0)  # main workspace tab
            except Exception:
                pass
        self._rebuild_list()
        self._update_selected_listbox()
        try:
            self._schedule_load_detail(target)
        except Exception:
            pass
        self.log(tr("已將 {n} 位角色加入主工作區（已鎖定）").format(n=len(displays)), "INFO")

    # ── 載入群聊（群聊參與者偵測＋修復；暫時修補，見 findings/群聊參與者偵測_可行性.md）──
    def _load_group_chat(self) -> None:
        from dialogs.group_chat_dialog import open_group_chat_dialog
        open_group_chat_dialog(self)

    def _group_chat_commit(self, displays: List[str], day: float,
                           fix_last: bool, fix_count: bool) -> None:
        """Replace + lock the selection with the group, then optionally repair
        LastInteractionTimeDays / interaction_count on each participant file."""
        displays = [d for d in displays if d in self.plain_to_path]
        if not displays:
            return
        if (fix_last or fix_count) and self._staged_conflict_block(
                [self.plain_to_path[d] for d in displays], tr("載入群聊")):
            return
        # Fully replace the selection and lock the group (survives filters).
        self.selected_displays = set(displays)
        self._locked_displays = set(displays)
        target = displays[0]
        self.manual_source.set(target)
        if hasattr(self, "current_target_var"):
            self.current_target_var.set(target)
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(0)   # main workspace tab
            except Exception:
                pass

        fixed = 0
        if fix_last or fix_count:
            for disp in displays:
                path = self.plain_to_path.get(disp)
                if not path:
                    continue
                d = safe_load_json(path)
                if not isinstance(d, dict):
                    continue
                nd = svc_group.apply_repair(
                    d, day, fix_last_interaction=fix_last, fix_interaction_count=fix_count)
                if nd != d and self.safe_write_json_with_backup(path, nd):
                    fixed += 1

        self._rebuild_list()
        self._update_selected_listbox()
        try:
            self._schedule_load_detail(target)
        except Exception:
            pass
        msg = tr("已載入群聊 {n} 人並上鎖").format(n=len(displays))
        if fix_last or fix_count:
            msg += tr("；修復 {n} 位（最後互動時間／互動次數）").format(n=fixed)
        self.log(msg, "SUCCESS")
        if self.selected_displays:
            self._load_character_detail(target)

    def _db_batch_generate(self, rows: List[Dict[str, Any]], exclusions: Dict[str, bool]) -> None:
        if not self.campaign_dir or not rows:
            return
        res = svc_chardb.batch_generate(self.campaign_dir, rows, self.safe_write_json_with_backup, **exclusions)
        self.log(tr("批量生成：新建 {c}，略過已有檔 {e}，排除 {x}").format(
            c=res["created"], e=res["skipped_existing"], x=res["skipped_excluded"]), "SUCCESS")
        self._db_reload_after_change()

    def _db_update_database(self) -> None:
        """Re-read the companion-mod export and reload the roster + DB tab."""
        self._reload_campaign_terminology()
        self._load_characters_in_thread()  # → _update_ui_after_load → _refresh_database

    def _db_clear_database(self) -> None:
        """Delete the campaign's exported DB files (moved to backups first)."""
        cid = self._current_campaign_id()
        if not cid:
            return
        if not messagebox.askyesno(
                tr("清除資料庫"),
                tr("確定刪除此戰役的資料庫檔案嗎？\n\n會刪除 storytools 內的 terminology.json 與 world_snapshot.json"
                   "（刪除前自動移到工具備份資料夾，可復原）。\n下次在遊戲內載入此戰役時，連接器會重新匯出。"),
                parent=self.root):
            return
        import shutil
        import datetime as _dt
        campaign_dir = getattr(self, "campaign_dir", None)
        deleted = 0
        if campaign_dir:
            st = Path(campaign_dir) / "storytools"
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.data_dir / "backups" / "db" / f"terminology_{cid}_{ts}"
            for fn in ("terminology.json", "world_snapshot.json"):
                fp = st / fn
                try:
                    if fp.is_file():
                        bak.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(fp), str(bak / fn))
                        deleted += 1
                except Exception as exc:
                    self.log(tr("清除資料庫：刪除 {fn} 失敗：{exc}").format(fn=fn, exc=exc), "ERROR")
        self._reload_campaign_terminology()       # file gone → terminology_campaign = {}
        self._load_characters_in_thread()         # rebuilds roster → DB tab placeholder
        messagebox.showinfo(
            tr("資料庫"),
            (tr("已刪除 {n} 個資料庫檔案（已備份）。").format(n=deleted) if deleted
             else tr("沒有可刪除的資料庫檔案。")),
            parent=self.root)

    def _rebuild_list(self):
        self.filter_after_id = None
        self._list_rebuilding = True
        try:
            term = self.filter_var.get().strip().lower()
            mode = sort_key_from_label(self.main_sort_var.get())

            chars = self._sorted_character_displays(mode, self.main_sort_reverse_var.get())

            top = self.char_list.yview()[0]   # preserve scroll across rebuild
            self.char_list.delete(0, tk.END)
            self._char_display_list = []

            for display in chars:
                if not self._is_visible_character(display, term):
                    continue
                label = self._display_label(display, star=True)
                self.char_list.insert(tk.END, label)
                self._char_display_list.append(display)

            # Re-apply visual selection highlights
            for i, display in enumerate(self._char_display_list):
                if display in self.selected_displays:
                    self.char_list.selection_set(i)
            self.char_list.yview_moveto(top)
        finally:
            self._list_rebuilding = False

    # ── Character list event handlers ─────────────────────────────────────────

    def _on_char_list_select(self, event=None):
        """Toggle characters in the selected list. Never auto-sets operation target.

        Setting the operation target is intentional only via:
          - clicking in the selected_listbox
          - right-click → 設為操作對象
        The only exception: if the selected list AND current target are both empty,
        we still auto-set the first added character so the UI isn't left in a
        "no target" state after the very first selection.
        """
        # Guard: skip spurious events fired by _rebuild_list's selection_set calls.
        if self._list_rebuilding:
            return

        was_empty = len(self.selected_displays) == 0
        current_target = self.manual_source.get()

        # Characters visible in the current (possibly filtered) list
        visible_set: Set[str] = set(self._char_display_list)

        selected_indices = self.char_list.curselection()
        visible_selected: Set[str] = set()
        for i in selected_indices:
            if i < len(self._char_display_list):
                display = self._char_display_list[i]
                if display is not None:
                    visible_selected.add(display)

        # Preserve characters that the user did NOT actively touch:
        #   1. Filtered-out characters — not visible, so not in curselection;
        #      the user didn't deselect them, the filter just hid them.
        #   2. Locked characters — immune to any unintentional deselection.
        filtered_out = self.selected_displays - visible_set
        locked_keep  = self._locked_displays & self.selected_displays
        new_selected  = visible_selected | filtered_out | locked_keep
        self.selected_displays = new_selected

        # Auto-set target ONLY when transitioning from truly empty (no list + no target)
        if was_empty and not current_target and new_selected:
            first_added = next(iter(new_selected))
            self.manual_source.set(first_added)
            if hasattr(self, "current_target_var"):
                self.current_target_var.set(first_added)
            self._schedule_load_detail(first_added)

        self._update_selected_listbox()
        self._set_status()
        if not new_selected:
            # Nothing selected → clear the right-side preview to match.
            self._clear_detail_panel()

    def _update_selected_listbox(self):
        self._selected_list_updating = True
        sel_top = self.selected_listbox.yview()[0]   # preserve scroll across rebuild
        self.selected_listbox.delete(0, tk.END)
        self.selected_list_mapping = []
        mode = sort_key_from_label(self.main_sort_var.get())
        selected_sorted = self._sorted_character_displays(mode, self.main_sort_reverse_var.get(),
                                                          displays=list(self.selected_displays))
        current_target = self.manual_source.get()
        # Read the Listbox's own normal bg/fg once so we can make native
        # selection invisible for non-target rows (itemconfig selectbackground
        # overrides the widget-level selectbackground per row).
        lb = self.selected_listbox
        normal_bg = lb.cget("background")
        normal_fg = lb.cget("foreground")

        # v0.36: characters with staged (unsaved) edits get a trailing ● marker
        # + amber text so the pending state is visible at a glance.
        dirty_paths = set(self.doc_staging.dirty_paths()) if hasattr(self, "doc_staging") else set()

        for display in selected_sorted:
            # Show only the Name field (not StringId) to keep labels short
            meta = self.character_meta.get(display, {})
            name = str(meta.get("Name") or "").strip() or normalize_display_name(display)
            arrow_part = "▶ " if display == current_target else "  "
            lock_part  = "🔒 " if display in self._locked_displays else ""
            star_part  = "★ " if display in self.favorites else ""
            is_dirty = self.plain_to_path.get(display) in dirty_paths
            dirty_part = " ●" if is_dirty else ""
            label = f"{arrow_part}{lock_part}{star_part}{name}{dirty_part}"
            lb.insert(tk.END, label)
            self.selected_list_mapping.append(display)
            idx = len(self.selected_list_mapping) - 1
            if display == current_target:
                # Gold / amber highlight for the active operation target.
                # Also set selectbackground so the gold survives native selection.
                lb.itemconfig(idx,
                              background=tcol("#C49A2D"), foreground=tcol("#FFFFFF"),
                              selectbackground=tcol("#C49A2D"), selectforeground=tcol("#FFFFFF"))
            else:
                # Non-target rows: make native selection invisible by matching
                # selectbackground to the row's own background.
                row_fg = tcol("#B26B00") if is_dirty else normal_fg
                lb.itemconfig(idx,
                              background=normal_bg, foreground=row_fg,
                              selectbackground=normal_bg, selectforeground=row_fg)
        # Belt-and-suspenders: also clear any lingering native selection.
        lb.selection_clear(0, tk.END)
        lb.yview_moveto(sel_top)
        self._selected_list_updating = False

    def _set_operation_target(self, display: str) -> None:
        """Set the operation target: add to selected list if absent, highlight, update label, load detail.

        v0.36: no unsaved-changes guard here — staged working copies are keyed
        per character path and survive switching; the global 儲存/取消 handles them.
        """
        # Ensure the target is in the selected list
        if display not in self.selected_displays:
            self.selected_displays.add(display)
            for i, d in enumerate(self._char_display_list):
                if d == display:
                    self.char_list.selection_set(i)
                    break
        self.manual_source.set(display)
        if hasattr(self, "current_target_var"):
            self.current_target_var.set(display)
        self._update_selected_listbox()   # re-render to apply gold highlight
        # Load immediately (not debounced): the user explicitly chose this target.
        # Using _schedule_load_detail here opened an 80 ms race-condition window
        # where a spurious event could schedule a different character and "win".
        self._load_character_detail(display)

    def _on_selected_list_click(self, event=None):
        # Use nearest(event.y) instead of curselection():
        # curselection() is unreliable after programmatic Listbox rebuilds and
        # can return stale or shifted indices, causing the wrong character to be
        # set as target. nearest() always maps the physical click position to the
        # correct item regardless of selection state.
        if getattr(self, "_selected_list_updating", False):
            return
        idx = self.selected_listbox.nearest(event.y)
        if idx < 0 or idx >= len(self.selected_list_mapping):
            return
        display = self.selected_list_mapping[idx]
        self._set_operation_target(display)

    def _on_char_list_right_click(self, event):
        """Right-click: show context menu (prevents accidental favorite toggling)."""
        idx = self.char_list.nearest(event.y)
        if idx < 0 or idx >= len(self._char_display_list):
            return
        display = self._char_display_list[idx]
        if not display:
            return
        menu = tk.Menu(self.root, tearoff=0)
        if display in self.favorites:
            menu.add_command(label=tr("★ 取消收藏"), command=lambda: self._toggle_favorite(display))
        else:
            menu.add_command(label=tr("☆ 加入收藏"), command=lambda: self._toggle_favorite(display))
        menu.tk_popup(event.x_root, event.y_root)

    def _schedule_load_detail(self, display: str) -> None:
        """Debounced wrapper: cancels any pending load and schedules a new one after 80 ms.

        This prevents UI thrashing when the user clicks rapidly through the character list.
        Direct callers that need *immediate* reload (edit/delete callbacks) should still
        call _load_character_detail() directly.
        """
        if hasattr(self, "_detail_load_after") and self._detail_load_after:
            self.root.after_cancel(self._detail_load_after)
        self._detail_load_after = self.root.after(80, lambda: self._load_character_detail(display))

    def _load_character_detail(self, display: str) -> None:
        """Load character data into the detail panel tabs."""
        # Cancel any pending debounced load (avoids double-load if called directly after schedule)
        if hasattr(self, "_detail_load_after") and self._detail_load_after:
            self.root.after_cancel(self._detail_load_after)
            self._detail_load_after = None
        self._detail_display = display
        path = self.plain_to_path.get(display)
        if not path:
            return
        disk     = safe_load_json(path) or {}
        # v0.36: most tabs render the EFFECTIVE view (staged working copy when
        # one exists); the owned info/secrets/events viewers instead get the
        # checkout-time BASELINE list — their pending +/− markers are derived
        # from staged-vs-base, so feeding them the staged list would double-show
        # additions.
        data     = self.doc_staging.pending.get(path, disk)
        base     = self.doc_staging.base.get(path, disk)
        meta     = self.character_meta.get(display, {})
        # Keep the cached meta's social/interaction fields in sync with the
        # effective data — the summary card reads these from meta first, so an
        # edit that only changed the (staged) JSON would otherwise show stale values.
        # (Companion-mod fields like Clan/Kingdom/Age are left untouched.)
        if isinstance(meta, dict) and meta:
            pr = data.get("PlayerRelation")
            meta["RomanceLevel"]     = svc_player_romance_level(data)
            meta["TrustLevel"]       = svc_player_trust_level(data)
            meta["InteractionCount"] = svc_player_interaction_count(data)
            meta["RelationValue"]    = float(pr.get("Value", 0)) if isinstance(pr, dict) else 0.0
            meta["NeverInteracted"]  = svc_is_never_interacted(data)
        is_fav   = display in self.favorites
        npc_name = self._get_character_name(path)   # computed once, used by multiple tabs

        if hasattr(self, "summary_card"):
            self.summary_card.load(data, meta, is_favorite=is_fav)
        if hasattr(self, "conversation_viewer"):
            ch = data.get("ConversationHistory", [])
            ch = ch if isinstance(ch, list) else []
            self.conversation_viewer.load(ch,
                                          npc_name=npc_name,
                                          npc_id=str(data.get("StringId") or ""),
                                          rag_status=self._rag_status_for(path.parent, data))
            # 旁聽／共用 counts are computed off the critical path (campaign-wide scan)
            self._schedule_conv_relations(path)
        if hasattr(self, "observations_page"):
            self.observations_page.load(data, npc_name=npc_name)
        if hasattr(self, "memory_page"):
            # path.parent is the campaign dir → memory_images/<id>.png resolves.
            self.memory_page.load(data, campaign_dir=path.parent, npc_name=npc_name)
        if hasattr(self, "json_preview"):
            self.json_preview.load(data)

        # ── Owned info / secrets tabs ─────────────────────────────────────
        # save_data_dir is the "campaign loaded" indicator: if None, world data
        # may only be sample data so we show a placeholder instead.
        world_loaded = self.save_data_dir is not None
        if hasattr(self, "owned_info_viewer"):
            if world_loaded:
                owned_info = [str(x) for x in base.get("KnownInfo", [])
                              if isinstance(x, (str, int)) and str(x).strip()]
                self.owned_info_viewer.load(owned_info, self.world_info_items, npc_name=npc_name)
            else:
                self.owned_info_viewer.show_no_data()
        if hasattr(self, "owned_secrets_viewer"):
            if world_loaded:
                owned_sec = [str(x) for x in base.get("KnownSecrets", [])
                             if isinstance(x, (str, int)) and str(x).strip()]
                self.owned_secrets_viewer.load(owned_sec, self.world_secrets_items, npc_name=npc_name)
            else:
                self.owned_secrets_viewer.show_no_data()
        if hasattr(self, "owned_events_viewer"):
            if world_loaded:
                owned_ev_ids = [str(x) for x in base.get("DynamicEvents", [])
                                if isinstance(x, (str, int)) and str(x).strip()]
                # Normalize dynamic_events entries to the {id, description} shape
                # expected by OwnedItemsViewer, keeping that widget generic.
                normalized_events = [
                    {
                        "id": ev.get("id", ""),
                        "description": (
                            f"【{svc_display.dynamic_event_type_label(ev.get('type', '?'))}"
                            f"｜{tr('重要度')} {ev.get('importance', '?')}】\n"
                            f"{ev.get('title', '')}\n{ev.get('description', '')}"
                        ),
                    }
                    for ev in self.world_dynamic_events_items
                    if ev.get("id")
                ]
                self.owned_events_viewer.load(owned_ev_ids, normalized_events, npc_name=npc_name)
            else:
                self.owned_events_viewer.show_no_data()
        if hasattr(self, "recent_events_viewer"):
            recent = data.get("RecentEvents", [])
            self.recent_events_viewer.load(recent if isinstance(recent, list) else [], npc_name=npc_name)

    def _clear_detail_panel(self) -> None:
        """Empty the right-side detail tabs when no character is selected."""
        self._detail_display = None
        if hasattr(self, "manual_source"):
            self.manual_source.set("")
        if hasattr(self, "current_target_var"):
            self.current_target_var.set(tr("（請先在左側選取角色）"))
        for attr in ("summary_card", "conversation_viewer", "observations_page",
                     "memory_page", "json_preview", "recent_events_viewer",
                     "owned_info_viewer", "owned_secrets_viewer", "owned_events_viewer"):
            w = getattr(self, attr, None)
            if w is not None and hasattr(w, "clear"):
                try:
                    w.clear()
                except Exception:
                    pass

    def _on_global_edit_mode_changed(self):
        """Trace on the shared edit_mode_var — sync tab-level UI everywhere.

        Widgets (summary card, JSON preview, conversation/owned/recent viewers,
        dynamic events panel) attach their own traces; only tab-level apply
        functions that live on the app need dispatching here. Guards against
        being fired before the UI is fully built.
        """
        try:
            if hasattr(self, "world_edit_buttons") and self.world_edit_buttons:
                self._apply_world_edit_mode()
        except Exception:
            pass

    def _apply_world_edit_mode(self):
        editable = self.world_edit_mode_var.get()
        state = "normal" if editable else "disabled"
        for btn in self.world_edit_buttons:
            btn.configure(state=state)
        # Sort toggle was removed — sort capability is now folded into edit
        # mode itself. Mirror the edit-mode flag onto world_sort_edit_var so
        # downstream logic (move buttons, _move_world_item guard) keeps working.
        self.world_sort_edit_var.set(bool(editable))
        # Legacy: if a sort_toggle widget is present (older builds), update it.
        sort_toggle = getattr(self, "world_sort_toggle", None)
        if sort_toggle is not None:
            try:
                sort_toggle.configure(state=state)
            except Exception:
                pass
        self._apply_world_sort_mode()

    def _apply_world_sort_mode(self):
        # Sort buttons are enabled whenever edit mode is on (the dedicated
        # sort-toggle was removed — see _apply_world_edit_mode).
        sort_state = "normal" if self.world_edit_mode_var.get() else "disabled"
        if hasattr(self, "info_move_frame"):
            for w in self.info_move_frame.winfo_children():
                w.configure(state=sort_state)
        if hasattr(self, "secret_move_frame"):
            for w in self.secret_move_frame.winfo_children():
                w.configure(state=sort_state)

    def _mark_world_dirty(self, dirty: bool = True):
        self.world_dirty = dirty
        if dirty:
            # Show a file count in the same「● 未儲存 N 檔」idiom as the main
            # workspace. N = world files that differ (world_info / world_secrets);
            # owner-only reassignments change no world file but still need saving,
            # so floor at 1.
            try:
                info_changed, secret_changed = ctl_world_files_changed(
                    self.world_info_items, self.world_info_original,
                    self.world_secrets_items, self.world_secrets_original)
                n = (1 if info_changed else 0) + (1 if secret_changed else 0)
            except Exception:
                n = 1
            self.world_dirty_var.set(tr("● 未儲存 {v0} 檔").format(v0=max(n, 1)))
        else:
            self.world_dirty_var.set("")
        self._refresh_world_save_buttons()

    def _refresh_world_save_buttons(self):
        """Show 儲存／取消 only when there are unsaved world changes."""
        save = getattr(self, "btn_world_save", None)
        cancel = getattr(self, "btn_world_cancel", None)
        if save is None or cancel is None:
            return
        kw = getattr(self, "_world_save_pack", {"side": tk.LEFT, "padx": 2})
        if getattr(self, "world_dirty", False):
            cancel.pack(**kw)   # cancel left, save right
            save.pack(**kw)
        else:
            save.pack_forget()
            cancel.pack_forget()

    def _move_world_item(self, kind: str, delta: int):
        if not (self.world_edit_mode_var.get() and self.world_sort_edit_var.get()):
            return
        items = self.world_info_items if kind == "info" else self.world_secrets_items
        idx = self.selected_info_index if kind == "info" else self.selected_secret_index
        lb = self.info_list if kind == "info" else self.secret_list
        if idx is None or idx < 0 or idx >= len(items):
            return
        new_idx, moved = svc_move_item(items, idx, delta)
        if not moved:
            return
        if kind == "info":
            self.selected_info_index = new_idx
        else:
            self.selected_secret_index = new_idx
        self._mark_world_dirty(True)
        self._refresh_world_lists()
        dmap = self._info_display_map if kind == "info" else self._secret_display_map
        lb_idx = dmap.index(new_idx) if new_idx in dmap else None
        if lb_idx is not None:
            lb.selection_clear(0, tk.END)
            lb.selection_set(lb_idx)
            lb.see(lb_idx)

    def _selected_owner_context(self) -> Optional[Tuple[str, str, str, str]]:
        return ctl_resolve_owner_context(
            self.world_owner_focus_kind,
            self.selected_info_index,
            self.selected_secret_index,
            self.world_info_items,
            self.world_secrets_items,
        )

    def remove_owner_from_selected_item(self):
        if not self.world_edit_mode_var.get():
            return
        ctx = self._selected_owner_context()
        if not ctx:
            messagebox.showinfo(tr("移除"), tr("請先選擇左側的公開訊息或秘密"))
            return
        kind, item_id, field, label = ctx
        if not item_id:
            return
        lb = self.world_owner_list
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo(tr("移除"), tr("請先在擁有者名單選擇 NPC"))
            return
        owners = self._world_item_owners(item_id, field)
        selected_names = []
        for idx in sel:
            if idx < len(owners):
                selected_names.append(owners[idx])
        if not selected_names:
            return
        target_map = self.known_info_owners if kind == "info" else self.known_secret_owners
        _, removed_count = svc_remove_owners(target_map, item_id, selected_names)
        if removed_count <= 0:
            return
        self._mark_world_dirty(True)
        self._refresh_world_lists()
        self.log(tr("已從 {label} {item_id} 移除 {removed_count} 位 NPC（待儲存）").format(label=label, item_id=item_id, removed_count=removed_count), "INFO")

    def clear_owners_from_selected_item(self):
        if not self.world_edit_mode_var.get():
            return
        ctx = self._selected_owner_context()
        if not ctx:
            messagebox.showinfo(tr("清空"), tr("請先選擇左側的公開訊息或秘密"))
            return
        kind, item_id, _field, label = ctx
        if not item_id:
            return
        target_map = self.known_info_owners if kind == "info" else self.known_secret_owners
        current = target_map.get(item_id, [])
        if not current:
            return
        if not messagebox.askyesno(tr("清空"), tr("確定清空「{label} {item_id}」的擁有者清單嗎？").format(label=label, item_id=item_id)):
            return
        _, cleared_count = svc_clear_owners(target_map, item_id)
        if cleared_count <= 0:
            return
        self._mark_world_dirty(True)
        self._refresh_world_lists()
        self.log(tr("已清空 {label} {item_id} 擁有者清單（{cleared_count} 位，待儲存）").format(label=label, item_id=item_id, cleared_count=cleared_count), "INFO")

    def clone_owner_list_from_selected_item(self):
        ctx = self._selected_owner_context()
        if not ctx:
            messagebox.showinfo(tr("仿製清單"), tr("請先選擇左側的公開訊息或秘密"))
            return
        kind, item_id, field, label = ctx
        owners = self._world_item_owners(item_id, field)
        self.cloned_owner_source = svc_clone_payload(kind, item_id, label, owners)
        if hasattr(self, "owner_clone_source_var"):
            self.owner_clone_source_var.set(tr("仿製來源：{label} / {iid} / {n} 位").format(label=label, iid=item_id, n=len(owners)))
        self.log(tr("已設定仿製來源：{label} {item_id}（{v0} 位）").format(label=label, item_id=item_id, v0=len(owners)), "INFO")

    def apply_cloned_owner_list_to_selected_item(self):
        if not self.world_edit_mode_var.get():
            return
        if not self.cloned_owner_source:
            messagebox.showinfo(tr("套用清單"), tr("尚未設定仿製來源"))
            return
        ctx = self._selected_owner_context()
        if not ctx:
            messagebox.showinfo(tr("套用清單"), tr("請先選擇左側的公開訊息或秘密"))
            return
        kind, item_id, _field, label = ctx
        if not item_id:
            return
        target_map = self.known_info_owners if kind == "info" else self.known_secret_owners
        _, applied_count = svc_apply_clone(target_map, item_id, self.cloned_owner_source)
        self._mark_world_dirty(True)
        self._refresh_world_lists()
        src_label = self.cloned_owner_source.get("label", "")
        src_id = self.cloned_owner_source.get("id", "")
        self.log(tr("已套用仿製清單：{src_label} {src_id} -> {label} {item_id}（{applied_count} 位，待儲存）").format(src_label=src_label, src_id=src_id, label=label, item_id=item_id, applied_count=applied_count), "INFO")

    def _world_build_diff_items(self) -> List[Dict[str, Any]]:
        """Preview rows [{name, field, old, new}] for pending 訊息與秘密 changes.

        Covers world_info / world_secrets item add/remove/edit (keyed by ``id``)
        plus per-character owner (KnownInfo/KnownSecrets) reassignments.
        """
        rows: List[Dict[str, Any]] = []

        # field = the item id; old/new = its content — the review dialog's
        # summariser derives the ＋新增／✏編輯文本／🗑清空 action from the value
        # shape, so we don't repeat the verb here (avoids a doubled emoji).
        def _diff_items(cur, orig, group):
            cur_by  = {str(x.get("id", "")): x for x in (cur or [])}
            orig_by = {str(x.get("id", "")): x for x in (orig or [])}
            for iid in cur_by:
                if iid and iid not in orig_by:
                    rows.append({"name": group, "field": iid,
                                 "old": "", "new": cur_by[iid].get("content", "")})
            for iid in orig_by:
                if iid and iid not in cur_by:
                    rows.append({"name": group, "field": iid,
                                 "old": orig_by[iid].get("content", ""), "new": ""})
            for iid in cur_by:
                if iid in orig_by and cur_by[iid] != orig_by[iid]:
                    rows.append({"name": group, "field": iid,
                                 "old": orig_by[iid].get("content", ""),
                                 "new": cur_by[iid].get("content", "")})

        _diff_items(self.world_info_items, self.world_info_original, tr("公開訊息 world_info.json"))
        _diff_items(self.world_secrets_items, self.world_secrets_original, tr("秘密 world_secrets.json"))

        # Owner reassignments: desired KnownInfo/KnownSecrets vs on-disk.
        info_rev, sec_rev = reverse_owner_maps(self.known_info_owners, self.known_secret_owners)
        for display, path in self.characters:
            d = safe_load_json(path) or {}
            cur_info = sorted(d.get("KnownInfo", []) if isinstance(d.get("KnownInfo"), list) else [])
            cur_sec  = sorted(d.get("KnownSecrets", []) if isinstance(d.get("KnownSecrets"), list) else [])
            want_info = sorted(info_rev.get(display, []))
            want_sec  = sorted(sec_rev.get(display, []))
            if cur_info == want_info and cur_sec == want_sec:
                continue
            rows.append({"name": tr("擁有者歸屬"), "field": display,
                         "old": tr("訊息×{i} / 秘密×{s}").format(i=len(cur_info), s=len(cur_sec)),
                         "new": tr("訊息×{i} / 秘密×{s}").format(i=len(want_info), s=len(want_sec))})
        return rows

    def save_world_changes(self, confirm: bool = True):
        if not self.world_dirty:
            messagebox.showinfo(tr("訊息與秘密"), tr("目前沒有未儲存變更"))
            return
        if confirm:
            from dialogs.staging_commit_dialog import (
                open_diff_review_dialog, snapshot_purge_option,
            )
            # world_info/world_secrets live under prompts/ (which the mod's
            # snapshot skips), but owner changes write character JSONs, and those
            # do get reverted — so this flow needs the purge option too.
            _opts, _confirm = snapshot_purge_option(self, self._world_write)
            open_diff_review_dialog(
                self,
                title=tr("儲存訊息與秘密變更"),
                header=tr("以下訊息／秘密／擁有者變更將寫入（寫入前自動備份）："),
                diff_items=self._world_build_diff_items(),
                confirm_label=tr("💾 儲存"),
                on_confirm=_confirm,
                options=_opts,
            )
            return
        self._world_write()

    def _world_write(self):
        info_path, secret_path = self._world_paths()

        world_info_changed, world_secret_changed = ctl_world_files_changed(
            self.world_info_items,
            self.world_info_original,
            self.world_secrets_items,
            self.world_secrets_original,
        )
        if world_info_changed:
            dump_world_items(info_path, self.world_info_items)
        if world_secret_changed:
            dump_world_items(secret_path, self.world_secrets_items)

        info_rev, sec_rev = reverse_owner_maps(self.known_info_owners, self.known_secret_owners)

        owner_changed = False
        for display, path in self.characters:
            d = safe_load_json(path) or {}
            existing_info = d.get("KnownInfo", [])
            existing_secret = d.get("KnownSecrets", [])
            if not isinstance(existing_info, list):
                existing_info = []
            if not isinstance(existing_secret, list):
                existing_secret = []

            desired_info = sorted(info_rev.get(display, []))
            desired_secret = sorted(sec_rev.get(display, []))
            if sorted(existing_info) == desired_info and sorted(existing_secret) == desired_secret:
                continue

            d["KnownInfo"] = desired_info
            d["KnownSecrets"] = desired_secret
            if self.safe_write_json_with_backup(path, d):
                owner_changed = True

        self.world_info_original = json.loads(json.dumps(self.world_info_items, ensure_ascii=False))
        self.world_secrets_original = json.loads(json.dumps(self.world_secrets_items, ensure_ascii=False))
        self._mark_world_dirty(False)
        self.log(ctl_world_save_log_message(world_info_changed, world_secret_changed, owner_changed), "SUCCESS")

    def cancel_world_changes(self):
        self.reload_world_data()
        self._rebuild_owner_index_from_files()
        self._refresh_world_lists()
        self.log(tr("已取消訊息與秘密未儲存變更"), "INFO")

    def validate_world_files(self):
        """有效檢查：JSON 格式 + 項目欄位完整性 + NPC 反向孤兒引用。"""
        info_path, secret_path = self._world_paths()
        # ── 1) File-level JSON validity ──────────────────────────────────
        failures = svc_validate_world_files(info_path, secret_path)
        if failures:
            messagebox.showerror(
                tr("有效檢查"),
                tr("以下檔案格式異常：\n") + "\n".join(failures),
                parent=self.root,
            )
            self.log(tr("訊息與秘密檔案 JSON 格式異常"), "ERROR")
            return

        # ── 2) Per-entry content scan ────────────────────────────────────
        info_items   = list(self.world_info_items or [])
        secret_items = list(self.world_secrets_items or [])
        info_probs, sec_probs, dup_lines = svc_validate_world_items_content(info_items, secret_items)

        # ── 3) Cross-reference: NPC KnownInfo/KnownSecrets vs world catalogs ─
        valid_info_ids   = {str(x.get("id", "")) for x in info_items if x.get("id")}
        valid_secret_ids = {str(x.get("id", "")) for x in secret_items if x.get("id")}
        char_iter = []
        for display, path in self.plain_to_path.items():
            try:
                d = safe_load_json(path) or {}
            except Exception:
                continue
            char_iter.append((display, d))
        info_orphans, sec_orphans = svc_find_orphan_world_refs(
            char_iter, valid_info_ids, valid_secret_ids
        )

        total_issues = len(info_probs) + len(sec_probs) + len(dup_lines) \
                       + len(info_orphans) + len(sec_orphans)
        if total_issues == 0:
            messagebox.showinfo(
                tr("有效檢查"),
                tr("訊息與秘密全數通過：\n  • {v0} 筆訊息、{v1} 筆秘密\n  • {v2} 個角色 JSON，KnownInfo / KnownSecrets 引用全部有效").format(v0=len(info_items), v1=len(secret_items), v2=len(char_iter)),
                parent=self.root,
            )
            self.log(tr("訊息與秘密有效檢查通過"), "SUCCESS")
            return

        lines: List[str] = []
        if info_probs or sec_probs:
            lines.append(tr("📋 內容問題：{v0} 項").format(v0=len(info_probs) + len(sec_probs)))
            lines.extend((info_probs + sec_probs)[:12])
            extra = len(info_probs) + len(sec_probs) - 12
            if extra > 0:
                lines.append(tr("  …及其他 {extra} 項").format(extra=extra))
        if dup_lines:
            if lines: lines.append("")
            lines.append(tr("⚠ 重複 id：{v0} 項").format(v0=len(dup_lines)))
            lines.extend(dup_lines[:8])
        if info_orphans or sec_orphans:
            if lines: lines.append("")
            n_total = sum(len(o[1]) for o in info_orphans) + sum(len(o[1]) for o in sec_orphans)
            lines.append(tr("💡 NPC 反向孤兒引用：{n_total} 個 ID（跨 {v0} 個角色）").format(n_total=n_total, v0=len(info_orphans) + len(sec_orphans)))
            for display, ids in (info_orphans + sec_orphans)[:8]:
                shown = ", ".join(ids[:3]) + ("…" if len(ids) > 3 else "")
                lines.append(f"  • {display}: {shown}")
        messagebox.showwarning(tr("有效檢查"), "\n".join(lines), parent=self.root)
        self.log(tr("訊息與秘密有效檢查發現 {total_issues} 項問題").format(total_issues=total_issues), "WARN")

    def apply_theme_from_settings(self) -> None:
        """Apply the theme selected in the settings tab immediately."""
        from ui import theme as _theme
        if not hasattr(self, "theme_display_var"):
            return
        selected_display = self.theme_display_var.get()
        theme_name = next(
            (t for t, d in AVAILABLE_THEMES if tr(d) == selected_display),
            "sandstone",
        )
        old_mode = _theme.mode()
        new_mode = _theme.theme_mode(theme_name)
        try:
            self.root.style.theme_use(theme_name)
            _theme.set_mode(new_mode)
            self._apply_tree_separators()   # theme_use resets element options
            self.settings["theme"] = theme_name
            save_json_dict(self.settings_path, self.settings)
            self.log(tr("主題已切換為 {theme_name}").format(theme_name=theme_name), "SUCCESS")
            # ttk chrome switches live, but tk.Text/Listbox/Canvas already built
            # keep their creation-time colours — a restart fully re-themes them.
            if new_mode != old_mode:
                messagebox.showinfo(
                    tr("介面主題"),
                    tr("明暗主題已切換。部分元件（文字區、清單）需重新啟動才會完全套用新配色。"),
                    parent=self.root)
        except Exception as e:
            self.log(tr("主題切換失敗: {e}").format(e=e), "ERROR")

    def _apply_tree_separators(self) -> None:
        """Draw vertical separators between every Treeview's column headers.

        ttk.Treeview can't render true body cell gridlines, but a bordered
        heading gives each column a clear boundary in the header row (which the
        eye carries down the columns).  Applied globally so all tables — 統治者
        聲明 / 外交狀態 / 疾病感染清單 / 資料庫各分頁 — read consistently.
        Re-applied after a theme switch because ``theme_use`` resets options.
        """
        try:
            st = self.root.style
        except Exception:
            return
        try:
            st.configure("Treeview.Heading", relief="solid", borderwidth=1)
        except Exception:
            pass
        # bordercolor is honoured by the clam-based ttkbootstrap themes.
        try:
            st.configure("Treeview.Heading", bordercolor=tcol("#B8B8B8"))
        except Exception:
            pass

    def save_preferences(self):
        # File-location settings (檔案位置區塊)
        new_backup_dir = self.backup_dir_var.get().strip()
        new_game_dir   = self.game_dir_var.get().strip()
        new_save_data  = self.save_data_var.get().strip()
        old_save_data  = (self.settings.get("save_data_dir") or "").strip()
        old_game_dir   = (self.settings.get("game_dir") or "").strip()
        self.settings["backup_dir"]    = new_backup_dir
        self.settings["game_dir"]      = new_game_dir
        self.settings["save_data_dir"] = new_save_data
        path_changed = (new_save_data != old_save_data) or (new_game_dir != old_game_dir)

        self.settings["default_sort"] = sort_key_from_label(self.default_sort_var.get())
        if hasattr(self, "snapshot_policy_display_var"):
            self.settings["snapshot_policy"] = svc_snapshot.policy_from_label(
                self.snapshot_policy_display_var.get())
        # default_campaign_var holds the display string; store the real id.
        self.settings["default_campaign"] = self._campaign_id_from_display(self.default_campaign_var.get().strip())
        selected_display = getattr(self, "language_display_var", self.language_var).get()
        lang_code = next(
            (c for c, d in AVAILABLE_LANGUAGES if d == selected_display or c == selected_display),
            "zh_TW",
        )
        if lang_code != self.settings.get("language", "zh_TW"):
            self.settings["language"] = lang_code
            # Update language_var immediately so terminology resolver picks up
            # the new language even before the app restart (i18n strings still
            # need a restart to swap the active dictionary).
            self.language_var.set(lang_code)
            self.reload_terminology()
            messagebox.showinfo(tr("語言設定"), tr("語言變更將於重新啟動後生效。\nLanguage change takes effect on next restart."))
        # Also save the current theme selection (apply separately via the button)
        if hasattr(self, "theme_display_var"):
            selected_theme_display = self.theme_display_var.get()
            theme_name = next(
                (t for t, d in AVAILABLE_THEMES if tr(d) == selected_theme_display),
                "sandstone",
            )
            self.settings["theme"] = theme_name
        save_json_dict(self.settings_path, self.settings)
        self._sync_sort_preferences_to_ui()
        # If file-location paths changed, re-init paths and reload everything.
        if path_changed:
            self._init_paths()
            self.refresh(ask_dirty=False)
            self.refresh_backup_center()
        self._rebuild_list()
        self._refresh_owned_lists()
        camps = self._campaign_ids
        preferred_campaign = self.settings["default_campaign"]
        if preferred_campaign and preferred_campaign in camps and self._selected_campaign_id() != preferred_campaign:
            if not self._confirm_discard_world_changes(tr("套用預設戰役")):
                self.default_campaign_var.set(self._campaign_display(self._selected_campaign_id()))
            else:
                self._set_campaign_combo_by_id(preferred_campaign)
                self.campaign_dir = self.save_data_dir / preferred_campaign
                self._load_characters_in_thread()
        self.log(tr("偏好設定已儲存"), "SUCCESS")

    def refresh_backup_center(self):
        """Delegate to the backup-center UI module (rebuilds the tree)."""
        from ui.backup_tab import refresh_backup_center as _refresh
        _refresh(self)

    def _select_all_visible(self):
        term = self.filter_var.get().strip().lower()
        for display, _ in self.characters:
            if self._is_visible_character(display, term):
                self.selected_displays.add(display)
        self._rebuild_list()
        self._update_selected_listbox()
        self._set_status()

    def _select_none_visible(self):
        term = self.filter_var.get().strip().lower()
        for display, _ in self.characters:
            # Locked characters are immune — skip them
            if display in self._locked_displays:
                continue
            if self._is_visible_character(display, term):
                self.selected_displays.discard(display)
        self._rebuild_list()
        self._update_selected_listbox()
        self._set_status()
        if not self.selected_displays:
            self._clear_detail_panel()

    def _refresh_presets_ui(self):
        names = sorted(self.presets.keys())
        self.preset_combo.configure(values=names)
        if names and self.preset_combo.get() not in names:
            self.preset_combo.set(names[0])

    def _save_preset(self):
        checked = list(self.selected_displays)
        default_name = self.preset_combo.get().strip()

        # ── Popup naming dialog ───────────────────────────────────────────
        win = tk.Toplevel(self.root)
        win.title(tr("儲存群組"))
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self._center_window(win, 320, 125)

        member_hint = tr("（已選 {v0} 位成員）").format(v0=len(checked))
        ttk.Label(win, text=f"{tr('群組名稱')} {member_hint}").pack(
            padx=16, pady=(14, 4), anchor="w"
        )
        name_var = tk.StringVar(value=default_name)
        entry = ttk.Entry(win, textvariable=name_var, width=34)
        entry.pack(fill=tk.X, padx=16, pady=(0, 10))
        entry.select_range(0, "end")
        entry.focus_set()

        def _do_save():
            name = name_var.get().strip()
            if not name:
                return
            win.destroy()
            self.presets[name] = checked
            if save_presets(self.presets_path, self.presets):
                self._refresh_presets_ui()
                self.preset_combo.set(name)
                action = tr("更新") if (name == default_name and default_name) else tr("建立")
                self.log(tr("已{action}群組「{name}」（{v0} 位成員）").format(action=action, name=name, v0=len(checked)), "SUCCESS")

        btn_row = ttk.Frame(win)
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 12))
        ttk.Button(btn_row, text=tr("儲存"), command=_do_save,
                   style="warning.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_row, text=tr("取消"), command=win.destroy,
                   style="secondary.TButton").pack(side=tk.RIGHT)

        entry.bind("<Return>",  lambda e: _do_save())
        entry.bind("<Escape>",  lambda e: win.destroy())

    def _load_preset(self):
        name = self.preset_combo.get().strip()
        if not name or name not in self.presets:
            return
        members = set(self.presets[name])
        current_names = {d for d, _ in self.characters}
        # Locked characters are immune to group load — keep them selected always
        locked_keep = self._locked_displays & self.selected_displays
        self.selected_displays = (current_names & members) | locked_keep
        self._rebuild_list()
        self._update_selected_listbox()
        self._set_status()
        self.log(tr("已載入預設「{name}」").format(name=name), "INFO")

    def _delete_preset(self):
        name = self.preset_combo.get().strip()
        if not name or name not in self.presets:
            return
        if not messagebox.askyesno(tr("刪除預設"), tr("確定要刪除預設「{name}」嗎？").format(name=name)):
            return
        self.presets.pop(name, None)
        save_presets(self.presets_path, self.presets)
        self._refresh_presets_ui()
        self.log(tr("已刪除預設「{name}」").format(name=name), "INFO")

    def _toggle_favorite(self, display: str):
        if display in self.favorites:
            self.favorites.remove(display)
        else:
            self.favorites.add(display)
        save_presets(self.favorites_path, {"favorites": list(self.favorites)})
        self._rebuild_list()

    # ── Selected-list lock helpers ────────────────────────────────────────────

    def _lock_all_selected(self):
        """Lock every character currently in the selected list."""
        self._locked_displays |= self.selected_displays
        self._update_selected_listbox()

    def _unlock_all_selected(self):
        """Remove all locks from selected characters."""
        self._locked_displays.clear()
        self._update_selected_listbox()

    def _toggle_selected_lock(self, display: str):
        """Toggle lock state for one character in the selected list."""
        if display in self._locked_displays:
            self._locked_displays.discard(display)
        else:
            self._locked_displays.add(display)
        self._update_selected_listbox()

    def _on_selected_list_right_click(self, event) -> None:
        """Context menu for the selected-characters listbox."""
        idx = self.selected_listbox.nearest(event.y)
        if idx < 0 or idx >= len(self.selected_list_mapping):
            return
        display = self.selected_list_mapping[idx]
        menu = tk.Menu(self.root, tearoff=False)
        if display in self._locked_displays:
            menu.add_command(
                label=tr("🔓 解鎖"),
                command=lambda: self._toggle_selected_lock(display),
            )
        else:
            menu.add_command(
                label=tr("🔒 鎖定"),
                command=lambda: self._toggle_selected_lock(display),
            )
        menu.add_separator()
        menu.add_command(
            label=tr("✖ 移除選取"),
            command=lambda: self._remove_from_selection(display),
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _remove_from_selection(self, display: str) -> None:
        """Remove a character from the selected list, ignoring its lock state.

        Any staged edits live in ``doc_staging`` keyed by path and are NOT
        discarded here — they persist until the global save/discard, so this
        never loses unsaved work.
        """
        self.selected_displays.discard(display)
        self._locked_displays.discard(display)
        self._rebuild_list()
        self._update_selected_listbox()
        self._set_status()
        if not self.selected_displays:
            self._clear_detail_panel()

    def get_scene_targets(self, source_plain: str) -> List[Path]:
        return [
            p for d, p in self.characters
            if d in self.selected_displays and self.path_to_plain.get(p, "") != source_plain
        ]

    def copy_to_clipboard(self, content: str):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.root.update_idletasks()
            self.log(tr("已複製內容到剪貼簿"), "INFO")
        except Exception as e:
            self.log(tr("複製失敗：{e}").format(e=e), "ERROR")

    def _safe_load_json(self, path: Path) -> Optional[dict]:
        return safe_load_json(path)

    def _source_path(self) -> Optional[Path]:
        return ctl_source_path_from_characters(self.characters, self.manual_source.get())

    def _checked_paths(self) -> List[Path]:
        return [p for d, p in self.characters if d in self.selected_displays]

    def _get_character_name(self, path: Path) -> str:
        data = safe_load_json(path) or {}
        fallback = self.path_to_plain.get(path, path.stem)
        return ctl_resolve_character_name(data, fallback)

    def _effective_data(self, path: Path) -> dict:
        return svc_effective_data(path, self.pending_changes, safe_load_json)

    def _queue_field_change(self, path: Path, field: str, value: Any):
        svc_queue_field_change(self.pending_changes, path, field, value)

    def queue_selected_fields_from_source(self):
        srcp = self._source_path()
        if not srcp:
            messagebox.showwarning(tr("暫存變更"), tr("請先選擇來源角色"))
            return
        targets = self._checked_paths()
        if not targets:
            messagebox.showwarning(tr("暫存變更"), tr("請至少勾選一位角色"))
            return
        open_field_picker_dialog(self, self._effective_data(srcp), targets)

    def open_single_field_editor(self):
        path = self._source_path()
        if not path:
            messagebox.showwarning(tr("角色編輯"), tr("請先選擇角色"))
            return
        open_field_editor_dialog(self, path)

    def _build_diff_items(self) -> List[Dict[str, Any]]:
        return svc_build_diff_items(self.pending_changes, safe_load_json, self._get_character_name)

    def open_diff_submit_window(self):
        items = self._build_diff_items()
        if not items:
            messagebox.showinfo(tr("Diff 提交"), tr("目前沒有暫存變更"))
            return
        open_diff_submit_dialog(self, items)

    def undo_last_commit(self):
        if not self.undo_stack:
            messagebox.showinfo(tr("回復"), tr("目前沒有可回復的提交"))
            return
        snapshot = self.undo_stack.pop()
        ok = 0
        for path, data in snapshot.items():
            if self.safe_write_json_with_backup(path, data):
                ok += 1
        self.log(tr("已回復上一次提交（{ok} 個角色）").format(ok=ok), "SUCCESS")

    def save_template_from_source(self):
        srcp = self._source_path()
        if not srcp:
            messagebox.showwarning(tr("模板"), tr("請先選擇來源角色"))
            return
        name = messagebox.askstring(tr("模板名稱"), tr("請輸入模板名稱："), parent=self.root)
        if not name:
            return
        d = self._effective_data(srcp)
        fields = EDITABLE_TEXT_FIELDS + ["KnownSecrets", "KnownInfo"]
        tpl = svc_template_from_data(d, fields)
        self.templates[name] = tpl
        if save_presets(self.templates_path, self.templates):
            self.log(tr("已儲存模板：{name}").format(name=name), "SUCCESS")

    def apply_template_to_checked(self):
        if not self.templates:
            messagebox.showinfo(tr("模板"), tr("尚未建立模板"))
            return
        targets = self._checked_paths()
        if not targets:
            messagebox.showwarning(tr("模板"), tr("請至少勾選一位角色"))
            return
        names = sorted(self.templates.keys())
        win = tk.Toplevel(self.root)
        win.title(tr("套用模板"))
        win.geometry("340x140")
        self._center_window(win, 340, 140)
        win.transient(self.root)
        v = tk.StringVar(value=names[0])
        ttk.Combobox(win, textvariable=v, values=names, state="readonly").pack(fill=tk.X, padx=10, pady=10)

        def apply_now():
            tpl = self.templates.get(v.get(), {})
            for t in targets:
                for k, val in tpl.items():
                    self._queue_field_change(t, k, val)
            self.log(tr("已套用模板到暫存：{v0} / {v1} 位").format(v0=v.get(), v1=len(targets)), "SUCCESS")
            win.destroy()

        ttk.Button(win, text=tr("套用到暫存"), command=apply_now).pack(side=tk.RIGHT, padx=10, pady=8)

    def _world_paths(self) -> Tuple[Path, Path]:
        # 5.0.x: world_info/world_secrets live per-campaign under prompts/world_data/.
        # 4.1.0: they live at the mod root. world_paths_for_app auto-detects via campaign_dir.
        return world_paths_for_app(
            self.save_data_dir, self.script_dir, getattr(self, "campaign_dir", None)
        )

    def _save_world_file(self, kind: str):
        info_path, secret_path = self._world_paths()
        if kind == "info":
            dump_world_items(info_path, self.world_info_items)
        else:
            dump_world_items(secret_path, self.world_secrets_items)

    def reload_world_data(self):
        info_path, secret_path = self._world_paths()
        self.world_info_items, self.world_secrets_items = load_world_items(info_path, secret_path, safe_load_json)
        self.world_info_original = clone_items(self.world_info_items)
        self.world_secrets_original = clone_items(self.world_secrets_items)
        # Dynamic events and disease data live inside the campaign folder (per-save).
        campaign = getattr(self, "campaign_dir", None)
        de_path = dynamic_events_path_for_app(campaign, self.script_dir)
        self.world_dynamic_events_items = load_dynamic_events(de_path, safe_load_json)
        # Full diplomacy bundle (5.0.x): statements / pressure / tax for the
        # statements + diplomacy-status sub-tabs. None on 4.1.0 legacy layout.
        raw_bundle = safe_load_json(de_path) if de_path.exists() else None
        self.diplomacy_bundle = raw_bundle if isinstance(raw_bundle, dict) else None
        ee_path = economic_effects_path_for_app(campaign, self.script_dir)
        self.economic_effects = load_economic_effects(ee_path, safe_load_json)
        if hasattr(self, "_dyn_tab"):
            refresh_dynamic_events_tab(self)
        def_path, inst_path = disease_paths_for_app(campaign, self.script_dir)
        self.diseases, self.disease_instances = load_disease_data(
            def_path, inst_path, safe_load_json
        )
        if hasattr(self, "_disease_tab"):
            refresh_disease_tab(self)
        self.world_dirty = False
        self._mark_world_dirty(False)
        self.selected_info_index = None
        self.selected_secret_index = None
        if hasattr(self, "info_list"):
            self._refresh_world_lists()

    @staticmethod
    def _owner_count_color(n: int) -> str:
        if n == 0:
            return tcol("#dc3545")
        if n <= 2:
            return tcol("#d97706")
        return tcol("#16a34a")

    def _refresh_world_lists(self):
        info_term = self.world_info_filter_var.get().strip().lower() if hasattr(self, "world_info_filter_var") else ""
        sec_term = self.world_secret_filter_var.get().strip().lower() if hasattr(self, "world_secret_filter_var") else ""

        # Preserve scroll positions so edits/moves don't jump the lists to top.
        info_top = self.info_list.yview()[0]
        sec_top = self.secret_list.yview()[0]

        self.info_list.delete(0, tk.END)
        self._info_display_map = []
        for i, item in enumerate(self.world_info_items):
            iid = str(item.get("id", "")).strip()
            desc = str(item.get("description", ""))
            if info_term and info_term not in iid.lower() and info_term not in desc.lower():
                continue
            owners_n = len(self.known_info_owners.get(iid, [])) if iid else 0
            lb_idx = self.info_list.size()
            self.info_list.insert(tk.END, f"{iid or '(no-id)'} ({owners_n})")
            self.info_list.itemconfig(lb_idx, foreground=self._owner_count_color(owners_n))
            self._info_display_map.append(i)

        self.secret_list.delete(0, tk.END)
        self._secret_display_map = []
        for i, item in enumerate(self.world_secrets_items):
            sid = str(item.get("id", "")).strip()
            desc = str(item.get("description", ""))
            if sec_term and sec_term not in sid.lower() and sec_term not in desc.lower():
                continue
            owners_n = len(self.known_secret_owners.get(sid, [])) if sid else 0
            lb_idx = self.secret_list.size()
            self.secret_list.insert(tk.END, f"{sid or '(no-id)'} ({owners_n})")
            self.secret_list.itemconfig(lb_idx, foreground=self._owner_count_color(owners_n))
            self._secret_display_map.append(i)

        # Restore the visual selection from the persisted data index so an
        # edit/delete/move doesn't leave the row de-highlighted.
        sel_i = getattr(self, "selected_info_index", None)
        if sel_i is not None:
            for lb_idx, di in enumerate(self._info_display_map):
                if di == sel_i:
                    self.info_list.selection_set(lb_idx)
                    break
        sel_s = getattr(self, "selected_secret_index", None)
        if sel_s is not None:
            for lb_idx, di in enumerate(self._secret_display_map):
                if di == sel_s:
                    self.secret_list.selection_set(lb_idx)
                    break

        self.info_list.yview_moveto(info_top)
        self.secret_list.yview_moveto(sec_top)
        self._update_world_preview()

    def _on_world_item_select(self, kind: str):
        self.world_owner_focus_kind = kind
        if kind == "info":
            s = self.info_list.curselection()
            lb_idx = s[0] if s else None
            self.selected_info_index = self._info_display_map[lb_idx] if lb_idx is not None and lb_idx < len(self._info_display_map) else None
        else:
            s = self.secret_list.curselection()
            lb_idx = s[0] if s else None
            self.selected_secret_index = self._secret_display_map[lb_idx] if lb_idx is not None and lb_idx < len(self._secret_display_map) else None
        if self.world_preview_after_id:
            self.root.after_cancel(self.world_preview_after_id)
        self.world_preview_after_id = self.root.after(120, self._update_world_preview)

    def _rebuild_owner_index_from_files(self):
        self.known_info_owners, self.known_secret_owners = build_owner_index_from_characters(
            self.characters, safe_load_json
        )

    def _world_item_owners(self, item_id: str, field: str) -> List[str]:
        if not item_id:
            return []
        if field == "KnownInfo":
            owners = owners_for_item(self.known_info_owners, item_id)
        else:
            owners = owners_for_item(self.known_secret_owners, item_id)
        raw = self.owner_sort_var.get() if hasattr(self, "owner_sort_var") else self.main_sort_var.get()
        mode = sort_key_from_label(raw)
        return self._sorted_character_displays(mode, False, owners)

    def _refresh_owned_lists(self):
        if not hasattr(self, "world_owner_list"):
            return
        # Preserve scroll position + selection so add/remove doesn't jump the
        # list to the top or drop the highlighted owners.
        top = self.world_owner_list.yview()[0]
        prev_owner_sel = {self.world_owner_list.get(i)
                          for i in self.world_owner_list.curselection()}
        self.world_owner_list.delete(0, tk.END)
        ctx = self._selected_owner_context()
        if not ctx:
            self.world_owner_list.insert(tk.END, tr("（請先選擇公開訊息或秘密）"))
            if hasattr(self, "owner_source_var"):
                self.owner_source_var.set(tr("清單來源：未選擇"))
            return

        _kind, item_id, field, label = ctx
        owners = self._world_item_owners(item_id, field)
        if hasattr(self, "owner_source_var"):
            self.owner_source_var.set(tr("清單來源：{label} / {iid} / {n} 位").format(label=label, iid=item_id, n=len(owners)))
        for name in owners:
            self.world_owner_list.insert(tk.END, self._display_label(name, star=True))
        if not owners:
            self.world_owner_list.insert(tk.END, tr("（目前無擁有者）"))
        if prev_owner_sel:
            for i in range(self.world_owner_list.size()):
                if self.world_owner_list.get(i) in prev_owner_sel:
                    self.world_owner_list.selection_set(i)
        self.world_owner_list.yview_moveto(top)

    def _update_world_preview(self):
        if self.selected_info_index is not None and 0 <= self.selected_info_index < len(self.world_info_items):
            self.world_info_preview.load(self.world_info_items[self.selected_info_index])
        else:
            self.world_info_preview.load_text(tr("請在左側上方列表選擇公開訊息條目"))

        if self.selected_secret_index is not None and 0 <= self.selected_secret_index < len(self.world_secrets_items):
            self.world_secret_preview.load(self.world_secrets_items[self.selected_secret_index])
        else:
            self.world_secret_preview.load_text(tr("請在左側下方列表選擇秘密條目"))

        self._refresh_owned_lists()

    def _applicable_npc_picker(self, parent, defaults: List[str], grid_row: int,
                               grid_col: int, per_row: int = 0):
        opts = ["all", "lords", "companions", "faction_leaders", "village_notables", "merchants"]
        labels = {
            "all": tr("全部"),
            "lords": tr("領主"),
            "companions": tr("同伴"),
            "faction_leaders": tr("勢力領袖"),
            "village_notables": tr("村莊要人"),
            "merchants": tr("商人"),
        }
        vars_map = {}
        row = ttk.Frame(parent)
        row.grid(row=grid_row, column=grid_col, sticky="w", padx=6, pady=(8, 0))
        for i, name in enumerate(opts):
            v = tk.BooleanVar(value=name in defaults)
            vars_map[name] = v
            cb = ttk.Checkbutton(row, text=labels.get(name, name), variable=v)
            if per_row > 0:
                # Grid-wrap to multiple rows so the block fits a narrow column
                # (the 訊息與秘密 editor's left attribute panel).
                r, c = divmod(i, per_row)
                cb.grid(row=r, column=c, sticky="w", padx=6, pady=1)
            else:
                cb.pack(side=tk.LEFT, padx=6)
        return vars_map

    def _save_npc_groups(self):
        save_presets(self.npc_groups_path, {"groups": self.npc_groups})

    def _sorted_names_with_favorites(self, names: List[str]) -> List[str]:
        return sorted(names, key=lambda n: (n not in self.favorites, n.lower()))

    def _open_world_item_editor(self, kind: str, mode: str, idx: Optional[int] = None):
        open_world_item_editor_dialog(self, kind, mode, idx)

    def create_world_item(self, kind: str):
        if not self.world_edit_mode_var.get():
            messagebox.showinfo(tr("訊息與秘密"), tr("目前為預覽模式，請先開啟編輯模式"))
            return
        self._open_world_item_editor(kind, "create")

    def edit_world_item(self, kind: str):
        if not self.world_edit_mode_var.get():
            messagebox.showinfo(tr("訊息與秘密"), tr("目前為預覽模式，請先開啟編輯模式"))
            return
        idx = self.selected_info_index if kind == "info" else self.selected_secret_index
        self._open_world_item_editor(kind, "edit", idx)

    def delete_world_item(self, kind: str):
        if not self.world_edit_mode_var.get():
            messagebox.showinfo(tr("訊息與秘密"), tr("目前為預覽模式，請先開啟編輯模式"))
            return
        is_info = kind == "info"
        items = self.world_info_items if is_info else self.world_secrets_items
        idx = self.selected_info_index if is_info else self.selected_secret_index
        if idx is None or idx >= len(items):
            messagebox.showwarning(tr("移除"), tr("請先選擇條目"))
            return

        item = items[idx]
        item_id = item.get("id", "")

        confirm_win = tk.Toplevel(self.root)
        confirm_win.title(tr("移除確認"))
        confirm_win.geometry("520x220")
        confirm_win.resizable(False, False)
        self._center_window(confirm_win, 520, 220)
        confirm_win.transient(self.root)
        confirm_win.grab_set()

        field = "KnownInfo" if is_info else "KnownSecrets"
        remove_from_npc_var = tk.BooleanVar(value=True)

        msg = tr("確定移除條目：{iid}\n類型：{kind}").format(
            iid=item_id, kind=tr('公開訊息') if is_info else tr('秘密'))
        ttk.Label(confirm_win, text=msg, justify="left").pack(anchor="w", padx=16, pady=(16, 10))
        ttk.Checkbutton(
            confirm_win,
            text=tr("從已使用 NPC 中移除該資訊/秘密"),
            variable=remove_from_npc_var,
        ).pack(anchor="w", padx=16, pady=(0, 10))

        tip = tr("勾選後會同步從 NPC 的 {field} 陣列中移除 {iid}。").format(field=field, iid=item_id)
        ttk.Label(confirm_win, text=tip, foreground=tcol("gray")).pack(anchor="w", padx=16)

        def do_delete():
            items.pop(idx)

            removed_count = 0
            if remove_from_npc_var.get():
                for display, pth in self.characters:
                    target_map = self.known_info_owners if field == "KnownInfo" else self.known_secret_owners
                    if item_id in target_map and display in target_map.get(item_id, []):
                        target_map[item_id] = [x for x in target_map.get(item_id, []) if x != display]
                        removed_count += 1

            self._mark_world_dirty(True)
            self._refresh_world_lists()
            if remove_from_npc_var.get():
                self.log(tr("已移除 {item_id}，並從 {removed_count} 位 NPC 的 {field} 移除").format(item_id=item_id, removed_count=removed_count, field=field), "SUCCESS")
            else:
                self.log(tr("已移除 {item_id}（未改動 NPC {field}）").format(item_id=item_id, field=field), "SUCCESS")
            confirm_win.destroy()

        btn_row = ttk.Frame(confirm_win)
        btn_row.pack(fill=tk.X, padx=16, pady=14)
        ttk.Button(btn_row, text=tr("確認移除"), command=do_delete).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_row, text=tr("取消"), command=confirm_win.destroy).pack(side=tk.RIGHT, padx=4)

    def sync_dialogue(self):
        srcp = self._source_path()
        if not srcp:
            messagebox.showwarning(tr("同步"), tr("請選擇來源角色"))
            return
        if self._staged_conflict_block([srcp], tr("同步")):
            return
        targets = self._checked_paths()
        if not targets:
            messagebox.showwarning(tr("同步"), tr("請選擇至少一位目標角色"))
            return
        d = safe_load_json(srcp) or {}
        ch = d.get("ConversationHistory", [])
        if not isinstance(ch, list) or not ch:
            messagebox.showwarning(tr("同步"), tr("來源角色無對話記錄"))
            return
        open_sync_dialog(self, srcp, targets, ch)

    def trim_conversation(self):
        srcp = self._source_path()
        if not srcp:
            messagebox.showwarning(tr("刪減"), tr("請選擇來源角色"))
            return
        if self._staged_conflict_block([srcp], tr("刪減")):
            return
        d = safe_load_json(srcp) or {}
        ch = d.get("ConversationHistory", [])
        if not isinstance(ch, list) or not ch:
            messagebox.showwarning(tr("刪減"), tr("該角色無對話記錄可刪減"))
            return
        open_trim_dialog(self, srcp, ch)

    def _append_to_file(self, path: Path, entries: List[Any]) -> bool:
        if Path(path) in self.doc_staging.pending:
            self.log(tr("跳過 {v0}：有未儲存的暫存變更（請先儲存或取消）").format(v0=Path(path).stem), "WARN")
            return False
        # Rewrite each copied line into the target's own reading perspective
        # (5.0.x: the character's own lines are ``I (名字, `id`): …``). Without
        # this, a source's first-person line would land verbatim in the target
        # and be mis-attributed. Lines without a string_id pass through unchanged.
        target = safe_load_json(path) or {}
        tid = target.get("StringId")
        if tid:
            entries = [convert_line_perspective(e, tid) for e in entries]
        return append_conversation_entries(path, entries, writer=self.safe_write_json_with_backup)

    # ── Preview-area conversation edit callbacks ───────────────────────────

    def _conv_edit_delete(self, checked_indices: List[int]) -> None:
        """Delete checked conversation rows from the currently previewed character."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return
        npc_name = self._get_character_name(path)
        count = len(checked_indices)
        if not messagebox.askyesno(
            tr("警告！"),
            tr("確定要從「{npc_name}」的對話歷史中\n刪除已勾選的 {count} 行嗎？\n（暫存，按右上「儲存」後才寫入檔案）").format(npc_name=npc_name, count=count),
        ):
            return
        d = self._staged_checkout(path)
        ch = d.get("ConversationHistory", [])
        indices_set = set(checked_indices)
        d["ConversationHistory"] = [ch[i] for i in range(len(ch)) if i not in indices_set]
        self._staged_store(path, d, tr("已從「{name}」刪除 {count} 行對話").format(name=npc_name, count=count))

    def _conv_edit_sync_menu(self, checked_indices: List[int], button: tk.Widget) -> None:
        """Show the sync-destination popover ABOVE the 同步 button."""
        from widgets.popover_menu import PopoverMenu
        items = [
            (tr("所有已選角色"),
             lambda: self._conv_edit_sync_all(checked_indices)),
            (tr("從已選角色指定…"),
             lambda: self._conv_edit_sync_pick(checked_indices, from_all=False)),
            (tr("從角色清單指定…"),
             lambda: self._conv_edit_sync_pick(checked_indices, from_all=True)),
        ]
        PopoverMenu(button, items, direction="up").show()

    def _conv_edit_sync_all(self, checked_indices: List[int]) -> None:
        """Sync checked rows to all currently selected characters."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return
        targets = [t for t in self._checked_paths() if t != path]
        if not targets:
            messagebox.showwarning(tr("同步"), tr("請在左側已選角色清單中選取至少一位目標角色"))
            return
        count = len(checked_indices)
        n_targets = len(targets)
        if not messagebox.askyesno(
            tr("確認同步"),
            tr("確定要將已勾選的 {count} 行對話\n同步至所有 {n_targets} 位已選角色嗎？").format(count=count, n_targets=n_targets),
        ):
            return
        self._do_sync(path, checked_indices, targets)

    def _conv_edit_sync_pick(self, checked_indices: List[int], *, from_all: bool) -> None:
        """Open a character picker dialog then sync to chosen targets."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return

        if from_all:
            # All characters from the current sorted list
            candidates = [
                (d, self.plain_to_path[d])
                for d in self._char_display_list
                if d and d in self.plain_to_path and self.plain_to_path[d] != path
            ]
            title = tr("從角色清單指定同步目標")
            show_filter = True
        else:
            # Only currently selected characters
            candidates = [
                (d, self.plain_to_path[d])
                for d in self.selected_displays
                if d in self.plain_to_path and self.plain_to_path[d] != path
            ]
            title = tr("從已選角色指定同步目標")
            show_filter = False

        if not candidates:
            messagebox.showinfo(tr("同步"), tr("沒有可選取的目標角色"))
            return

        self._open_sync_picker(title, candidates, checked_indices, show_filter=show_filter)

    def _open_sync_picker(
        self,
        title: str,
        candidates: list,
        checked_indices: List[int],
        *,
        show_filter: bool,
    ) -> None:
        """Open a character picker Toplevel and sync on confirm."""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("440x480")
        self._center_window(win, 440, 480)
        win.transient(self.root)
        win.grab_set()

        display_names = [d for d, _ in candidates]
        filtered_names: List[str] = list(display_names)

        if show_filter:
            filter_frame = ttk.Frame(win)
            filter_frame.pack(fill=tk.X, padx=10, pady=(10, 4))
            ttk.Label(filter_frame, text="🔍").pack(side=tk.LEFT)
            filter_var = tk.StringVar()
            filter_entry = ttk.Entry(filter_frame, textvariable=filter_var)
            filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        list_frame = ttk.Frame(win)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        lb = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, exportselection=False,
                        yscrollcommand=vsb.set)
        vsb.configure(command=lb.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _rebuild_lb(names: List[str]) -> None:
            lb.delete(0, tk.END)
            for name in names:
                lb.insert(tk.END, name)

        _rebuild_lb(display_names)

        if show_filter:
            def _on_filter(*_):
                kw = filter_var.get().strip().lower()
                filtered = [n for n in display_names if kw in n.lower()] if kw else display_names
                filtered_names.clear()
                filtered_names.extend(filtered)
                _rebuild_lb(filtered)
            filter_var.trace_add("write", _on_filter)

        def _confirm() -> None:
            sel_indices = lb.curselection()
            if not sel_indices:
                messagebox.showwarning(tr("同步"), tr("請選取至少一位目標角色"), parent=win)
                return
            chosen_displays = [filtered_names[i] for i in sel_indices]
            chosen_paths = [
                self.plain_to_path[d] for d in chosen_displays if d in self.plain_to_path
            ]
            source_path = self.plain_to_path.get(self._detail_display)
            self._do_sync(source_path, checked_indices, chosen_paths)
            win.destroy()

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text=tr("確認同步"), command=_confirm,
                   style="warning.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=tr("取消"), command=win.destroy,
                   style="secondary.TButton").pack(side=tk.LEFT)

    def _do_sync(self, source_path, checked_indices: List[int], target_paths: list) -> None:
        """Append checked entries from source to all target paths."""
        if not source_path or not target_paths:
            return
        if self._staged_conflict_block([source_path] + list(target_paths), tr("同步")):
            return
        d = safe_load_json(source_path) or {}
        ch = d.get("ConversationHistory", [])
        entries_to_sync = [ch[i] for i in checked_indices if i < len(ch)]
        if not entries_to_sync:
            return
        ok = 0
        for tp in target_paths:
            if self._append_to_file(tp, entries_to_sync):
                ok += 1
        self.log(tr("已同步 {v0} 行對話至 {ok} 位角色").format(v0=len(entries_to_sync), ok=ok), "SUCCESS")

    def _conv_edit_apply_line(self, index: int, new_text: str,
                              position: Optional[int] = None) -> None:
        """Persist one edited conversation line, optionally moving it (staged).

        The editing UI is the 對話歷史 page's 快速編輯 panel — editing a single
        line used to open a modal dialog, which threw away the list, the
        preview and your scroll position for what is a tiny, frequent edit.

        *position* is the 1-based line number the user wants this line to end up
        at; ``None`` or the current position leaves the order alone.
        """
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path or not new_text:
            return
        doc = self._staged_checkout(path)
        cur = doc.get("ConversationHistory", [])
        if not isinstance(cur, list) or not (0 <= index < len(cur)):
            return
        cur[index] = new_text
        msg = tr("已編輯第 {n} 行對話").format(n=index + 1)
        if position is not None:
            target = max(0, min(int(position) - 1, len(cur) - 1))
            if target != index:
                cur.insert(target, cur.pop(index))
                msg = tr("已編輯第 {n} 行對話並移至第 {m} 行").format(
                    n=index + 1, m=target + 1)
        doc["ConversationHistory"] = cur
        self._staged_store(path, doc, msg)

    def _conv_edit_insert(self, speaker: str, text: str, position: int) -> None:
        """Insert a new conversation entry at the given 1-based position."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return
        # No speaker → write the text verbatim (a pure prompt / narration line,
        # deliberately not attributed to anyone).  compose() also applies the
        # wrapper's own text convention (battle shouts are stored quoted).
        entry = svc_speaker.compose(svc_speaker.parse(speaker) if speaker else None, text)
        d = self._staged_checkout(path)
        ch = d.get("ConversationHistory", [])
        if not isinstance(ch, list):
            ch = []
        insert_idx = max(0, min(position - 1, len(ch)))  # 1-based → 0-based, clamped
        ch.insert(insert_idx, entry)
        d["ConversationHistory"] = ch
        self._staged_store(path, d, tr("已於第 {n} 行插入 1 行對話至「{name}」").format(n=insert_idx + 1, name=self._get_character_name(path)))

    def _conv_edit_replace_all(self, entries: List[str], source: str = "") -> None:
        """Replace the whole ConversationHistory (MD / clipboard import, staged).

        Staged like every other edit, so an import that turns out wrong is one
        「取消」 away — nothing reaches disk until the user saves.
        """
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return
        doc = self._staged_checkout(path)
        old = len(doc.get("ConversationHistory") or [])
        doc["ConversationHistory"] = list(entries)
        self._staged_store(path, doc, tr("已{source}：{old} 行 → {new} 行").format(
            source=source or tr("導入對話"), old=old, new=len(entries)))

    def _conv_edit_patch_lines(self, updates: Dict[int, str], source: str = "") -> None:
        """Overwrite individual lines by index ([#n] clipboard import, staged)."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path or not updates:
            return
        doc = self._staged_checkout(path)
        cur = doc.get("ConversationHistory")
        if not isinstance(cur, list):
            return
        doc["ConversationHistory"] = svc_transfer.apply_patch(cur, updates)
        self._staged_store(path, doc, tr("已{source}：覆蓋 {n} 行").format(
            source=source or tr("導入對話"), n=len(updates)))

    # ── Memory page callbacks (5.0.5+ dual-track; staged write + reload) ──────

    def _memory_target_path(self) -> Optional[Path]:
        display = self._detail_display
        return self.plain_to_path.get(display) if display else None

    def _memory_entry_save(self, index: Optional[int], fields: dict) -> None:
        """Add (index None) or update a ``Memories[]`` book entry."""
        path = self._memory_target_path()
        if not path:
            return
        d = self._staged_checkout(path)
        mems = d.get("Memories")
        if not isinstance(mems, list):
            mems = []
        fields = dict(fields)
        stem = fields.pop("_image_stem", "")
        if index is None:
            # A memory_images pick reuses its filename stem as the new entry id
            # (so the mod's 記憶之書, which looks up memory_images/<id>.png, finds
            # it).  Cross-region picks (event/dialogue images) keep a fresh uuid
            # id and rely on image_path.
            entry_id = stem or None
            entry = svc_memory.new_memory_entry(
                day=fields.get("campaign_day", 0),
                title=fields.get("title", ""),
                summary=fields.get("summary", ""),
                scene=fields.get("scene", ""),
                image_path=fields.get("image_path", ""), entry_id=entry_id,
            )
            mems.append(entry)
            msg = tr("已新增記憶之書條目")
        elif 0 <= index < len(mems):
            mems[index] = svc_memory.update_memory_entry(mems[index], fields)
            msg = tr("已更新記憶之書條目")
        else:
            return
        d["Memories"] = mems
        self._staged_store(path, d, msg)

    def _memory_entry_delete(self, index: int) -> None:
        path = self._memory_target_path()
        if not path:
            return
        d = self._staged_checkout(path)
        mems = d.get("Memories")
        if isinstance(mems, list) and 0 <= index < len(mems):
            mems.pop(index)
            d["Memories"] = mems
            self._staged_store(path, d, tr("已刪除記憶之書條目"))

    # ── 對話觀察 callback ────────────────────────────────────────────────
    def _observation_delete(self, indices) -> None:
        """Drop the selected DialogueObservations.

        Deleted high index first so the earlier positions stay valid.

        ``ProcessedDialogueObservationHashes`` is deliberately left alone: the
        mod hashes each observation with encrypted separator literals, so we
        cannot tell which hash belongs to which entry — and we don't need to.
        That set is only read to *skip* observations already sent to event
        analysis, so a hash whose observation is gone simply stops matching.
        """
        path = self._memory_target_path()
        if not path:
            return
        if isinstance(indices, int):
            indices = [indices]
        d = self._staged_checkout(path)
        removed = 0
        for i in sorted({int(x) for x in indices}, reverse=True):
            if svc_observation.delete_observation(d, i):
                removed += 1
        if removed:
            self._eaves_index = None          # observations changed
            self._staged_store(path, d,
                               tr("已刪除 {n} 筆對話觀察").format(n=removed))

    # ── 對話輻射（旁聽＋共用）Phase 3a／3a+ ────────────────────────────────
    def _relations_indexes(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """`(eavesdropper_index, sharer_index)`, built from effective data and
        cached until any character write invalidates it (`_eaves_index = None`).

        Both are built in one scan.  The cost is the file read (~0.1s campaign-
        wide); the caller runs it off the critical path (see `_schedule_conv_relations`).
        """
        camp = str(self.campaign_dir) if self.campaign_dir else ""
        if self._eaves_index is not None and self._eaves_index_camp == camp:
            return self._eaves_index
        items = []
        for path in self.plain_to_path.values():
            try:
                data = self._staging_effective(path)
            except Exception:
                data = None
            if isinstance(data, dict):
                items.append((str(path), data))
        self._eaves_index = (svc_radiation.build_index(items),
                             svc_radiation.build_share_index(items))
        self._eaves_index_camp = camp
        return self._eaves_index

    def _schedule_conv_relations(self, path) -> None:
        """Compute 旁聽／共用 counts off the visible reload path.

        The list renders immediately; a moment later the badges fill in.  A
        monotonic token drops stale results when the user switches fast.
        """
        self._conv_rel_token = getattr(self, "_conv_rel_token", 0) + 1
        tok = self._conv_rel_token
        self.root.after_idle(lambda: self._refresh_conv_relations(path, tok))

    def _refresh_conv_relations(self, path, tok) -> None:
        if tok != getattr(self, "_conv_rel_token", 0):
            return
        display = self._detail_display
        if not display or self.plain_to_path.get(display) != path:
            return
        try:
            data = self._staging_effective(path)
            ch = data.get("ConversationHistory") if isinstance(data, dict) else None
            if not isinstance(ch, list):
                return
            eaves_idx, share_idx = self._relations_indexes()
            key = str(path)
            eaves = svc_radiation.line_eaves_counts(ch, data, eaves_idx, viewer_key=key)
            share = svc_radiation.line_share_counts(ch, share_idx, viewer_key=key)
            if hasattr(self, "conversation_viewer"):
                self.conversation_viewer.set_relation_counts(eaves, share)
        except Exception:
            pass

    def _rag_status_for(self, campaign_dir, data) -> str:
        """RAG index state for the 對話歷史 header (a per-character, whole-CH index).

        ``indexed`` — an index file exists; ``stale`` — a 6.0 campaign (has a
        ``rag/`` dir) but this character's index was cleared and will rebuild on
        load; ``none`` — no ``rag/`` dir at all (pre-6.0 / never indexed).
        """
        try:
            sid = str(data.get("StringId") or "") if isinstance(data, dict) else ""
            rag_dir = Path(campaign_dir) / svc_rag.RAG_DIR_NAME
            if not rag_dir.exists():
                return "none"
            return "indexed" if svc_rag.has_rag_index(campaign_dir, sid) else "stale"
        except Exception:
            return "none"

    def _viewed_ch_line(self, line_index: int):
        """`(path, line)` for the shown character's line, or `(None, None)`."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return None, None
        data = self._staging_effective(path)
        ch = data.get("ConversationHistory") if isinstance(data, dict) else None
        if not isinstance(ch, list) or not (0 <= line_index < len(ch)):
            return None, None
        return path, ch[line_index]

    def _conv_view_eavesdroppers(self, line_index: int) -> None:
        """右鍵〔查看旁聽者〕— eavesdropper list for one line."""
        path, line = self._viewed_ch_line(line_index)
        if path is None:
            return
        data = self._staging_effective(path)
        eaves_idx, _ = self._relations_indexes()
        evs = svc_radiation.eavesdroppers_for_line(line, data, eaves_idx, exclude_key=str(path))
        from dialogs.relations_dialog import open_eavesdropper_dialog
        open_eavesdropper_dialog(
            self, line_no=line_index + 1, line_text=str(line), eavesdroppers=evs,
            on_add=self._relations_add_locked, on_clean=self._eaves_clean,
            display_for=lambda key: self.path_to_plain.get(Path(key)))

    def _conv_view_sharers(self, line_index: int) -> None:
        """〔查看共用者〕— characters holding the same line content."""
        path, line = self._viewed_ch_line(line_index)
        if path is None:
            return
        _, share_idx = self._relations_indexes()
        shs = svc_radiation.sharers_for_line(line, share_idx, exclude_key=str(path))
        from dialogs.relations_dialog import open_sharer_dialog
        open_sharer_dialog(
            self, line_no=line_index + 1, line_text=str(line), sharers=shs,
            on_add=self._relations_add_locked, on_clean=self._share_clean,
            display_for=lambda key: self.path_to_plain.get(Path(key)))

    def _conv_clear_eavesdroppers(self, line_indices) -> None:
        """〔清空旁聽者〕— clean every eavesdropper of the selected line(s)."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return
        data = self._staging_effective(path)
        ch = data.get("ConversationHistory") if isinstance(data, dict) else None
        if not isinstance(ch, list):
            return
        eaves_idx, _ = self._relations_indexes()
        # {listener_key: {utterance_id, …}} across all chosen lines
        targets: Dict[str, set] = {}
        for i in line_indices:
            if 0 <= i < len(ch):
                for e in svc_radiation.eavesdroppers_for_line(
                        ch[i], data, eaves_idx, exclude_key=str(path)):
                    targets.setdefault(e.listener_key, set()).add(e.utterance_id)
        total = sum(len(u) for u in targets.values())
        if not total:
            messagebox.showinfo(tr("清空旁聽者"),
                                tr("選取的對話行沒有偵測到旁聽者。"), parent=self.root)
            return
        if not messagebox.askyesno(
            tr("清空旁聽者"),
            tr("確定要清空 {lines} 行對話、共 {n} 位角色的旁聽嗎？\n"
               "會移除他們的對話觀察，以及（若仍在）對話歷史中的旁聽行。\n"
               "（暫存，按右上「儲存」後才寫入檔案）").format(
                   lines=len(line_indices), n=len(targets))):
            return
        cleaned = 0
        for key, utts in targets.items():
            for utt in utts:
                res = self._eaves_clean(key, utt, refresh=False)
                if res.get("observations") or res.get("history"):
                    cleaned += 1
        self._eaves_index = None
        if self._detail_display:
            try:
                self._load_character_detail(self._detail_display)
            except Exception:
                pass
        self.log(tr("已清空 {n} 筆旁聽").format(n=cleaned), "INFO")

    def _relations_add_locked(self, keys) -> int:
        """Add related characters (by file-path key) to the selected list, locked."""
        displays = []
        for k in keys:
            d = self.path_to_plain.get(Path(k))
            if d and d not in displays:
                displays.append(d)
        if not displays:
            return 0
        self.selected_displays |= set(displays)
        self._locked_displays |= set(displays)
        self._rebuild_list()
        self._update_selected_listbox()
        self.log(tr("已將 {n} 位角色加入已選角色清單（已鎖定）").format(n=len(displays)), "INFO")
        return len(displays)

    def _eaves_clean(self, key, utterance_id: str, *, refresh: bool = True) -> Dict[str, int]:
        """Clean one listener's trace of an utterance (staged write to their file)."""
        path = Path(key)
        d = self._staged_checkout(path)
        res = svc_radiation.clean_eavesdropper(d, utterance_id)
        if res.get("observations") or res.get("history"):
            name = self._get_character_name(path)
            self._staged_store(path, d, tr("已清理「{name}」的旁聽（觀察 {o}、對話 {h}）").format(
                name=name, o=res["observations"], h=res["history"]))
            self._eaves_index = None          # observations changed → index stale
            if refresh and self._detail_display:
                try:
                    self._load_character_detail(self._detail_display)
                except Exception:
                    pass
        return res

    def _share_clean(self, key, content: str) -> Dict[str, int]:
        """Remove one character's copy of a shared line (staged write)."""
        path = Path(key)
        d = self._staged_checkout(path)
        res = svc_radiation.clean_sharer(d, content)
        if res.get("observations") or res.get("history"):
            name = self._get_character_name(path)
            self._staged_store(path, d, tr("已移除「{name}」的共用對話（對話 {h}、觀察 {o}）").format(
                name=name, h=res["history"], o=res["observations"]))
            self._eaves_index = None          # CH/observations changed → index stale
            if self._detail_display:
                try:
                    self._load_character_detail(self._detail_display)
                except Exception:
                    pass
        return res

    # ── Owned info / secrets / events callbacks (Stage C: buffered staging) ─────
    # Dispatch table: kind → (json_field, owner_map_attr_or_None, display_label)
    _OWNED_KIND_DISPATCH: Dict[str, Tuple[str, Optional[str], str]] = {
        "info":           ("KnownInfo",     "known_info_owners",   "訊息"),  # noqa: cjk
        "secrets":        ("KnownSecrets",  "known_secret_owners", "秘密"),  # noqa: cjk
        "dynamic_events": ("DynamicEvents", None,                  "事件"),  # noqa: cjk
    }

    def _owned_field_for_kind(self, kind: str) -> Optional[str]:
        d = self._OWNED_KIND_DISPATCH.get(kind)
        return d[0] if d else None

    # ── Doc staging helpers (v0.36.0 主工作區暫存機制) ─────────────────────────

    def _staged_checkout(self, path) -> dict:
        """Working copy for *path* — mutate it, then call _staged_store."""
        return self.doc_staging.checkout(path, safe_load_json)

    def _staging_effective(self, path) -> dict:
        """Read-only effective view: staged working copy if any, else disk."""
        return self.doc_staging.peek(path, safe_load_json)

    def _staged_store(self, path, doc: dict, msg: str = "") -> bool:
        """Register *doc* as the staged state and refresh the UI (no disk write)."""
        p = Path(path)
        self.doc_staging.put(p, doc, safe_load_json)
        self.doc_staging.prune_clean()
        # Any staged edit can change a character's CH or observations, which the
        # campaign-wide 旁聽／共用 index is built from — drop it so it rebuilds.
        self._eaves_index = None
        if msg:
            self.log(tr("{msg}（暫存，儲存後寫入）").format(msg=msg), "INFO")
        display = getattr(self, "_detail_display", None)
        if display and self.plain_to_path.get(display) == p:
            self._load_character_detail(display)
        self._staging_refresh_ui()
        return True

    def _staging_refresh_ui(self) -> None:
        """Sync the top-right global staging bar + selected-list dirty markers."""
        if not hasattr(self, "_staging_var"):
            return
        self.doc_staging.prune_clean()
        n = len(self.doc_staging.dirty_paths())
        if n > 0:
            self._staging_var.set(tr("● 未儲存 {n} 檔").format(n=n))
            # Order (left→right): status · 取消 · 儲存 — cancel left, confirm right.
            self._staging_label.pack(side=tk.LEFT, padx=(0, 6))
            self._staging_discard_btn.pack(side=tk.LEFT, padx=2)
            self._staging_save_btn.pack(side=tk.LEFT, padx=2)
        else:
            self._staging_var.set("")
            self._staging_label.pack_forget()
            self._staging_save_btn.pack_forget()
            self._staging_discard_btn.pack_forget()
        if hasattr(self, "selected_listbox"):
            self._update_selected_listbox()

    def _staging_commit_all(self, confirm: bool = True) -> bool:
        """Write all staged working copies to disk (💾 儲存).

        *confirm*=True opens the field-level diff review first; False writes
        directly (used by the save option in close/reload guards).
        """
        self.doc_staging.prune_clean()
        paths = self.doc_staging.dirty_paths()
        if not paths:
            return True

        # mtime conflict: the game (or something else) rewrote a file while
        # changes were pending — make the overwrite decision explicit.
        conflicts = self.doc_staging.conflicted_paths()
        if conflicts:
            names = "、".join((self._get_character_name(p) or p.stem) for p in conflicts[:6])
            more = tr("…等 {v0} 檔").format(v0=len(conflicts)) if len(conflicts) > 6 else ""
            if not messagebox.askyesno(
                tr("暫存衝突"),
                tr("下列角色檔案在暫存期間被外部（遊戲）修改：\n{names}{more}\n\n仍要以工具中的暫存版本覆蓋嗎？\n（選「否」則中止儲存，暫存保留）").format(names=names, more=more),
                parent=self.root,
            ):
                return False

        def _do_write() -> bool:
            self._auto_backup_campaign(tr("儲存暫存變更"))
            results = self.doc_staging.commit_all(self.safe_write_json_with_backup)
            errs = {p: e for p, e in results.items() if e}
            ok_n = len(results) - len(errs)
            if ok_n:
                self.log(tr("已儲存暫存變更：{ok_n} 個角色檔案").format(ok_n=ok_n), "SUCCESS")
            for p, e in errs.items():
                self.log(tr("儲存失敗 → {v0}: {e}").format(v0=p.name, e=e), "ERROR")
            # Owned lists may have changed on disk → refresh owner maps.
            self._owned_rebuild_owner_map("info")
            self._owned_rebuild_owner_map("secrets")
            display = getattr(self, "_detail_display", None)
            if display:
                self._load_character_detail(display)
            self._staging_refresh_ui()
            if errs:
                messagebox.showerror(
                    tr("儲存"),
                    tr("{v0} 個檔案寫入失敗（暫存保留，可重試）。詳見記錄。").format(v0=len(errs)),
                    parent=self.root)
            return not errs

        if confirm:
            diff = self.doc_staging.diff_all(
                lambda p: self._get_character_name(p) or p.stem)
            from dialogs.staging_commit_dialog import open_staging_commit_dialog
            open_staging_commit_dialog(self, diff, on_confirm=_do_write)
            return True
        return _do_write()

    def _staging_discard_all(self) -> None:
        """Drop every staged working copy (↩ 取消)."""
        self.doc_staging.prune_clean()
        n = len(self.doc_staging.dirty_paths())
        if n == 0:
            return
        if not messagebox.askyesno(
            tr("取消暫存"),
            tr("確定要丟棄 {n} 個角色檔案的暫存變更嗎？").format(n=n),
            parent=self.root,
        ):
            return
        self.doc_staging.discard()
        self.log(tr("已丟棄所有暫存變更"), "WARN")
        display = getattr(self, "_detail_display", None)
        if display:
            self._load_character_detail(display)
        self._staging_refresh_ui()

    def _staging_guard(self, action_name: str) -> bool:
        """Save/discard/cancel prompt for staged docs before reload-type actions.

        Returns True when it's safe to proceed.
        """
        self.doc_staging.prune_clean()
        n = len(self.doc_staging.dirty_paths())
        if n == 0:
            return True
        choice = self._ask_save_discard_cancel(
            tr("{action_name} — 有未儲存的暫存變更").format(action_name=action_name),
            tr("目前有 {n} 個角色檔案的暫存變更尚未儲存。\n\n如何處理？").format(n=n),
        )
        if choice == "save":
            return self._staging_commit_all(confirm=False)
        if choice == "discard":
            self.doc_staging.discard()
            self.log(tr("已丟棄所有暫存變更"), "WARN")
            self._staging_refresh_ui()
            return True
        return False

    def _staged_conflict_block(self, paths, action_name: str) -> bool:
        """Block an immediate-write operation whose targets have staged changes.

        Immediate multi-file tools (同步/寫入劇情/重置/批量清空/載入群聊) write
        straight to disk; letting them run on a staged character would fork the
        state.  Returns True (= blocked) after telling the user what to do.
        """
        self.doc_staging.prune_clean()
        hits = [Path(p) for p in paths if Path(p) in self.doc_staging.pending]
        if not hits:
            return False
        names = "、".join((self._get_character_name(p) or p.stem) for p in hits[:5])
        more = tr("…等 {v0} 位").format(v0=len(hits)) if len(hits) > 5 else ""
        messagebox.showwarning(
            tr(action_name),
            tr("下列角色有未儲存的暫存變更：\n{names}{more}\n\n請先於右上角「儲存」或「取消」暫存，再執行此操作。").format(names=names, more=more),
            parent=self.root)
        return True

    # ── Cross-cutting unsaved-changes guards ──────────────────────────────────

    def _has_any_disease_pending(self) -> bool:
        return bool(getattr(self, "disease_pending", []))

    def _ask_save_discard_cancel(self, title: str, message: str) -> str:
        """Modal 3-option dialog. Returns 'save' | 'discard' | 'cancel'."""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
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
        # Order (left→right): 回去(cancel) · 丟棄(discard) · 儲存(save) — cancel
        # left, confirm right, per the tool-wide button convention.
        ttk.Button(btn, text=tr("↩ 回去"), command=lambda: _set("cancel"),
                   style="secondary.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(btn, text=tr("🗑 丟棄"), command=lambda: _set("discard"),
                   style="danger.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(btn, text=tr("💾 儲存"), command=lambda: _set("save"),
                   style="success.TButton").pack(side=tk.LEFT, padx=4)
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.wait_window()
        return result["choice"]

    def _confirm_discard_all_pending(self, action_name: str) -> bool:
        """Prompt about ALL pending changes (staged docs + disease + dyn events).  Used by app close."""
        self.doc_staging.prune_clean()
        doc_n     = len(self.doc_staging.dirty_paths())
        disease_n = self._disease_pending_count()
        dyn_n     = self._dyn_pending_count() if hasattr(self, "_dyn_pending_count") else 0
        world_dirty = bool(getattr(self, "world_dirty", False))
        total = doc_n + disease_n + dyn_n + (1 if world_dirty else 0)
        if total == 0:
            return True
        parts = []
        if doc_n:     parts.append(tr("主工作區角色檔案 {n} 檔").format(n=doc_n))
        if disease_n: parts.append(tr("疾病 {n} 筆").format(n=disease_n))
        if dyn_n:     parts.append(tr("動態事件 {n} 筆").format(n=dyn_n))
        if world_dirty: parts.append(tr("訊息與秘密（未儲存變更）"))
        choice = self._ask_save_discard_cancel(
            tr("{action} — 有未儲存的變更").format(action=action_name),
            tr("目前有尚未儲存的暫存變更：\n  • {items}\n\n如何處理？").format(
                items="\n  • ".join(parts)),
        )
        if choice == "cancel":
            return False
        if choice == "save":
            ok = True
            if doc_n and not self._staging_commit_all(confirm=False):
                ok = False
            if disease_n and not self._disease_commit(confirm=False):
                ok = False
            if dyn_n and not self._dyn_commit(confirm=False):
                ok = False
            if world_dirty:
                try:
                    self.save_world_changes(confirm=False)   # direct write, no dialog
                except Exception as exc:
                    self.log(tr("訊息與秘密儲存失敗：{exc}").format(exc=exc), "ERROR")
                    ok = False
            return ok
        if choice == "discard":
            self.doc_staging.discard()
            self.disease_pending.clear()
            self._disease_refresh_action_bar()
            self.dyn_events_pending = self._dyn_empty_pending()
            if hasattr(self, "_dyn_tab"):
                refresh_dynamic_events_tab(self)
            if world_dirty:
                self.cancel_world_changes()     # reload world data = discard
            self.log(tr("已丟棄所有暫存變更"), "WARN")
            return True
        return False

    def _owned_stage_add(self, item_ids: List[str], kind: str) -> None:
        """Stage adding *item_ids* to the current character's list (staged doc).

        No disk write; the global 💾 儲存 (top-right) commits.
        """
        display = self._detail_display
        path    = self.plain_to_path.get(display) if display else None
        field   = self._owned_field_for_kind(kind)
        if not path or not field:
            return
        doc = self._staged_checkout(path)
        arr = [str(x) for x in doc.get(field, [])] if isinstance(doc.get(field), list) else []
        existing = set(arr)
        for iid in item_ids:
            s = str(iid).strip()
            if s and s not in existing:
                arr.append(s)
                existing.add(s)
        doc[field] = arr
        self.doc_staging.prune_clean()
        self._staging_refresh_ui()
        self._refresh_owned_viewer_for_kind(kind)

    def _owned_stage_remove(self, item_id: str, kind: str) -> None:
        """Toggle *item_id* in the staged list: present → remove（暫存移除／
        取消暫存新增）; absent but on the baseline → restore（↩ 復原）."""
        display = self._detail_display
        path    = self.plain_to_path.get(display) if display else None
        field   = self._owned_field_for_kind(kind)
        if not path or not item_id or not field:
            return
        doc = self._staged_checkout(path)
        arr = [str(x) for x in doc.get(field, [])] if isinstance(doc.get(field), list) else []
        s = str(item_id)
        if s in arr:
            arr = [x for x in arr if x != s]
        else:
            base = self.doc_staging.base.get(Path(path), {})
            base_arr = [str(x) for x in base.get(field, [])] if isinstance(base.get(field), list) else []
            if s in base_arr:
                # Restore in baseline order so committing preserves disk order.
                keep = set(arr) | {s}
                adds = [x for x in arr if x not in set(base_arr)]
                arr = [x for x in base_arr if x in keep] + adds
        doc[field] = arr
        self.doc_staging.prune_clean()
        self._staging_refresh_ui()
        self._refresh_owned_viewer_for_kind(kind)

    def _owned_get_pending(self, kind: str) -> Tuple[set, set]:
        """(adds, removes) for the current character & kind — derived from the
        staged working copy vs its checkout-time baseline."""
        display = self._detail_display
        path    = self.plain_to_path.get(display) if display else None
        field   = self._owned_field_for_kind(kind)
        if not path or not field:
            return (set(), set())
        p = Path(path)
        staged = self.doc_staging.pending.get(p)
        if staged is None:
            return (set(), set())
        return svc_list_delta(self.doc_staging.base.get(p, {}), staged, field)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _refresh_owned_viewer_for_kind(self, kind: str, *, force_reload: bool = False) -> None:
        """Repaint the relevant OwnedItemsViewer.

        ``force_reload=True`` re-runs ``viewer.load(...)`` to refresh stats;
        otherwise we just update header badges & re-render the staged state.
        """
        viewer_attr = {
            "info":           "owned_info_viewer",
            "secrets":        "owned_secrets_viewer",
            "dynamic_events": "owned_events_viewer",
        }.get(kind)
        viewer = getattr(self, viewer_attr, None) if viewer_attr else None
        if viewer is None:
            return
        if force_reload:
            display = self._detail_display
            if display:
                self._load_character_detail(display)
            else:
                viewer.refresh_pending_visuals()
        else:
            try:
                viewer._render()         # re-render only (re-uses current load state)
            except Exception:
                pass
            viewer.refresh_pending_visuals()

    def _owned_rebuild_owner_map(self, kind: str) -> None:
        """Rebuild the in-memory owner map (info/secrets) for *kind* from disk.

        Called after a commit so the world tab's "owners" view reflects the
        new state.  Dynamic events have no owner map (None in dispatch).
        """
        dispatch = self._OWNED_KIND_DISPATCH.get(kind)
        if not dispatch:
            return
        field, owner_attr, _label = dispatch
        if not owner_attr:
            return
        owner_map: Dict[str, List[str]] = {}
        for display, path in self.plain_to_path.items():
            d = safe_load_json(path) or {}
            arr = d.get(field, [])
            if not isinstance(arr, list):
                continue
            for iid in arr:
                owner_map.setdefault(str(iid), []).append(display)
        for iid in list(owner_map.keys()):
            owner_map[iid] = sorted(set(owner_map[iid]))
        setattr(self, owner_attr, owner_map)

    # ── RecentEvents callbacks (from RecentEventsViewer) ────────────────────────

    def _recent_event_delete(self, checked_indices: List[int]) -> None:
        """Delete RecentEvents at the given indices (sorted descending to keep positions valid)."""
        display = self._detail_display
        path    = self.plain_to_path.get(display) if display else None
        if not path or not checked_indices:
            return
        d = self._staged_checkout(path)
        events = d.get("RecentEvents", [])
        if not isinstance(events, list):
            return
        # Remove from highest index first to preserve positions
        for idx in sorted(checked_indices, reverse=True):
            if 0 <= idx < len(events):
                events.pop(idx)
        d["RecentEvents"] = events
        self._staged_store(path, d, tr("已從「{name}」刪除 {n} 條近期事件").format(name=display, n=len(checked_indices)))

    def _recent_event_clear(self) -> None:
        """Clear all RecentEvents for the currently displayed character."""
        display = self._detail_display
        path    = self.plain_to_path.get(display) if display else None
        if not path:
            return
        d = self._staged_checkout(path)
        count = len(d.get("RecentEvents", []) or [])
        d["RecentEvents"] = []
        self._staged_store(path, d, tr("已清空「{name}」的近期事件（共 {count} 條）").format(name=display, count=count))

    # ── Disease tab callbacks ────────────────────────────────────────────────────

    def _disease_remove(self, instance: dict, refresh: bool = True) -> None:
        """Stage removal of a disease instance (Stage C — buffered).

        Supports BOTH hero (target_type=0) and party (target_type 1/2)
        infections.  ``hero_sid`` in the stage entry is overloaded to mean
        "target id" — kept for backwards compat with assign stages.
        ``target_type`` is recorded so commit-time logic can decide whether
        to also sync a character JSON.

        If *instance* is itself a pending-assign sentinel (op="assign"), the
        click cancels that staged op instead of recording a remove.

        *refresh* — pass False during batch removal (``_disease_remove_selected``)
        so the list repaints once at the end instead of per row.
        """
        if not isinstance(instance, dict):
            return

        def _done() -> None:
            self._disease_refresh_action_bar()
            if refresh:
                refresh_disease_tab(self)

        # If this is a pending-assign sentinel, click means "cancel the assign".
        if instance.get("op") == "assign":
            try:
                self.disease_pending.remove(instance)
            except ValueError:
                pass
            self.log(tr("已取消暫存疾病：{v0} - {v1}").format(v0=instance.get('hero_display',''), v1=instance.get('disease_name','')), "INFO")
            _done()
            return

        target_id = str(instance.get("target_id", ""))
        dis_id    = str(instance.get("disease_id", ""))
        dis_name  = str(instance.get("disease_name", dis_id))
        try:
            target_type = int(instance.get("target_type", 0))
        except (TypeError, ValueError):
            target_type = 0

        # If there's already a pending REMOVE for this combo, undo it (toggle).
        for s in list(self.disease_pending):
            if (s.get("op") == "remove"
                    and s.get("hero_sid") == target_id
                    and s.get("disease_id") == dis_id):
                self.disease_pending.remove(s)
                self.log(tr("已取消暫存移除：{target_id} - {dis_name}").format(target_id=target_id, dis_name=dis_name), "INFO")
                _done()
                return

        # Stage a fresh REMOVE.
        self.disease_pending.append({
            "op":           "remove",
            "hero_sid":     target_id,    # overloaded: any target id
            "target_type":  target_type,
            "disease_id":   dis_id,
            "disease_name": dis_name,
            "hero_display": target_id,
        })
        _done()

    def _disease_remove_selected(self, instances: list) -> None:
        """Bottom-bar batch remove/heal: toggle a remove stage for each row.

        Each row routes through :meth:`_disease_remove` (so existing-instance
        removes, party removes, and pending-assign cancels all behave the same);
        we suppress per-row repaints and refresh once at the end.
        """
        rows = [x for x in (instances or []) if isinstance(x, dict)]
        if not rows:
            return
        for inst in rows:
            self._disease_remove(inst, refresh=False)
        self._disease_refresh_action_bar()
        refresh_disease_tab(self)

    def _disease_assign(self) -> None:
        """Open a dialog to assign a disease to a hero."""
        from ui import msgbox as _mb
        if not self.diseases:
            _mb.showinfo(tr("疾病分配"), tr("尚未載入疾病資料，請先載入戰役。"), parent=self.root)
            return
        if not self.characters:
            _mb.showinfo(tr("疾病分配"), tr("尚未載入角色，請先載入戰役。"), parent=self.root)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(tr("為英雄分配疾病"))
        dlg.grab_set()
        dlg.resizable(False, False)

        ttk.Label(dlg, text=tr("選擇英雄：")).grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        # Exclude heroes already staged for assignment so the same hero can't be
        # added twice (which produced duplicate 暫存新增 rows).
        staged_assign_displays = {
            s.get("hero_display") for s in self.disease_pending
            if s.get("op") == "assign"
        }
        hero_options = [d for d, _ in self.characters if d not in staged_assign_displays]
        if not hero_options:
            dlg.destroy()
            _mb.showinfo(tr("疾病分配"),
                         tr("所有英雄都已在暫存清單中。"), parent=self.root)
            return
        hero_var = tk.StringVar(value=hero_options[0] if hero_options else "")
        hero_cb = ttk.Combobox(dlg, textvariable=hero_var, values=hero_options,
                                state="readonly", width=35)
        hero_cb.grid(row=0, column=1, padx=10, pady=(10, 4))

        ttk.Label(dlg, text=tr("選擇疾病：")).grid(row=1, column=0, padx=10, pady=4, sticky="w")
        dis_options = [d.get("name", d.get("id", "?")) for d in self.diseases]
        dis_var = tk.StringVar(value=dis_options[0] if dis_options else "")
        dis_cb = ttk.Combobox(dlg, textvariable=dis_var, values=dis_options,
                               state="readonly", width=35)
        dis_cb.grid(row=1, column=1, padx=10, pady=4)

        result = {"ok": False}

        def on_ok():
            result["ok"] = True
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.grid(row=2, column=0, columnspan=2, pady=(8, 10))
        ttk.Button(btn_row, text=tr("確定"), command=on_ok,
                   style="warning.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text=tr("取消"), command=dlg.destroy,
                   style="secondary.TButton").pack(side=tk.LEFT, padx=6)

        dlg.wait_window()
        if not result["ok"]:
            return

        hero_display = hero_var.get()
        dis_name_sel = dis_var.get()
        if not hero_display or not dis_name_sel:
            return

        # Resolve selected disease definition
        dis_def = next(
            (d for d in self.diseases if d.get("name", d.get("id")) == dis_name_sel), None
        )
        if not dis_def:
            return

        # Resolve hero StringId
        hero_path = self.plain_to_path.get(hero_display)
        if not hero_path:
            return
        char_data = safe_load_json(hero_path) or {}
        hero_sid = char_data.get("StringId", "") or self.character_meta.get(hero_display, {}).get("StringId", "")

        # Get current campaign days from any loaded character (best effort)
        campaign_days = 0.0
        for d2 in [char_data]:
            if d2.get("LastSeenFriends"):
                vals = list(d2.get("LastSeenFriends", {}).values())
                if vals:
                    campaign_days = max(vals)

        # Stage the assignment instead of writing to disk immediately (Stage C).
        # If a pending REMOVE exists for the same combo, the assign cancels
        # the pair (we just drop the remove, since the existing instance survives).
        for s in list(self.disease_pending):
            if (s.get("op") == "remove"
                    and s.get("hero_sid") == hero_sid
                    and s.get("disease_id") == dis_def.get("id")):
                self.disease_pending.remove(s)
                self.log(
                    tr("取消暫存移除（因再次分配）：{hero_display} - {dis_name_sel}").format(hero_display=hero_display, dis_name_sel=dis_name_sel),
                    "INFO",
                )
                self._disease_refresh_action_bar()
                refresh_disease_tab(self)
                return

        self.disease_pending.append({
            "op":            "assign",
            "hero_sid":      hero_sid,
            "disease_id":    str(dis_def.get("id", "")),
            "disease_name":  dis_name_sel,
            "hero_display":  hero_display,
            "disease_def":   dis_def,
            "campaign_days": campaign_days,
        })
        self._disease_refresh_action_bar()
        refresh_disease_tab(self)
        # Auto-select + scroll to the freshly-staged hero so the user sees it
        # land (overrides the list's scroll-preserve). iid matches disease_tab's
        # pending-assign row key.
        new_iid = f"assign::{hero_sid}::{str(dis_def.get('id', ''))}"
        tv = getattr(self, "_disease_tree", None)
        if tv is not None:
            try:
                if tv.exists(new_iid):
                    tv.selection_set(new_iid)
                    tv.see(new_iid)
                    from ui.disease_tab import _disease_apply_edit_ui
                    _disease_apply_edit_ui(self)
            except tk.TclError:
                pass

    # ── Disease staging commit / discard / UI refresh (Stage C) ─────────────

    def _disease_pending_count(self) -> int:
        return len(getattr(self, "disease_pending", []) or [])

    def _disease_refresh_action_bar(self) -> None:
        """Show / hide the 💾 / ↩ / pending-badge widgets in the disease action bar."""
        n = self._disease_pending_count()
        save_btn   = getattr(self, "_disease_save_btn", None)
        cancel_btn = getattr(self, "_disease_cancel_btn", None)
        pend_lbl   = getattr(self, "_disease_pending_lbl", None)
        pend_var   = getattr(self, "_disease_pending_var", None)
        if pend_var is not None:
            pend_var.set(f" {n} {tr('暫存')} " if n > 0 else "")
        # side=RIGHT cluster (first packed = rightmost): save, cancel, badge →
        # renders left→right as [badge] [取消] [儲存] (status left, confirm right).
        for widget, kwargs_attr in (
            (save_btn,   "_disease_save_btn_pack_kwargs"),
            (cancel_btn, "_disease_cancel_btn_pack_kwargs"),
            (pend_lbl,   "_disease_pending_lbl_pack_kwargs"),
        ):
            if widget is None:
                continue
            try:
                if n > 0:
                    widget.pack(**getattr(self, kwargs_attr, {"side": "right"}))
                else:
                    widget.pack_forget()
            except Exception:
                pass

    def _disease_discard(self) -> None:
        """Drop all pending disease mutations after user confirmation."""
        from ui import msgbox as _mb
        n = self._disease_pending_count()
        if n == 0:
            return
        if not _mb.askyesno(
            tr("確認取消"),
            tr("確定要丟棄這 {n} 個未儲存的疾病變更嗎？").format(n=n),
            parent=self.root,
        ):
            return
        self.disease_pending.clear()
        self.log(tr("已丟棄 {n} 個疾病暫存變更").format(n=n), "WARN")
        self._disease_refresh_action_bar()
        refresh_disease_tab(self)

    def _disease_build_diff_items(self) -> List[Dict[str, Any]]:
        """Preview rows [{name, field, old, new}] for the pending disease ops."""
        rows: List[Dict[str, Any]] = []
        for s in self.disease_pending:
            op = s["op"]
            dname = s.get("disease_name", "")
            if op == "assign":
                rows.append({"name": s.get("hero_display", s.get("hero_sid", "")),
                             "field": tr("＋ 感染"), "old": "", "new": dname})
            elif op == "remove":
                rows.append({"name": s.get("hero_display", s.get("hero_sid", "")),
                             "field": tr("－ 移除"), "old": dname, "new": ""})
            elif op == "clear_infections":
                rows.append({"name": tr("疾病目錄"), "field": tr("🩹 清空病種感染"),
                             "old": dname, "new": ""})
            elif op == "purge_definition":
                rows.append({"name": tr("疾病目錄"), "field": tr("🗑 刪除病種定義"),
                             "old": dname, "new": ""})
        return rows

    def _disease_commit(self, confirm: bool = True) -> bool:
        """Save pending disease changes.

        *confirm*=True opens the field-diff review first (the normal 💾 儲存);
        False writes directly (used by the app-close save-all path, which needs
        a synchronous result).
        """
        if not self.disease_pending:
            return True
        if self._confirm_if_game_running(tr("儲存疾病變更")):
            return False
        if confirm:
            from dialogs.staging_commit_dialog import (
                open_diff_review_dialog, snapshot_purge_option,
            )
            rows = self._disease_build_diff_items()
            _opts, _confirm = snapshot_purge_option(self, self._disease_write)
            open_diff_review_dialog(
                self,
                title=tr("儲存疾病變更"),
                header=tr("以下疾病變更將寫入 disease_instances.json 與相關角色 JSON（寫入前自動備份）："),
                diff_items=rows,
                confirm_label=tr("💾 儲存"),
                on_confirm=_confirm,
                options=_opts,
            )
            return True
        return self._disease_write()

    def _disease_write(self) -> bool:
        """Replay all pending stages on disease_instances + sync each affected hero JSON."""
        from ui import msgbox as _mb
        if not self.disease_pending:
            return True
        n_assign = sum(1 for s in self.disease_pending if s["op"] == "assign")
        n_remove = sum(1 for s in self.disease_pending if s["op"] == "remove")

        # Backup once before mass-write.
        self._auto_backup_campaign(tr("套用疾病變更"))

        # Replay all stages on the in-memory disease_instances list (+ defs).
        # Track which HEROES (target_type=0) need character-JSON sync; party
        # removals don't touch any character JSON.
        new_instances = list(self.disease_instances)
        new_definitions = list(self.diseases)
        affected_heroes: Set[str] = set()
        purged_any = False
        for s in self.disease_pending:
            op          = s["op"]
            target_id   = s.get("hero_sid", "")     # overloaded for parties
            dis_id      = s.get("disease_id", "")
            target_type = int(s.get("target_type", 0) or 0)
            if op == "assign":
                # Assign is hero-only (target_type=0).
                affected_heroes.add(target_id)
                new_instances = svc_assign_hero_disease(
                    new_instances, target_id, s.get("disease_def") or {}, float(s.get("campaign_days", 0.0))
                )
            elif op == "remove":
                # Generic remove: works for heroes AND parties.
                new_instances = svc_remove_disease_instance(new_instances, target_id, dis_id)
                if target_type == 0:
                    affected_heroes.add(target_id)
            elif op in ("clear_infections", "purge_definition"):
                # Catalog-scoped: collect heroes losing an instance (for JSON
                # sync) BEFORE removing, then wipe every infection of dis_id.
                for x in svc_instances_for_disease(new_instances, dis_id):
                    if x.get("target_type") == 0:
                        affected_heroes.add(x.get("target_id", ""))
                new_instances = svc_remove_all_instances_of_disease(new_instances, dis_id)
                if op == "purge_definition":
                    new_definitions = svc_remove_disease_definition(new_definitions, dis_id)
                    purged_any = True

        # Write disease_instances.json (always) + diseases.json (only when a
        # purge changed the catalog).
        campaign = getattr(self, "campaign_dir", None)
        def_path, inst_path = disease_paths_for_app(campaign, self.script_dir)
        try:
            dump_disease_instances(inst_path, new_instances)
        except Exception as exc:
            _mb.showerror(tr("寫入失敗"), str(exc), parent=self.root)
            return False
        self.disease_instances = new_instances
        if purged_any:
            try:
                if not self.safe_write_json_with_backup(def_path, new_definitions):
                    self.log(tr("寫入 diseases.json 失敗"), "ERROR")
                    _mb.showerror(tr("寫入失敗"), "diseases.json", parent=self.root)
                    return False
            except Exception as exc:
                self.log(tr("寫入 diseases.json 失敗：{exc}").format(exc=exc), "ERROR")
                _mb.showerror(tr("寫入失敗"), str(exc), parent=self.root)
                return False
            self.diseases = new_definitions

        # Sync each affected character JSON.
        sync_failures: List[str] = []
        for hero_sid in affected_heroes:
            char_path = self.plain_to_path.get(hero_sid)
            if char_path is None:
                # Try matching by StringId in character_meta.
                for display, meta in self.character_meta.items():
                    if meta.get("StringId") == hero_sid:
                        char_path = self.plain_to_path.get(display)
                        break
            if char_path is None:
                continue
            try:
                char_data = safe_load_json(char_path) or {}
                remaining = instances_for_hero(new_instances, hero_sid)
                svc_sync_character_diseases(char_data, remaining, self.diseases)
                if not self.safe_write_json_with_backup(char_path, char_data):
                    sync_failures.append(hero_sid)
            except Exception as exc:
                self.log(tr("同步角色疾病失敗 → {hero_sid}: {exc}").format(hero_sid=hero_sid, exc=exc), "ERROR")
                sync_failures.append(hero_sid)

        # Clear pending + refresh UI.
        # Count parties that were affected for the success log.
        party_targets = {
            s.get("hero_sid", "") for s in self.disease_pending
            if s.get("op") == "remove" and int(s.get("target_type", 0) or 0) != 0
        }
        self.disease_pending.clear()
        delta = f"+{n_assign}/-{n_remove}"
        if party_targets:
            affected = tr("英雄 {h}、部隊 {p}").format(h=len(affected_heroes), p=len(party_targets))
        else:
            affected = tr("英雄 {h}").format(h=len(affected_heroes))
        self.log(tr("已儲存疾病變更：{delta}（影響 {affected}）").format(delta=delta, affected=affected),
                 "SUCCESS")
        if sync_failures:
            self.log(tr("⚠ {v0} 位英雄角色 JSON 同步失敗：{v1}").format(v0=len(sync_failures), v1=', '.join(sync_failures[:5])), "ERROR")
        self._disease_refresh_action_bar()
        refresh_disease_tab(self)
        if self._detail_display:
            self._load_character_detail(self._detail_display)
        return True

    def _disease_clear_infections_for(self, disease_id: str) -> None:
        """Stage 'clear all infections of this disease' (toggle).

        v0.25.0: no longer writes immediately — buffers a ``clear_infections``
        op so 💾 儲存 / ↩ 取消 cover it like every other disease edit.  Clicking
        the button again cancels the staged op.  The disease *definition* is
        preserved — only its infections are wiped on commit.
        """
        self._disease_stage_catalog_op("clear_infections", disease_id)

    def _disease_purge_definition(self, disease_id: str) -> None:
        """Stage 'delete this disease definition + heal everyone' (toggle).

        v0.25.0: buffered like ``clear_infections`` (see above).  On commit it
        removes the entry from diseases.json AND clears every infection of it.
        """
        self._disease_stage_catalog_op("purge_definition", disease_id)

    def _disease_stage_catalog_op(self, op: str, disease_id: str) -> None:
        """Toggle a catalog-scoped staged op (clear_infections / purge_definition).

        These join the same ``disease_pending`` buffer as assign/remove, so the
        shared 💾 儲存 / ↩ 取消 workflow now covers disease-catalog operations.
        """
        if not disease_id:
            return
        # Toggle off if this exact op is already staged for this disease.
        for s in list(self.disease_pending):
            if s.get("op") == op and s.get("disease_id") == disease_id:
                self.disease_pending.remove(s)
                self.log(tr("已取消暫存目錄操作：{op} - {v0}").format(op=op, v0=s.get('disease_name', disease_id)), "INFO")
                self._disease_refresh_action_bar()
                refresh_disease_tab(self)
                return
        defn = svc_disease_def(self.diseases or [], disease_id)
        dname = defn.get("name", disease_id) if defn else disease_id
        self.disease_pending.append({
            "op": op, "disease_id": disease_id, "disease_name": dname,
        })
        self._disease_refresh_action_bar()
        refresh_disease_tab(self)

    def _disease_clear_all(self) -> None:
        """Wipe diseases.json + disease_instances.json for the current campaign
        and reset every character's IsSick / CurrentDiseases / DiseaseProgress.

        Confirmation required.  A campaign backup is taken first.  Pending
        disease stages are also dropped (they would be invalidated anyway).
        """
        from ui import msgbox as _mb
        if self._confirm_if_game_running(tr("清空所有疾病")):
            return
        campaign = getattr(self, "campaign_dir", None)
        if campaign is None:
            _mb.showinfo(
                tr("清空所有疾病"),
                tr("尚未載入戰役，無法清空。"),
                parent=self.root,
            )
            return

        # Inventory what would be wiped so the prompt is concrete.
        n_def    = len(self.diseases or [])
        all_inst = list(self.disease_instances or [])
        n_hero   = sum(1 for x in all_inst if x.get("target_type") == 0)
        n_party  = sum(1 for x in all_inst if x.get("target_type") in (1, 2))
        pending_n = self._disease_pending_count()

        msg_lines = [
            tr("此操作將 ⚠ 不可逆 地清空當前戰役的疾病資料："),
            "",
            tr("  • diseases.json：{n_def} 筆疾病定義 → 清空").format(n_def=n_def),
            tr("  • disease_instances.json：{n_hero} 位英雄 + {n_party} 個隊伍感染 → 清空").format(n_hero=n_hero, n_party=n_party),
            tr("  • 所有英雄角色 JSON：IsSick / CurrentDiseases / DiseaseProgress 重設為非生病"),
        ]
        if pending_n:
            msg_lines += ["", tr("  ⚠ 目前 {pending_n} 筆暫存疾病變更也將被丟棄。").format(pending_n=pending_n)]
        msg_lines += ["", tr("執行前會自動備份戰役。是否繼續？")]
        if not _mb.askyesno(
            tr("清空所有疾病"), "\n".join(msg_lines),
            parent=self.root, icon="warning",
        ):
            return

        # Backup once.
        self._auto_backup_campaign(tr("清空疾病"))

        def_path, inst_path = disease_paths_for_app(campaign, self.script_dir)

        # Wipe both JSON files (use safe_write_json_with_backup so a per-file
        # backup is also kept).
        wipe_failures: List[str] = []
        for label, path in (("diseases.json", def_path),
                            ("disease_instances.json", inst_path)):
            try:
                if not self.safe_write_json_with_backup(path, []):
                    wipe_failures.append(label)
            except Exception as exc:
                self.log(tr("清空 {label} 失敗：{exc}").format(label=label, exc=exc), "ERROR")
                wipe_failures.append(label)
        if wipe_failures:
            _mb.showerror(
                tr("清空失敗"),
                tr("無法寫入：") + ", ".join(wipe_failures),
                parent=self.root,
            )
            return

        # Reset in-memory state + drop pending stages.
        self.diseases = []
        self.disease_instances = []
        self.disease_pending.clear()

        # Sync every character JSON whose disease fields are non-empty.
        sync_count = 0
        sync_failures: List[str] = []
        for display, char_path in self.plain_to_path.items():
            try:
                char_data = safe_load_json(char_path) or {}
                if not isinstance(char_data, dict):
                    continue
                # Skip already-clean characters to avoid touching their mtime.
                already_clean = (
                    not char_data.get("IsSick")
                    and not char_data.get("CurrentDiseases")
                    and not char_data.get("DiseaseProgress")
                )
                if already_clean:
                    continue
                # sync with empty instance list = clear all disease fields
                svc_sync_character_diseases(char_data, [], [])
                if self.safe_write_json_with_backup(char_path, char_data):
                    sync_count += 1
                else:
                    sync_failures.append(display)
            except Exception as exc:
                self.log(tr("清空時同步角色失敗 → {display}: {exc}").format(display=display, exc=exc), "ERROR")
                sync_failures.append(display)

        self.log(
            tr("已清空所有疾病：定義 -{n_def}, 英雄感染 -{n_hero}, 隊伍感染 -{n_party}, 角色 JSON 同步 {sync_count} 筆").format(n_def=n_def, n_hero=n_hero, n_party=n_party, sync_count=sync_count),
            "SUCCESS",
        )
        if sync_failures:
            self.log(
                tr("⚠ {v0} 位角色同步失敗：{v1}").format(v0=len(sync_failures), v1=', '.join(sync_failures[:5])),
                "ERROR",
            )

        self._disease_refresh_action_bar()
        refresh_disease_tab(self)
        if self._detail_display:
            self._load_character_detail(self._detail_display)

    # ── Dynamic events staging methods (Stage F) ──────────────────────

    @staticmethod
    def _dyn_empty_pending() -> Dict[str, Any]:
        """Fresh diplomacy staging buffer (events + statements + pressure)."""
        return {
            "edits": {}, "delete_ids": set(), "new_events": [],
            "stmt_edits": {}, "stmt_deletes": set(), "stmt_new": [],
            "pressure": None,
        }

    def _dyn_pending_count(self) -> int:
        p = self.dyn_events_pending
        return (len(p.get("delete_ids", set())) + len(p.get("edits", {}))
                + len(p.get("new_events", []))
                + len(p.get("stmt_deletes", set())) + len(p.get("stmt_edits", {}))
                + len(p.get("stmt_new", []))
                + (1 if p.get("pressure") is not None else 0))

    # ── Response-pressure staging (Stage E) ────────────────────────────
    @staticmethod
    def _norm_pressure(pressure: Any) -> Dict[str, Dict[str, Any]]:
        """Normalise a pressure block for stable equality / storage.

        ``PressureByKingdomId`` values → int (drop unparseable); empty-string
        ``ResponseEventIdByKingdom`` assignments dropped."""
        p = pressure if isinstance(pressure, dict) else {}
        raw_pre = p.get("PressureByKingdomId") or {}
        raw_asg = p.get("ResponseEventIdByKingdom") or {}
        pre: Dict[str, int] = {}
        for k, v in raw_pre.items():
            try:
                pre[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        asg = {str(k): str(v) for k, v in raw_asg.items() if str(v or "").strip()}
        return {"PressureByKingdomId": pre, "ResponseEventIdByKingdom": asg}

    def _dyn_stage_pressure(self, pressure: dict) -> None:
        """Stage a full replacement of the response-pressure block.

        Auto-cancels when the edited block equals the on-disk pressure."""
        norm = self._norm_pressure(pressure)
        original = self._norm_pressure(svc_bundle_pressure(self.diplomacy_bundle or {}))
        self.dyn_events_pending["pressure"] = None if norm == original else norm

    def _dyn_clear_pressure_stage(self) -> None:
        self.dyn_events_pending["pressure"] = None

    # ── New-event staging (Stage D) ────────────────────────────────────
    def _dyn_stage_new_event(self, event: dict) -> int:
        """Append a freshly-built event to the new-events buffer; return its index."""
        lst = self.dyn_events_pending.setdefault("new_events", [])
        lst.append(event)
        return len(lst) - 1

    def _dyn_replace_new_event(self, index: int, event: dict) -> None:
        """Overwrite a staged new event in place (editor 'save' for new events)."""
        lst = self.dyn_events_pending.setdefault("new_events", [])
        if 0 <= index < len(lst):
            lst[index] = event

    def _dyn_unstage_new_event(self, index: int) -> None:
        lst = self.dyn_events_pending.setdefault("new_events", [])
        if 0 <= index < len(lst):
            lst.pop(index)

    # ── Statement staging (Stage C) ────────────────────────────────────
    # Keys are diplomacy_service.statement_keys() over the CURRENT on-disk
    # top-level list (app.diplomacy_bundle) — same snapshot the sub-tab shows.

    def _stmt_original_by_key(self, key: str) -> Optional[dict]:
        stmts = svc_bundle_statements(self.diplomacy_bundle or {})
        for k, s in zip(svc_statement_keys(stmts), stmts):
            if k == key:
                return s
        return None

    def _stmt_stage_edit(self, key: str, model: dict) -> None:
        """Stage a full-model edit; auto-cancels when equal to the original."""
        original = self._stmt_original_by_key(key)
        if original is None:
            return
        edits = self.dyn_events_pending.setdefault("stmt_edits", {})
        if svc_serialize_statement(model, embedded=False) == original \
                and not model.get("_embedded_overlay_dirty"):
            edits.pop(key, None)
        else:
            edits[key] = model

    def _stmt_stage_delete(self, key: str) -> None:
        if self._stmt_original_by_key(key) is None:
            return
        self.dyn_events_pending.setdefault("stmt_deletes", set()).add(key)
        self.dyn_events_pending.setdefault("stmt_edits", {}).pop(key, None)

    def _stmt_stage_undelete(self, key: str) -> None:
        self.dyn_events_pending.setdefault("stmt_deletes", set()).discard(key)

    def _stmt_stage_new(self, model: dict) -> None:
        self.dyn_events_pending.setdefault("stmt_new", []).append(model)

    def _stmt_unstage_new(self, index: int) -> None:
        lst = self.dyn_events_pending.setdefault("stmt_new", [])
        if 0 <= index < len(lst):
            lst.pop(index)

    def _dyn_stage_edit(self, event_id: str, field: str, new_value: Any) -> None:
        """Stage an edit to one field of one event.

        Auto-cancels when the edited value equals the on-disk value
        (so toggling back to original removes the staged change).
        """
        if not event_id or field not in DYN_EDITABLE_FIELDS:
            return
        # Find the on-disk event
        event = next((e for e in self.world_dynamic_events_items
                      if str(e.get("id", "")) == event_id), None)
        if event is None:
            return
        original = event.get(field)
        edits_bucket = self.dyn_events_pending["edits"]
        ev_edits = edits_bucket.get(event_id, {})
        # Normalise list-valued fields for equality comparison
        if field in ("kingdoms_involved", "characters_involved",
                     "participating_kingdoms", "applicable_npcs"):
            new_norm = [str(x) for x in (new_value or [])]
            orig_norm = [str(x) for x in (original or [])]
            equal = (new_norm == orig_norm)
            new_value = new_norm
        elif field == "player_involved":
            new_value = bool(new_value)
            equal = (new_value == bool(original))
        elif field == "kingdom_engagement":
            def _norm_eng(d):
                out = {}
                if isinstance(d, dict):
                    for k, v in d.items():
                        try:
                            out[str(k)] = max(0, min(100, int(v)))
                        except (TypeError, ValueError):
                            continue
                return out
            new_value = _norm_eng(new_value)
            equal = (new_value == _norm_eng(original))
        elif field in ("next_statement_attempt_days", "failed_statement_attempts"):
            new_value = dict(new_value) if isinstance(new_value, dict) else {}
            equal = (new_value == (dict(original) if isinstance(original, dict) else {}))
        elif field == "economic_effects":
            def _norm_eco(lst):
                return [svc_normalize_eco_effect(e) for e in lst if isinstance(e, dict)] \
                    if isinstance(lst, list) else []
            new_value = _norm_eco(new_value)
            equal = (new_value == _norm_eco(original))
        elif field == "importance":
            try:
                new_value = max(1, min(9, int(new_value)))
            except (TypeError, ValueError):
                return
            try:
                equal = (int(new_value) == int(original))
            except (TypeError, ValueError):
                equal = False
        elif field == "expiration_campaign_days":
            try:
                new_value = float(new_value)
            except (TypeError, ValueError):
                return
            try:
                equal = (abs(float(new_value) - float(original)) < 1e-9)
            except (TypeError, ValueError):
                equal = False
        elif field == "event_history":
            # Normalise each entry's campaign_days to float and description
            # to str, preserving any other keys, before comparing for equality.
            def _norm_hist(lst):
                out = []
                if not isinstance(lst, list):
                    return out
                for h in lst:
                    if not isinstance(h, dict):
                        continue
                    h2 = dict(h)
                    if "campaign_days" in h2:
                        try:
                            h2["campaign_days"] = float(h2["campaign_days"])
                        except (TypeError, ValueError):
                            pass
                    if "description" in h2:
                        h2["description"] = str(h2["description"])
                    out.append(h2)
                return out
            new_value = _norm_hist(new_value)
            orig_norm = _norm_hist(original)
            equal = (new_value == orig_norm)
        else:
            equal = (str(new_value) == str(original or ""))

        if equal:
            ev_edits.pop(field, None)
            if not ev_edits:
                edits_bucket.pop(event_id, None)
        else:
            ev_edits[field] = new_value
            edits_bucket[event_id] = ev_edits

    def _dyn_stage_delete(self, event_id: str) -> None:
        """Stage deletion of an event (cascades through to NPC JSONs on commit)."""
        if not event_id:
            return
        self.dyn_events_pending["delete_ids"].add(event_id)
        # If the event also had edits staged, drop them — delete supersedes edit.
        self.dyn_events_pending["edits"].pop(event_id, None)

    def _dyn_stage_undelete(self, event_id: str) -> None:
        if not event_id:
            return
        self.dyn_events_pending["delete_ids"].discard(event_id)

    def _dyn_discard(self, *, skip_confirm: bool = False) -> None:
        """Drop all pending dynamic-event mutations."""
        from ui import msgbox as _mb
        n = self._dyn_pending_count()
        if n == 0:
            return
        if not skip_confirm:
            if not _mb.askyesno(
                tr("確認取消"),
                tr("確定要丟棄這 {n} 個未儲存的事件變更嗎？").format(n=n),
                parent=self.root,
            ):
                return
        self.dyn_events_pending = self._dyn_empty_pending()
        self.log(tr("已丟棄 {n} 個動態事件暫存變更").format(n=n), "WARN")
        refresh_dynamic_events_tab(self)

    def _dyn_build_diff_items(self) -> List[Dict[str, Any]]:
        """Preview rows [{name, field, old, new}] for the pending diplomacy changes."""
        p = self.dyn_events_pending
        edits   = p.get("edits", {}) or {}
        deletes = p.get("delete_ids", set()) or set()
        s_edits = p.get("stmt_edits", {}) or {}
        s_dels  = p.get("stmt_deletes", set()) or set()
        s_new   = p.get("stmt_new", []) or []
        n_new   = p.get("new_events", []) or []
        p_pressure = p.get("pressure")
        ev = tr("事件"); st = tr("聲明")
        rows: List[Dict[str, Any]] = []
        for eid in sorted(deletes):
            rows.append({"name": ev, "field": tr("🗑 刪除"), "old": eid, "new": ""})
        for eid, ev_edits in edits.items():
            rows.append({"name": ev, "field": tr("✏ 編輯") + f" {eid[:8]}",
                         "old": "", "new": ", ".join(ev_edits.keys())})
        for e in n_new:
            rows.append({"name": ev, "field": tr("➕ 新增"),
                         "old": "", "new": str(e.get("title") or e.get("id", "?"))})
        for key in sorted(s_dels):
            rows.append({"name": st, "field": tr("🗑 刪除"), "old": key, "new": ""})
        for key in s_edits.keys():
            rows.append({"name": st, "field": tr("✏ 編輯") + f" {key}", "old": "", "new": tr("已修改")})
        for m in s_new:
            rows.append({"name": st, "field": tr("➕ 新增"), "old": "", "new": m.get("kingdom_id", "?")})
        if p_pressure is not None:
            n_pre = len(p_pressure.get("PressureByKingdomId", {}))
            rows.append({"name": tr("回應壓力"), "field": tr("⚖ 更新"),
                         "old": "", "new": f"{n_pre} {tr('王國')}"})
        return rows

    def _dyn_commit(self, confirm: bool = True) -> bool:
        """Apply all pending edits + cascading deletes; write everything atomically.

        *confirm*=True opens the field-diff review first (the normal 💾 儲存);
        False writes directly (app-close save-all path, needs a sync result).
        Returns True iff every affected file wrote successfully.
        """
        from ui import msgbox as _mb
        if self._dyn_pending_count() == 0:
            return True
        if self._confirm_if_game_running(tr("儲存動態事件變更")):
            return False

        # Bundle-format validation must happen before we offer to save.
        p = self.dyn_events_pending
        has_stmt_changes = bool(p.get("stmt_edits") or p.get("stmt_deletes") or p.get("stmt_new"))
        has_bundle_only_changes = has_stmt_changes or (p.get("pressure") is not None)
        if has_bundle_only_changes and not isinstance(self.diplomacy_bundle, dict):
            _mb.showerror(tr("無法儲存"),
                          tr("聲明／壓力變更需要 5.0.x 外交包，目前戰役為舊版格式。"),
                          parent=self.root)
            return False

        if confirm:
            from dialogs.staging_commit_dialog import (
                open_diff_review_dialog, snapshot_purge_option,
            )
            _opts, _confirm = snapshot_purge_option(self, self._dyn_write)
            open_diff_review_dialog(
                self,
                title=tr("儲存動態事件變更"),
                header=tr("以下動態事件／聲明變更將寫入（刪除事件會一併清除 NPC JSON 中的引用；寫入前自動備份）："),
                diff_items=self._dyn_build_diff_items(),
                confirm_label=tr("💾 儲存"),
                on_confirm=_confirm,
                options=_opts,
            )
            return True
        return self._dyn_write()

    def _dyn_write(self) -> bool:
        """Write all staged diplomacy changes atomically. Returns True on full success."""
        from ui import msgbox as _mb
        edits:    Dict[str, dict] = self.dyn_events_pending.get("edits", {}) or {}
        deletes:  Set[str]        = self.dyn_events_pending.get("delete_ids", set()) or set()
        s_edits:  Dict[str, dict] = self.dyn_events_pending.get("stmt_edits", {}) or {}
        s_dels:   Set[str]        = self.dyn_events_pending.get("stmt_deletes", set()) or set()
        s_new:    List[dict]      = self.dyn_events_pending.get("stmt_new", []) or []
        n_new:    List[dict]      = self.dyn_events_pending.get("new_events", []) or []
        p_pressure: Optional[dict] = self.dyn_events_pending.get("pressure")
        has_stmt_changes = bool(s_edits or s_dels or s_new)
        is_bundle = isinstance(self.diplomacy_bundle, dict)

        # Backup once before mass-write
        self._auto_backup_campaign(tr("套用動態事件變更"))

        campaign = getattr(self, "campaign_dir", None)
        de_path  = dynamic_events_path_for_app(campaign, self.script_dir)
        new_bundle: Optional[dict] = None

        if is_bundle:
            # 1) Statements first (keys refer to the pre-change list); twin
            #    updates land on the bundle's event objects.
            nb, stmt_summary = svc_apply_statement_changes(
                self.diplomacy_bundle, edits=s_edits, deletes=s_dels, new=s_new)
            # 1b) Apply staged response-pressure BEFORE the delete cascade, so the
            #     cascade also clears assignments pointing at deleted events.
            if p_pressure is not None:
                nb = svc_replace_pressure(nb, p_pressure)
            # 2) Event-delete cascade on bundle-level references.
            nb, casc = svc_remove_events_cascade(nb, deletes)
            # 3) Event edits/deletes on the (twin-updated) bundle events.
            new_events = []
            for ev in nb.get("dynamic_events", []) or []:
                eid = str(ev.get("id", ""))
                if eid in deletes:
                    continue
                if eid in edits:
                    new_events.append(svc_apply_event_edits(ev, edits[eid]))
                else:
                    new_events.append(ev)
            # 4) Append freshly-created events (Stage D).
            new_events.extend(n_new)
            try:
                ok = svc_write_bundle_update(
                    de_path,
                    writer=self.safe_write_json_with_backup,
                    loader=safe_load_json,
                    events=new_events,
                    statements=nb.get("kingdom_statements", []),
                    pressure=nb.get("kingdom_response_pressure"),
                )
            except Exception as exc:
                _mb.showerror(tr("寫入失敗"), str(exc), parent=self.root)
                return False
            if not ok:
                _mb.showerror(tr("寫入失敗"),
                              tr("無法寫入 {v0}，操作已中止。").format(v0=de_path.name),
                              parent=self.root)
                return False
            new_bundle = dict(nb)
            new_bundle["dynamic_events"] = new_events
            if casc.get("statements_removed") or casc.get("pressure_cleared"):
                self.log(tr("事件刪除串聯：移除 {v0} 筆關聯聲明、清除 {v1} 個壓力指派").format(v0=casc['statements_removed'], v1=len(casc['pressure_cleared'])), "INFO")
            if stmt_summary.get("missing_event"):
                self.log(tr("⚠ 部分聲明指向不存在的事件：{ids}").format(
                    ids=", ".join(sorted(set(stmt_summary['missing_event']))[:3])), "WARNING")
        else:
            # 4.1.0 legacy: bare-array dynamic_events.json (events only).
            new_events = []
            for ev in self.world_dynamic_events_items:
                eid = str(ev.get("id", ""))
                if eid in deletes:
                    continue
                if eid in edits:
                    new_events.append(svc_apply_event_edits(ev, edits[eid]))
                else:
                    new_events.append(ev)
            new_events.extend(n_new)
            try:
                if not svc_write_dynamic_events(
                    de_path, new_events,
                    writer=self.safe_write_json_with_backup,
                    loader=safe_load_json,
                ):
                    _mb.showerror(tr("寫入失敗"),
                                  tr("無法寫入 {v0}，操作已中止。").format(v0=de_path.name),
                                  parent=self.root)
                    return False
            except Exception as exc:
                _mb.showerror(tr("寫入失敗"), str(exc), parent=self.root)
                return False

        # Cascade-clean NPC JSONs that reference deleted events
        cascade_cleaned: List[str] = []
        cascade_failed:  List[str] = []
        if deletes:
            for display, path in self.plain_to_path.items():
                try:
                    char_data = safe_load_json(path) or {}
                    refs = char_data.get("DynamicEvents", [])
                    if not isinstance(refs, list):
                        continue
                    if not any(str(r) in deletes for r in refs):
                        continue
                    cleaned = svc_clean_char_event_refs(char_data, deletes)
                    if self.safe_write_json_with_backup(path, cleaned):
                        cascade_cleaned.append(display)
                    else:
                        cascade_failed.append(display)
                except Exception as exc:
                    self.log(tr("清除事件引用失敗 → {display}: {exc}").format(display=display, exc=exc), "ERROR")
                    cascade_failed.append(display)

        # Update in-memory state + clear pending
        self.world_dynamic_events_items = new_events
        if new_bundle is not None:
            # Keep the in-memory bundle aligned with what we just wrote so the
            # statements / diplomacy-status sub-tabs stay accurate.
            self.diplomacy_bundle = new_bundle
        self.dyn_events_pending = self._dyn_empty_pending()

        msg_parts = [tr("事件 +{e} 編輯 -{d} 刪除 ＋{a} 新增").format(e=len(edits), d=len(deletes), a=len(n_new))]
        if has_stmt_changes:
            msg_parts.append(tr("聲明 +{e} 編輯 -{d} 刪除 ＋{a} 新增").format(e=len(s_edits), d=len(s_dels), a=len(s_new)))
        if p_pressure is not None:
            msg_parts.append(tr("回應壓力已更新"))
        if cascade_cleaned:
            msg_parts.append(tr("清除 {n} 個 NPC 引用").format(n=len(cascade_cleaned)))
        self.log(tr("已儲存變更：{parts}").format(parts=", ".join(msg_parts)), "SUCCESS")
        if cascade_failed:
            self.log(tr("⚠ {v0} 個 NPC 引用清除失敗：{v1}").format(v0=len(cascade_failed), v1=', '.join(cascade_failed[:5])), "ERROR")

        refresh_dynamic_events_tab(self)
        return True

    def _dyn_validity_check(self) -> None:
        """Scan NPC JSONs for orphan DynamicEvents references + offer batch clean.

        Three checks:
          1. JSON-level scan of dynamic_events.json itself (missing required
             fields, duplicate ids, malformed types).
          2. Forward orphan: NPC JSONs reference event UUIDs that no longer
             exist in dynamic_events.json.
          3. Reverse dangling: events reference characters by sid that no
             longer exist in the campaign.
        """
        from ui import msgbox as _mb
        events = list(self.world_dynamic_events_items or [])
        valid_event_ids: Set[str] = {str(e.get("id", "")) for e in events if e.get("id")}
        # Build event_id → title map for friendly display
        event_title_map: Dict[str, str] = {
            str(e.get("id", "")): str(e.get("title", "") or e.get("id", ""))
            for e in events if e.get("id")
        }

        # ── Check 1: dynamic_events.json content validity ──────────────────
        REQUIRED_FIELDS = ("id", "title", "type", "importance")
        json_issues: List[str] = []
        seen_ids: Dict[str, int] = {}
        for idx, ev in enumerate(events):
            if not isinstance(ev, dict):
                json_issues.append(tr("  • 第 {v0} 筆：不是物件（type={v1}）").format(v0=idx+1, v1=type(ev).__name__))
                continue
            eid = str(ev.get("id", "")).strip()
            if not eid:
                json_issues.append(tr("  • 第 {v0} 筆：缺少 id").format(v0=idx+1))
            else:
                seen_ids[eid] = seen_ids.get(eid, 0) + 1
            missing = [f for f in REQUIRED_FIELDS if not ev.get(f)]
            if missing:
                title = ev.get("title") or eid or "?"
                json_issues.append(tr("  • 「{title}」({v0}…)：缺少欄位 {v1}").format(title=title, v0=eid[:8], v1=', '.join(missing)))
        dups = [k for k, v in seen_ids.items() if v > 1]
        if dups:
            for d in dups[:5]:
                title = event_title_map.get(d, "?")
                json_issues.append(tr("  • 重複 id：「{title}」({d}) 出現 {v0} 次").format(title=title, d=d, v0=seen_ids[d]))

        # ── Check 2: forward orphans (NPC → event id no longer exists) ────
        char_iter = []
        for display, path in self.plain_to_path.items():
            try:
                data = safe_load_json(path) or {}
            except Exception:
                continue
            char_iter.append((display, path, data))
        orphans = svc_find_orphan_event_refs(char_iter, valid_event_ids)

        # ── Check 3: reverse dangling (event → character sid not in campaign) ──
        valid_char_sids: Set[str] = set()
        char_meta = getattr(self, "character_meta", {}) or {}
        for meta in char_meta.values():
            sid = str(meta.get("StringId", "")).strip()
            if sid:
                valid_char_sids.add(sid)
        # The player's hero is referenced as ``main_hero`` but never has a
        # character JSON of its own — always treat it (and any other reserved
        # virtual sid) as valid so the reverse check doesn't false-positive.
        valid_char_sids.update(VIRTUAL_CHARACTER_SIDS)
        from services.dynamic_event_service import find_dangling_character_refs as svc_find_dangling
        dangling = svc_find_dangling(events, valid_char_sids) if valid_char_sids else []

        # ── Helper: friendly char rendering with terminology fallback ─────
        def _char_display(sid: str) -> str:
            sid = str(sid)
            try:
                disp, source = self.resolve_display_name(sid)
            except Exception:
                disp, source = sid, "id_only"
            if source == "id_only" or not disp or disp == sid:
                return f"{tr('無名詞')} ({sid})"
            return f"{disp} ({sid})"

        # ── Check 4 (Stage C): bundle-level statement integrity ───────────
        stmt_orphans: List[Tuple[str, str]] = []
        unknown_kingdoms: List[Tuple[str, str]] = []
        if isinstance(self.diplomacy_bundle, dict):
            stmt_orphans = svc_find_orphan_statements(self.diplomacy_bundle)
            kingdom_universe: Set[str] = set()
            for source in ("terminology_campaign", "terminology_primary", "terminology_fallback"):
                payload = getattr(self, source, None) or {}
                kdict = payload.get("kingdoms") if isinstance(payload, dict) else None
                if isinstance(kdict, dict):
                    kingdom_universe.update(str(k) for k in kdict)
            unknown_kingdoms = svc_find_unknown_kingdoms(self.diplomacy_bundle, kingdom_universe)

        # ── All-clear ─────────────────────────────────────────────────────
        if not json_issues and not orphans and not dangling \
                and not stmt_orphans and not unknown_kingdoms:
            n_stmt = len(svc_bundle_statements(self.diplomacy_bundle or {}))
            _mb.showinfo(
                tr("有效檢查"),
                tr("動態事件檢查全數通過：\n  • 事件：{v0} 筆，欄位皆完整\n  • 正向：{v1} 個角色 JSON，引用全部有效\n  • 反向：所有 characters_involved 都對應到現有角色\n  • 聲明：{n_stmt} 筆，事件連結與王國 id 皆有效").format(v0=len(events), v1=len(char_iter), n_stmt=n_stmt),
                parent=self.root,
            )
            return

        # Build report
        lines: List[str] = []
        if stmt_orphans:
            lines.append(tr("🗣 孤兒聲明：{v0} 筆指向不存在的事件（僅警告）").format(v0=len(stmt_orphans)))
            for key, eid in stmt_orphans[:5]:
                lines.append(f"  • {key} → {eid[:8]}…")
            if len(stmt_orphans) > 5:
                lines.append(tr("  …及其他 {v0} 筆").format(v0=len(stmt_orphans) - 5))
            lines.append("")
        if unknown_kingdoms:
            lines.append(tr("🏛 未知王國 id：{v0} 處（僅警告，可能來自其他模組）").format(v0=len(unknown_kingdoms)))
            for where, kid in unknown_kingdoms[:5]:
                lines.append(f"  • {where}: {kid}")
            if len(unknown_kingdoms) > 5:
                lines.append(tr("  …及其他 {v0} 處").format(v0=len(unknown_kingdoms) - 5))
            lines.append("")
        if json_issues:
            lines.append(tr("📋 dynamic_events.json 結構問題：{v0} 項").format(v0=len(json_issues)))
            lines.extend(json_issues[:12])
            if len(json_issues) > 12:
                lines.append(tr("  …及其他 {v0} 項").format(v0=len(json_issues) - 12))
        if orphans:
            if lines:
                lines.append("")
            total_orphans = sum(len(o[2]) for o in orphans)
            lines.append(tr("⚠ 失效引用：{total_orphans} 個 UUID（跨 {v0} 個角色）").format(total_orphans=total_orphans, v0=len(orphans)))
            for display, _path, ids in orphans[:8]:
                # Show character display + each orphan's title (already deleted)
                shown_ids = ids[:3]
                rendered = []
                for oid in shown_ids:
                    title = event_title_map.get(oid, tr("（已不存在）"))
                    rendered.append(f"「{title}」({oid[:8]}…)")
                more = "…" if len(ids) > 3 else ""
                lines.append(f"  • {display}: {', '.join(rendered)}{more}")
            if len(orphans) > 8:
                lines.append(tr("  …及其他 {v0} 個角色").format(v0=len(orphans) - 8))
        if dangling:
            if lines:
                lines.append("")
            lines.append(tr("💡 反向警告：{v0} 個事件引用了不存在的角色（僅警告，不會自動清除）").format(v0=len(dangling)))
            for eid, sids in dangling[:5]:
                title = event_title_map.get(eid, eid)
                rendered_chars = ", ".join(_char_display(s) for s in sids[:3])
                more = "…" if len(sids) > 3 else ""
                lines.append(f"  • 「{title}」({eid[:8]}…): {rendered_chars}{more}")
            if len(dangling) > 5:
                lines.append(tr("  …及其他 {v0} 個事件").format(v0=len(dangling) - 5))

        if not orphans:
            _mb.showinfo(tr("有效檢查"), "\n".join(lines), parent=self.root)
            return

        # Confirm batch clean
        if not _mb.askyesno(
            tr("發現失效引用"),
            "\n".join(lines) + "\n\n" + tr("是否批次清除（forward orphans 部分）？"),
            parent=self.root,
        ):
            return

        # Backup once
        self._auto_backup_campaign(tr("清除孤兒事件引用"))

        cleaned_count = 0
        failed: List[str] = []
        for display, path, orphan_ids in orphans:
            try:
                data = safe_load_json(path) or {}
                cleaned = svc_clean_char_event_refs(data, set(orphan_ids))
                if self.safe_write_json_with_backup(path, cleaned):
                    cleaned_count += 1
                else:
                    failed.append(display)
            except Exception as exc:
                self.log(tr("清除孤兒事件引用失敗 → {display}: {exc}").format(display=display, exc=exc), "ERROR")
                failed.append(display)

        self.log(tr("已清除 {cleaned_count} 個 NPC 的孤兒事件引用").format(cleaned_count=cleaned_count), "SUCCESS")
        if failed:
            self.log(tr("⚠ {v0} 個角色清除失敗：{v1}").format(v0=len(failed), v1=', '.join(failed[:5])), "ERROR")
        _mb.showinfo(
            tr("有效檢查完成"),
            tr("已清除 {cleaned_count} 個角色的孤兒引用。").format(cleaned_count=cleaned_count),
            parent=self.root,
        )

    def _disease_validity_check(self) -> None:
        """Two-direction disease consistency check with optional cleanup.

        Direction 1 (forward orphan):
          disease_instances.json entries whose disease_id is absent from the
          diseases catalog.  Fix: remove the instances + sync affected character
          JSONs via sync_character_diseases().

        Direction 2 (reverse orphan):
          Character JSONs that claim IsSick/CurrentDiseases but have no active
          entry in disease_instances.json.  Fix: call sync_character_diseases()
          with an empty instance list to clear the stale fields.
        """
        from ui import msgbox as _mb

        # ── Direction 1: orphaned instances ───────────────────────────────
        invalid_insts = invalid_hero_instances(self.disease_instances, self.diseases)

        # ── Direction 2: stale character JSON fields ───────────────────────
        def _char_iter():
            for display, path in self.plain_to_path.items():
                try:
                    data = safe_load_json(path) or {}
                    yield display, path, data
                except Exception:
                    pass

        stale_chars = stale_disease_characters(self.disease_instances, _char_iter())

        # ── All-clear ─────────────────────────────────────────────────────
        n_inst = len(svc_hero_instances(self.disease_instances))
        if not invalid_insts and not stale_chars:
            _mb.showinfo(
                tr("有效檢查"),
                tr("兩方向檢查全部通過：\n  • 正向：{n_inst} 筆感染記錄，disease_id 皆有效\n  • 反向：所有角色 JSON 疾病欄位與感染記錄一致").format(n_inst=n_inst),
                parent=self.root,
            )
            return

        # ── Build combined report ──────────────────────────────────────────
        report_parts: List[str] = []
        if invalid_insts:
            lines = "\n".join(
                f"  • {x.get('target_id','?')} → {x.get('disease_id','?')}"
                for x in invalid_insts
            )
            report_parts.append(
                tr("【正向孤兒】{n} 筆感染記錄的 disease_id 不存在於疾病目錄：\n{lines}").format(
                    n=len(invalid_insts), lines=lines)
            )
        if stale_chars:
            lines = "\n".join(f"  • {display} ({sid})" for display, _, sid in stale_chars)
            report_parts.append(
                tr("【反向孤兒】{n} 位角色 JSON 標記了 IsSick/CurrentDiseases，\n"
                   "但 disease_instances.json 中無對應有效記錄：\n{lines}").format(
                    n=len(stale_chars), lines=lines)
            )

        n_total = len(invalid_insts) + len(stale_chars)
        n_inst_heroes = len({x.get("target_id", "?") for x in invalid_insts})

        campaign = getattr(self, "campaign_dir", None)
        backup_base = Path(self.backup_dir_var.get())
        backup_note = tr("  ★ 清除前將自動備份整個戰役資料夾至：\n    {path}\n").format(
            path=backup_base / 'save_data') if campaign else (
            tr("  ⚠ 未載入戰役資料夾，無法自動備份，請手動備份後再操作\n")
        )

        prompt = (
            "\n\n".join(report_parts) + "\n\n"
            + tr("── 清除將執行同步寫入 ──\n")
            + (tr("  正向：移除 {a} 筆失效記錄 + 同步 {b} 位英雄 JSON\n").format(
                a=len(invalid_insts), b=n_inst_heroes) if invalid_insts else "")
            + (tr("  反向：清空 {n} 位角色的疾病欄位\n").format(n=len(stale_chars))
               if stale_chars else "")
            + f"\n{backup_note}\n"
            + tr("是否全部清除？")
        )
        if not _mb.askyesno(
            tr("發現 {n_total} 個不一致（正向 {v0} + 反向 {v1}）").format(n_total=n_total, v0=len(invalid_insts), v1=len(stale_chars)),
            prompt, parent=self.root,
        ):
            return
        # Check itself is read-only; only the fix below writes campaign data.
        if self._confirm_if_game_running(tr("疾病有效性修復")):
            return

        # ── Pre-write: backup campaign directory ───────────────────────────
        if campaign:
            try:
                backup_path = backup_campaign_dir(campaign, backup_base)
                self.log(tr("有效檢查清理前備份完成：{backup_path}").format(backup_path=backup_path), "SUCCESS")
                self.refresh_backup_center()
            except Exception as e:
                self.log(tr("備份失敗，清理作業已中止：{e}").format(e=e), "ERROR")
                _mb.showerror(tr("備份失敗"), tr("無法建立備份，清理作業已中止。\n錯誤：{e}").format(e=e), parent=self.root)
                return
        else:
            self.log(tr("未載入戰役資料夾，跳過自動備份，直接執行清理"), "WARNING")

        synced_total = 0
        failed: List[str] = []
        all_affected_displays: set = set()

        # ── Direction 1 cleanup ────────────────────────────────────────────
        if invalid_insts:
            valid_insts = [x for x in self.disease_instances if x not in invalid_insts]
            _, inst_path = disease_paths_for_app(campaign, self.script_dir)
            try:
                dump_disease_instances(inst_path, valid_insts)
            except Exception as e:
                _mb.showerror(tr("寫入失敗"), str(e), parent=self.root)
                return
            self.disease_instances = valid_insts

            for hero_id in sorted({x.get("target_id", "?") for x in invalid_insts}):
                char_path = self.plain_to_path.get(hero_id)
                if char_path is None:
                    for disp, meta in self.character_meta.items():
                        if meta.get("StringId") == hero_id:
                            char_path = self.plain_to_path.get(disp)
                            all_affected_displays.add(disp)
                            break
                if char_path is None:
                    continue
                try:
                    char_data = safe_load_json(char_path) or {}
                    remaining = instances_for_hero(valid_insts, hero_id)
                    svc_sync_character_diseases(char_data, remaining, self.diseases)
                    if self.safe_write_json_with_backup(char_path, char_data):
                        synced_total += 1
                    else:
                        failed.append(hero_id)
                except Exception as e:
                    self.log(tr("同步角色 {hero_id} 失敗：{e}").format(hero_id=hero_id, e=e), "ERROR")
                    failed.append(hero_id)

        # ── Direction 2 cleanup ────────────────────────────────────────────
        if stale_chars:
            for display, char_path, sid in stale_chars:
                all_affected_displays.add(display)
                try:
                    char_data = safe_load_json(char_path) or {}
                    # Pass empty instances → clears IsSick / CurrentDiseases / DiseaseProgress
                    svc_sync_character_diseases(char_data, [], self.diseases)
                    if self.safe_write_json_with_backup(char_path, char_data):
                        synced_total += 1
                        self.log(tr("  已清除 {display}（{sid}）的殘留疾病欄位").format(display=display, sid=sid), "INFO")
                    else:
                        failed.append(sid)
                except Exception as e:
                    self.log(tr("清除 {display} 疾病欄位失敗：{e}").format(display=display, e=e), "ERROR")
                    failed.append(sid)

        # ── Refresh detail panel if affected ──────────────────────────────
        current = getattr(self, "_detail_display", None)
        if current and current in all_affected_displays:
            self._load_character_detail(current)

        # ── Summary log ───────────────────────────────────────────────────
        parts = []
        if invalid_insts:
            parts.append(tr("正向清除 {n} 筆失效記錄").format(n=len(invalid_insts)))
        if stale_chars:
            parts.append(tr("反向清除 {n} 位角色殘留疾病欄位").format(n=len(stale_chars)))
        msg = tr("有效檢查完成：{parts}；共寫入 {n} 個角色 JSON").format(parts="；".join(parts), n=synced_total)
        if failed:
            msg += tr("；失敗 {n} 位：{who}").format(n=len(failed), who=", ".join(failed))
            self.log(msg, "ERROR")
        else:
            self.log(msg, "SUCCESS")
        if campaign:
            self.log(tr("  → 備份位置：{v0}（可於「備份」分頁查閱）").format(v0=backup_base / 'save_data'), "INFO")
        refresh_disease_tab(self)

    def insert_plot(self):
        selected_paths = self._checked_paths()
        if not selected_paths:
            messagebox.showinfo(tr("寫入劇情"), tr("請選擇至少一位角色"))
            return
        if self._staged_conflict_block(selected_paths, tr("寫入劇情")):
            return
        open_plot_insert_dialog(self, selected_paths)

    def choose_backup_dir(self):
        d = filedialog.askdirectory(title=tr("選擇備份資料夾"))
        if d:
            self.backup_dir_var.set(d)
            self.refresh_backup_center()

    def choose_game_dir(self):
        """Let the user pick the Bannerlord install root and re-derive paths."""
        d = filedialog.askdirectory(title=tr("選擇遊戲主目錄（Bannerlord 安裝資料夾）"))
        if not d:
            return
        p = Path(d)
        # Soft-check: warn if it doesn't look like a Bannerlord install but still allow.
        if not (p / "Modules").is_dir():
            if not messagebox.askyesno(
                tr("確認"),
                tr("此資料夾看起來不像 Bannerlord 主目錄（找不到 Modules 子資料夾）。\n\n路徑：{p}\n\n仍要使用嗎？").format(p=p),
            ):
                return
        self.game_dir_var.set(str(p))
        # Don't apply yet — wait for "儲存偏好" so user has a chance to also
        # adjust the save_data path before paths get re-resolved.

    def choose_save_data_dir(self):
        """Let the user pick the AIInfluence save_data folder explicitly."""
        if not self._confirm_discard_world_changes(tr("切換戰役位置")):
            return
        d = filedialog.askdirectory(title=tr("選擇 AIInfluence 的 save_data 資料夾"))
        if not d:
            return
        self.save_data_var.set(d)

    def auto_detect_paths(self):
        """Re-run path auto-detection from scratch, ignoring overrides."""
        self.settings["game_dir"] = ""
        self.settings["save_data_dir"] = ""
        save_json_dict(self.settings_path, self.settings)
        self._init_paths()
        if self.save_data_dir is None:
            messagebox.showwarning(tr("自動偵測"), tr("仍找不到 AIInfluence save_data。請手動指定遊戲位置。"))
        else:
            messagebox.showinfo(tr("自動偵測完成"),
                tr("遊戲位置：{v0}\n戰役位置：{v1}").format(v0=self.game_dir or tr("（未偵測到）"), v1=self.save_data_dir))
            self.refresh(ask_dirty=False)

    def backup_campaign(self):
        if not self.campaign_dir or not self.campaign_dir.is_dir():
            messagebox.showwarning(tr("備份"), tr("尚未載入戰役資料夾"))
            return

        backup_base = Path(self.backup_dir_var.get())

        try:
            backup_path = backup_campaign_dir(self.campaign_dir, backup_base)
            self.log(tr("戰役備份完成：{backup_path}").format(backup_path=backup_path), "SUCCESS")
            self.refresh_backup_center()
            messagebox.showinfo(tr("備份成功"), tr("已備份至：\n{backup_path}").format(backup_path=backup_path))
        except Exception as e:
            self.log(tr("備份失敗：{v0}").format(v0=str(e)), "ERROR")
            messagebox.showerror(tr("備份失敗"), str(e))

    def _auto_backup_campaign(self, reason: str) -> bool:
        """Back up the whole campaign folder before a destructive write.

        Returns True on success. Failures are logged (no longer silently
        swallowed) so a missed safety backup is visible. Passing paths through
        ``Path`` here is what the old inline calls got wrong — they handed the
        service a raw string and the resulting exception was eaten.
        """
        campaign = getattr(self, "campaign_dir", None)
        if not campaign or not Path(campaign).is_dir():
            return False
        try:
            backup_campaign_dir(Path(campaign), Path(self.backup_dir_var.get()))
            return True
        except Exception as exc:
            self.log(tr("⚠ 自動備份失敗（{reason}）：{exc}").format(reason=reason, exc=exc), "WARN")
            return False

    def backup_tool_config_now(self):
        """Back up the tool's own config directory (settings/presets/aliases…)."""
        try:
            path = backup_tool_config(self.config_dir, Path(self.backup_dir_var.get()))
            self.log(tr("工具設定備份完成：{path}").format(path=path), "SUCCESS")
            self.refresh_backup_center()
            messagebox.showinfo(tr("備份成功"), tr("工具設定已備份至：\n{path}").format(path=path))
        except Exception as e:
            self.log(tr("工具設定備份失敗：{e}").format(e=e), "ERROR")
            messagebox.showerror(tr("備份失敗"), str(e))

    def open_backup_dir(self):
        backup_dir = self.backup_dir_var.get()
        if not Path(backup_dir).exists():
            messagebox.showwarning(tr("開啟備份資料夾"), tr("備份資料夾不存在，請先設定或建立"))
            return
        try:
            os.startfile(backup_dir)
        except Exception as e:
            self.log(tr("開啟備份資料夾失敗：{e}").format(e=e), "ERROR")
            messagebox.showerror(tr("開啟錯誤"), str(e))

    def open_save_data_dir(self):
        """Open AI Influence's save_data folder (…\\AIInfluence\\save_data)."""
        sd = getattr(self, "save_data_dir", None)
        if not sd or not Path(sd).is_dir():
            messagebox.showwarning(tr("開啟戰役主目錄"),
                                   tr("尚未定位戰役資料夾，請先到「設定 → 檔案位置」確認。"))
            return
        try:
            os.startfile(str(sd))
        except Exception as e:
            self.log(tr("開啟戰役主目錄失敗：{e}").format(e=e), "ERROR")
            messagebox.showerror(tr("開啟錯誤"), str(e))

    def safe_write_json_with_backup(self, path: Path, data: dict) -> bool:
        # Every character write in the tool funnels through here, so the 6.0 RAG
        # bookkeeping hangs off this one place rather than each call site.
        rag_sid = svc_rag.string_id_of(data) if svc_rag.is_character_payload(data) else ""
        history_changed = False
        if rag_sid:
            svc_rag.clamp_memory_processed_index(data)
            history_changed = self._conversation_history_changed(path, data)
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception as e:
            self.log(tr("寫入 {v0} 失敗：{v1}").format(v0=path.name, v1=str(e)), "ERROR")
            messagebox.showerror(tr("寫入錯誤"), tr("無法寫入 {v0}\n錯誤：{v1}").format(v0=path.name, v1=str(e)))
            return False
        if history_changed and svc_rag.invalidate_rag_index(path.parent, rag_sid):
            self.log(
                tr("已清除 {v0} 的對話檢索索引（RAG），遊戲載入戰役時會自動重建").format(v0=rag_sid),
                "INFO",
            )
        self._apply_snapshot_policy(path.parent)
        self._touch_open_detail(path)
        return True

    def save_settings(self) -> None:
        """Persist the settings dict (single entry point for preference UIs)."""
        try:
            save_json_dict(self.settings_path, self.settings)
        except Exception as exc:
            self.log(tr("儲存設定失敗：{v0}").format(v0=str(exc)), "ERROR")

    def _touch_open_detail(self, path: Path) -> None:
        """Refresh the detail panel when *path* is the character it is showing.

        Hooked here, at the single write choke point, rather than in each
        caller: the immediate-write tools (寫入劇情, 重置, 批量清空, 修剪,
        載入群聊…) each wrote straight to disk and left the open 對話歷史 /
        對話觀察 / 摘要 showing pre-write data until the user clicked away and
        back.  Anything that writes a character file now refreshes what the user
        is looking at, including write paths added later.

        Debounced: a batch write touching 20 files reloads the panel once.
        """
        try:
            display = getattr(self, "_detail_display", None)
            if not display or self.plain_to_path.get(display) != Path(path):
                return
            pending = getattr(self, "_detail_reload_after", None)
            if pending:
                self.root.after_cancel(pending)
            self._detail_reload_after = self.root.after(60, self._reload_open_detail)
        except Exception:
            pass   # never let a refresh convenience break a successful write

    def _reload_open_detail(self) -> None:
        self._detail_reload_after = None
        display = getattr(self, "_detail_display", None)
        if display and display in self.plain_to_path:
            self._load_character_detail(display)

    def _apply_snapshot_policy(self, campaign_dir: Path) -> None:
        """Handle the mod's save_snapshots after writing campaign data.

        Runs on every campaign write — including the immediate-write paths
        (conversation editing, memory page, plot insert) that never pass through
        a confirm dialog — because a snapshot left behind silently reverts those
        edits the next time the player loads the game.

        Three policies (設定 → 偏好設定 → 存檔備份處理):
        ``keep`` leaves them alone, ``backup_then_clear`` copies them into the
        Backup Center first, ``auto_clear`` (default) just removes them.

        Cheap to call repeatedly: once purged there is nothing left to find, so
        later writes in the same session cost one directory listing.
        """
        policy = svc_snapshot.normalize_policy(self.settings.get("snapshot_policy"))
        if not svc_snapshot.clears_snapshots(policy):
            self._warn_snapshots_kept_once(campaign_dir)
            return

        # Copy first when asked — a failed copy must not lead to a delete, or the
        # player loses the rollback they explicitly opted to keep.
        if svc_snapshot.backs_up_first(policy):
            try:
                saved = backup_snapshots(campaign_dir, Path(self.backup_dir_var.get()))
            except Exception as exc:
                self.log(tr("備份戰役自動備份失敗，已保留未清除：{v0}").format(v0=str(exc)), "ERROR")
                return
            if saved is not None:
                self.log(tr("已將 save_snapshots 備份至：{v0}").format(v0=str(saved)), "INFO")
                self.refresh_backup_center()

        removed, errors = svc_snapshot.purge_snapshots(campaign_dir)
        if removed:
            self.log(
                tr("已清除 {n} 個戰役自動備份（save_snapshots），編輯不會在載入時被還原")
                .format(n=removed), "INFO")
        for err in errors:
            self.log(tr("清除戰役自動備份失敗：{v0}").format(v0=err), "ERROR")

    def _warn_snapshots_kept_once(self, campaign_dir: Path) -> None:
        """Under the ``keep`` policy, say once per campaign that edits may revert.

        Once per campaign per session: this runs on *every* write, and a warning
        on each keystroke-sized save would be worse than the risk it describes.
        """
        try:
            if not svc_snapshot.has_snapshots(campaign_dir):
                return
            seen = getattr(self, "_snapshot_keep_warned", None)
            if seen is None:
                seen = self._snapshot_keep_warned = set()
            key = str(campaign_dir)
            if key in seen:
                return
            seen.add(key)
            self.log(
                tr("此戰役仍有 save_snapshots（依偏好設定保留）；在主選單所做的編輯，"
                   "可能在載入遊戲時被還原"), "WARNING")
        except Exception:
            pass   # a warning must never break a successful write

    @staticmethod
    def _conversation_history_changed(path: Path, data: dict) -> bool:
        """True when *data* changes the ConversationHistory already on disk.

        Read before the write so an unrelated edit (a description, a disease
        field) doesn't throw away a RAG index the mod would have to re-embed.
        A brand-new file counts as changed only when it ships history.
        """
        try:
            old = safe_load_json(path) if Path(path).is_file() else None
        except Exception:
            return True  # can't tell → invalidate, the safe direction
        if not isinstance(old, dict):
            return bool(data.get(svc_rag.CONVERSATION_KEY))
        return old.get(svc_rag.CONVERSATION_KEY) != data.get(svc_rag.CONVERSATION_KEY)

    def _confirm_if_game_running(self, operation: str) -> bool:
        """遊戲執行中時，對會被覆寫的戰役資料寫入彈出確認提示（非硬擋）。

        回傳 True 表示「使用者取消，呼叫端應中止」；False 表示放行可繼續。

        AI Influence 5.0.x 只在戰役載入時讀檔一次，之後全在記憶體運作並隨時
        整包覆寫（SaveFull）——若戰役仍在進行中，工具寫入的外交包／疾病檔會被
        沖掉。

        兩種模式：
        * **精準模式**（核心模組運作中、心跳新鮮）：可區分主選單／戰役中，
          只有「戰役載入中」才提示，主選單直接放行不打擾。
        * **回退模式**（無核心模組）：無法區分主選單與戰役中（兩者都只是
          Bannerlord.exe 執行中），故遊戲執行時一律提示確認。
        遊戲未執行時不提示、直接放行。
        """
        status = getattr(self, "_game_status", None)

        # Precise path — when the Story Master companion mod's heartbeat is fresh
        # we know the exact state, so we ONLY prompt when a campaign is actually
        # loaded (in_campaign / paused) and stay silent at the main menu.
        if status is not None and getattr(status, "heartbeat_fresh", False):
            if getattr(status, "state", None) not in ("in_campaign", "paused"):
                return False  # main menu → safe to save, no prompt
            self.log(tr("{operation}：核心模組偵測到戰役載入中，已提示使用者確認").format(operation=operation), "WARNING")
            proceed = messagebox.askyesno(
                tr("戰役進行中"),
                tr("連接器偵測到「戰役正在載入中」。\n\n此時 AI 效應會隨時用記憶體內容整包覆寫存檔，「{operation}」儲存的變更會被沖掉而遺失。\n\n請先退出戰役回到主選單後再儲存。\n\n是否仍要繼續儲存？").format(operation=operation),
                icon="warning", default="no", parent=self.root,
            )
            if not proceed:
                self.log(tr("{operation}：使用者取消儲存").format(operation=operation), "INFO")
                return True
            return False

        # Fallback — no companion mod / no fresh heartbeat: psutil-based behaviour
        # (can't tell main menu from in-campaign, so prompt whenever the game runs).
        running = status.running if status is not None else None
        if running is None:
            running = svc_detect_bannerlord_running()
        if not running:
            return False
        self.log(tr("{operation}：偵測到遊戲執行中，已提示使用者確認").format(operation=operation), "WARNING")
        proceed = messagebox.askyesno(
            tr("遊戲執行中"),
            tr("偵測到 Bannerlord 正在執行。\n\n若你仍在「戰役進行中」，AI 效應會隨時用記憶體內容整包覆寫存檔，此時「{operation}」儲存的變更會被沖掉而遺失。\n\n請確認你已「退出戰役回到主選單」（或關閉遊戲）後再儲存；完成後重新載入戰役即可生效。\n\n是否仍要繼續儲存？").format(operation=operation),
            icon="warning",
            default="no",
            parent=self.root,
        )
        if not proceed:
            self.log(tr("{operation}：使用者取消儲存").format(operation=operation), "INFO")
            return True
        return False

    # ── Core module status (v1.1.0 transformation: the module is the main
    #    body; the editor no longer installs it) ──────────────────────────
    def _companion_resolve_game_dir(self) -> Optional[Path]:
        """Best-effort BannerlordRoot: the configured game_dir, else derived
        from the known save_data path."""
        gd = getattr(self, "game_dir", None)
        if gd and Path(gd).is_dir():
            return Path(gd)
        sd = getattr(self, "save_data_dir", None)
        if sd:
            from services.path_service import find_bannerlord_root_from_save_data
            root = find_bannerlord_root_from_save_data(sd)
            if root:
                return root
        return None

    def _core_mod_status(self):
        """services.companion_mod_service.module_status for the current paths."""
        import services.companion_mod_service as cm
        return cm.module_status(self._companion_resolve_game_dir(), app_paths.app_version())

    def validate_json(self):
        paths = self._checked_paths()
        if not paths:
            messagebox.showinfo(tr("驗證檔案"), tr("請選擇至少一位角色"))
            return
        total, failures = validate_character_files(paths, self._get_character_name)

        # Log result
        if not failures:
            self.log(tr("驗證完成（{total} 位角色）✓ 全部通過").format(total=total), "SUCCESS")
        else:
            self.log(tr("驗證完成（{total} 位角色）✗ 失敗 {failed}/{total}：{names}").format(
                total=total, failed=len(failures), names=", ".join(failures)), "ERROR")

        # Show popup result window
        result_win = tk.Toplevel(self.root)
        result_win.title(tr("驗證檔案結果"))
        result_win.geometry("480x360")
        result_win.minsize(380, 260)
        self._center_window(result_win, 480, 360)
        result_win.transient(self.root)

        if not failures:
            ttk.Label(result_win, text="✅", font=("", 40)).pack(pady=(24, 4))
            ttk.Label(result_win, text=tr("全部通過！共驗證 {n} 位角色").format(n=total),
                      font=("", 13, "bold")).pack(pady=6)
        else:
            ttk.Label(result_win, text="❌", font=("", 40)).pack(pady=(20, 4))
            ttk.Label(result_win, text=tr("驗證完成：{n} 位角色，{f} 位失敗").format(n=total, f=len(failures)),
                      font=("", 13, "bold")).pack(pady=4)
            list_frame = ttk.Frame(result_win)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=6)
            sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
            lb = tk.Listbox(list_frame, yscrollcommand=sb.set, font=("", 10),
                            selectmode=tk.BROWSE)
            sb.config(command=lb.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            for f in failures:
                lb.insert(tk.END, f"✗  {f}")

        ttk.Button(result_win, text=tr("關閉"), command=result_win.destroy,
                   style="secondary.TButton").pack(pady=10)

    # ── Preview-area JSON edit callbacks ──────────────────────────────────

    def _json_edit_save(self, data: dict) -> None:
        """Save edited JSON back to the currently previewed character's file."""
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if not path:
            return
        self.doc_staging.put(Path(path), data, safe_load_json)
        self.doc_staging.prune_clean()
        self.log(tr("已暫存 JSON 編輯：{v0}（儲存後寫入）").format(v0=self._get_character_name(path)), "INFO")
        self._load_character_detail(display)
        self._staging_refresh_ui()

    def _json_edit_revert(self) -> None:
        """Revert to on-disk data — drops this character's staged working copy.

        The working copy is the whole document, so this also discards edits
        staged from other tabs for the same character (the confirm says so).
        """
        display = self._detail_display
        path = self.plain_to_path.get(display) if display else None
        if path and self.doc_staging.is_dirty(path):
            if not messagebox.askyesno(
                tr("還原"),
                tr("此角色有暫存變更（含其他分頁的編輯）。\n還原將丟棄整份暫存、回到磁碟上的狀態，繼續？"),
                parent=self.root,
            ):
                return
            self.doc_staging.discard(path)
            self.log(tr("已丟棄「{display}」的暫存變更").format(display=display), "WARN")
            self._staging_refresh_ui()
        if display:
            self._load_character_detail(display)

    def reset_character(self):
        paths = self._checked_paths()
        if not paths:
            messagebox.showinfo(tr("重置角色"), tr("請選擇至少一位角色"))
            return
        if self._staged_conflict_block(paths, tr("重置角色")):
            return
        open_reset_character_dialog(self, paths)

    def quick_reset(self):
        """清空回應：批量清除選取角色的 LastDynamicResponse / LastAIResponseJson。"""
        paths = self._checked_paths()
        if not paths:
            messagebox.showinfo(tr("清空回應"), tr("請選擇至少一位角色"))
            return
        if self._staged_conflict_block(paths, tr("清空回應")):
            return
        if not messagebox.askyesno(tr("清空回應"), tr("確定要清空選取角色的 AI 回應暫存嗎？（清空 LastDynamicResponse / LastAIResponseJson 並驗證）")):
            return

        ok_count = 0
        for path in paths:
            d = safe_load_json(path) or {}
            d["LastDynamicResponse"] = None
            d["LastAIResponseJson"] = None
            if self.safe_write_json_with_backup(path, d):
                ok_count += 1
        self.log(tr("已清空回應 {ok_count} 位角色").format(ok_count=ok_count), "SUCCESS")

        self.validate_json()

    def bulk_clear_diseases(self):
        """批量清除已選角色的疾病狀態（移除其在 disease_instances.json 的英雄感染記錄
        並同步 IsSick / CurrentDiseases / DiseaseProgress 等欄位歸零）。"""
        if not self._checked_paths():
            messagebox.showinfo(tr("移除疾病"), tr("請至少勾選一位角色"))
            return
        if self._staged_conflict_block(self._checked_paths(), tr("移除疾病")):
            return
        if self._confirm_if_game_running(tr("批量移除疾病")):
            return

        # 1. Collect (display, path, StringId) for each selected character
        targets: List[Tuple[str, Path, str]] = []
        for display in self.selected_displays:
            path = self.plain_to_path.get(display)
            if not path:
                continue
            meta = self.character_meta.get(display, {}) if isinstance(self.character_meta, dict) else {}
            sid = str(meta.get("StringId", "")).strip()
            if not sid:
                # fall back to reading from disk
                try:
                    sid = str((safe_load_json(path) or {}).get("StringId", "")).strip()
                except Exception:
                    sid = ""
            if not sid:
                continue
            targets.append((display, path, sid))
        if not targets:
            messagebox.showinfo(
                tr("移除疾病"),
                tr("已選角色皆無有效 StringId，無法定位疾病記錄"),
                parent=self.root,
            )
            return

        # 2. Pre-count what will actually be removed
        sid_set = {t[2] for t in targets}
        affected_inst = [
            x for x in (self.disease_instances or [])
            if x.get("target_type") == 0 and x.get("target_id") in sid_set
        ]

        # Build preview
        preview_lines = [f"  • {d}" for d, _, _ in targets[:8]]
        if len(targets) > 8:
            preview_lines.append(tr("  …及其他 {v0} 位").format(v0=len(targets) - 8))
        if not messagebox.askyesno(
            tr("移除疾病"),
            tr("將清除 {v0} 位角色的疾病狀態（影響 {v1} 筆感染記錄）：\n\n").format(v0=len(targets), v1=len(affected_inst))
            + "\n".join(preview_lines)
            + tr("\n\n此操作會立即寫入磁碟（會自動備份戰役）。要繼續嗎？"),
            parent=self.root,
        ):
            return

        # 3. Backup once
        self._auto_backup_campaign(tr("批量移除疾病"))

        # 4. Filter disease_instances to drop matching hero entries
        new_instances = [
            x for x in (self.disease_instances or [])
            if not (x.get("target_type") == 0 and x.get("target_id") in sid_set)
        ]

        # 5. Write disease_instances.json
        campaign = getattr(self, "campaign_dir", None)
        _, inst_path = disease_paths_for_app(campaign, self.script_dir)
        try:
            dump_disease_instances(inst_path, new_instances)
        except Exception as exc:
            messagebox.showerror(tr("寫入失敗"), str(exc), parent=self.root)
            self.log(tr("批量移除疾病失敗：{exc}").format(exc=exc), "ERROR")
            return
        self.disease_instances = new_instances

        # 6. Sync each affected character JSON (clear IsSick / CurrentDiseases / DiseaseProgress)
        sync_failures: List[str] = []
        for display, char_path, _sid in targets:
            try:
                char_data = safe_load_json(char_path) or {}
                svc_sync_character_diseases(char_data, [], self.diseases)
                if not self.safe_write_json_with_backup(char_path, char_data):
                    sync_failures.append(display)
            except Exception as exc:
                self.log(tr("同步角色疾病欄位失敗 → {display}: {exc}").format(display=display, exc=exc), "ERROR")
                sync_failures.append(display)

        self.log(
            tr("已批量清除 {v0} 位角色的疾病（移除 {v1} 筆感染記錄）").format(v0=len(targets), v1=len(affected_inst)),
            "SUCCESS",
        )
        if sync_failures:
            self.log(
                tr("⚠ {v0} 位角色 JSON 同步失敗：{v1}").format(v0=len(sync_failures), v1=', '.join(sync_failures[:5])),
                "ERROR",
            )

        # Refresh the disease tab if it was already built; reload current
        # character detail so the summary reflects cleared state.
        try:
            refresh_disease_tab(self)
        except Exception:
            pass
        if getattr(self, "_detail_display", None):
            try:
                self._load_character_detail(self._detail_display)
            except Exception:
                pass

    # ── SummaryCard callbacks ───────────────────────────────────────────────
    def _summary_field_save(self, field: str, new_value: str) -> None:
        """Save one AI-generated text field to the currently-viewed character JSON."""
        display = getattr(self, "_detail_display", None)
        if not display:
            messagebox.showinfo(tr("儲存"), tr("請先選擇角色"))
            return
        path = self.plain_to_path.get(display)
        if not path:
            self.log(tr("無法儲存 {field}：找不到角色路徑 {display}").format(field=field, display=display), "ERROR")
            return
        d = self._staged_checkout(path)
        old_val = d.get(field, "")
        # Normalize trailing newline — the inline tk.Text always keeps a trailing newline.
        new_val = (new_value or "").rstrip("\n")
        if str(old_val or "") == new_val:
            self.log(tr("{display}：{field} 未變更").format(display=display, field=field), "INFO")
            return
        d[field] = new_val
        self._staged_store(path, d, tr("已更新 {field} → {display}").format(field=field, display=display))

    def _summary_reset_response(self) -> None:
        """Clear LastDynamicResponse / LastAIResponseJson on the currently-viewed character."""
        display = getattr(self, "_detail_display", None)
        if not display:
            messagebox.showinfo(tr("清空回應"), tr("請先選擇角色"))
            return
        path = self.plain_to_path.get(display)
        if not path:
            self.log(tr("找不到角色路徑 {display}").format(display=display), "ERROR")
            return
        if not messagebox.askyesno(
            tr("清空回應"),
            tr("確定要清空此角色的 LastDynamicResponse / LastAIResponseJson？"),
        ):
            return
        d = self._staged_checkout(path)
        d["LastDynamicResponse"] = None
        d["LastAIResponseJson"] = None
        self._staged_store(path, d, tr("已清空回應 → {display}").format(display=display))

    # ── Summary 編輯屬性 / 快速清空 (v0.35.1) ──────────────────────────────────
    def _summary_current_path(self):
        """(display, path) for the currently-viewed character, or (None, None)."""
        display = getattr(self, "_detail_display", None)
        if not display:
            messagebox.showinfo(tr("角色屬性"), tr("請先選擇角色"))
            return None, None
        path = self.plain_to_path.get(display)
        if not path:
            return None, None
        return display, path

    def _summary_attr_edit(self) -> None:
        display, path = self._summary_current_path()
        if not path:
            return
        from dialogs.attr_editor_dialog import open_attr_editor
        open_attr_editor(self, path, self._staging_effective(path), self._summary_attr_save)

    def _summary_attr_save(self, path, changes: dict) -> None:
        """Apply 編輯屬性 changes to the character JSON (one write + reload)."""
        if not changes:
            return
        d = self._staged_checkout(path)
        if "romance" in changes:
            svc_set_player_romance(d, changes["romance"])
        if "trust" in changes:
            svc_set_player_trust(d, changes["trust"])
        if "interaction" in changes:
            svc_set_player_interaction(d, int(changes["interaction"]))
        if "last_interaction" in changes:
            d["LastInteractionTimeDays"] = float(changes["last_interaction"])
        if "romance_eligible" in changes:
            d["IsRomanceEligible"] = bool(changes["romance_eligible"])
        self._staged_store(path, d, tr("已更新角色屬性（{n} 項）").format(n=len(changes)))

    def _summary_quick_clear(self, kind: str, fields) -> None:
        """Dispatch the 快速清空 menu actions on the current character."""
        if kind == "response":
            self._summary_reset_response()
            return
        if kind == "diseases":
            self._summary_clear_diseases()
            return
        if not fields:
            return
        display, path = self._summary_current_path()
        if not path:
            return
        d = self._staged_checkout(path)
        pristine = svc_pristine_template(d)
        if kind == "attrs":
            if "romance" in fields:
                svc_set_player_romance(d, 0)
            if "trust" in fields:
                svc_set_player_trust(d, 0)
            if "interaction" in fields:
                svc_set_player_interaction(d, 0)
            if "relation" in fields:
                d["PlayerRelation"] = {"Value": 0, "Description": "neutral"}
            label = tr("清空屬性")
        elif kind == "status":
            if "mood" in fields:
                # Clear = remove the emotional state so 情緒 no longer displays
                # (consistent with party/war/task vanishing when cleared); the
                # game regenerates it on the next interaction.
                d["EmotionalState"] = None
            if "party" in fields:
                d["NPCForces"] = pristine.get("NPCForces")
            if "war" in fields:
                d["WarStatus"] = None
            if "task" in fields:
                d["CurrentTask"] = ""
            label = tr("清空狀態")
        else:
            return
        self._staged_store(path, d, tr("{label} → {display}（{n} 欄）").format(label=label, display=display, n=len(fields)))

    def _summary_clear_diseases(self) -> None:
        """Clear the current character's disease state (JSON fields + infection records)."""
        display, path = self._summary_current_path()
        if not path:
            return
        if self._staged_conflict_block([path], tr("清空疾病")):
            return
        meta = self.character_meta.get(display, {}) if isinstance(self.character_meta, dict) else {}
        sid = str(meta.get("StringId", "")).strip()
        if not sid:
            try:
                sid = str((safe_load_json(path) or {}).get("StringId", "")).strip()
            except Exception:
                sid = ""
        if not messagebox.askyesno(
            tr("清空疾病"),
            tr("確定要清空此角色的疾病狀態（並移除其感染記錄）嗎？"),
            parent=self.root,
        ):
            return
        # Drop this hero's infection records from disease_instances.json.
        if sid:
            campaign = getattr(self, "campaign_dir", None)
            new_instances = [
                x for x in (self.disease_instances or [])
                if not (x.get("target_type") == 0 and x.get("target_id") == sid)
            ]
            if len(new_instances) != len(self.disease_instances or []):
                _, inst_path = disease_paths_for_app(campaign, self.script_dir)
                try:
                    dump_disease_instances(inst_path, new_instances)
                    self.disease_instances = new_instances
                except Exception as exc:
                    messagebox.showerror(tr("寫入失敗"), str(exc), parent=self.root)
                    self.log(tr("清空疾病失敗（感染記錄）→ {display}: {exc}").format(display=display, exc=exc), "ERROR")
                    return
        # Clear the character JSON disease fields.
        d = safe_load_json(path) or {}
        svc_sync_character_diseases(d, [], self.diseases)
        if self.safe_write_json_with_backup(path, d):
            self.log(tr("已清空疾病 → {display}").format(display=display), "SUCCESS")
            self._load_character_detail(display)
        else:
            self.log(tr("清空疾病失敗 → {display}").format(display=display), "ERROR")

    # ── Persona editor (v0.34) ────────────────────────────────────────────────
    def _persona_current(self):
        """(display, path, data) for the currently-viewed character, or None."""
        display = getattr(self, "_detail_display", None)
        if not display:
            messagebox.showinfo(tr("角色人設"), tr("請先選擇角色"))
            return None
        path = self.plain_to_path.get(display)
        if not path:
            return None
        return display, path, self._staging_effective(path)

    def _persona_open_editor(self) -> None:
        cur = self._persona_current()
        if not cur:
            return
        from dialogs.persona_editor_dialog import open_persona_editor
        open_persona_editor(self, cur[1], cur[2])

    def _persona_export(self) -> None:
        cur = self._persona_current()
        if not cur:
            return
        from dialogs.persona_editor_dialog import open_persona_export
        open_persona_export(self, cur[1], cur[2])

    def _persona_import(self) -> None:
        cur = self._persona_current()
        if not cur:
            return
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        try:
            fields, _kind = svc_persona.parse_import_json(text)
        except ValueError:
            messagebox.showwarning(
                tr("導入人設"),
                tr("剪貼簿內容不是有效的人設 JSON（需含至少一個人設欄位）。"))
            return
        from dialogs.persona_editor_dialog import open_persona_editor
        open_persona_editor(self, cur[1], cur[2], import_fields=fields)

    def _persona_batch_save(self, path, changed: dict) -> None:
        """Write the changed persona fields to *path* in one write + reload."""
        if not changed:
            return
        d = self._staged_checkout(path)
        for field, value in changed.items():
            d[field] = (value or "").rstrip("\n")
        self._staged_store(path, d, tr("已更新角色人設（{n} 欄）").format(n=len(changed)))

    def _resolve_char_name_by_sid(self, string_id: str) -> Optional[str]:
        """Reverse lookup: find a display name given a character StringId.

        Used by SummaryCard to render 'LastSeenFriends' entries with readable names.
        Consults the campaign cache → terminology library → character JSON meta.
        """
        if not string_id:
            return None
        sid = str(string_id).strip()
        if not sid:
            return None
        name, source = svc_resolve_character_name_lib(
            sid,
            primary=self.terminology_primary,
            fallback=self.terminology_fallback,
            campaign=self.terminology_campaign,
            json_resolver=self._resolve_char_name_from_meta,
        )
        if source == "id_only":
            return None
        return name

    def _resolve_char_name_from_meta(self, sid: str) -> Optional[str]:
        """Look up *sid* in character_meta (JSON-backed characters only)."""
        for _display, meta in self.character_meta.items():
            if str(meta.get("StringId", "")).strip() == sid:
                return meta.get("Name") or _display
        return None

    # ── Terminology helpers ─────────────────────────────────────────────
    def _current_campaign_id(self) -> str:
        """Return the currently-selected campaign folder id (empty if none).

        The combobox shows a display label ("name (id)"); this maps it back to
        the real folder id.
        """
        return self._selected_campaign_id()

    # ── Game-status heartbeat (G3) ──────────────────────────────────────
    def _banner_setup_warning(self):
        """Return ``(pill, message, palette_key)`` when setup is incomplete, else None.

        Priority: missing game/campaign path (blocking) > companion mod not
        installed (recommended). Both gate the tool's core features (the database
        tab needs the companion mod), so they take over the banner until fixed.
        """
        sd = getattr(self, "save_data_dir", None)
        gd = getattr(self, "game_dir", None)
        if not sd or not gd:
            return (tr("⚠ 路徑未設定"),
                    tr("尚未正確設定遊戲／戰役位置 — 請前往「設定 → 遊戲檔案位置」確認後再使用。"),
                    "warn_path")
        try:
            st = self._core_mod_status()
            state = getattr(st, "state", None)
            if state == "not_installed":
                return (tr("⚠ 未偵測到核心模組"),
                        tr("找不到核心模組 — 請確認模組已正確安裝於遊戲 Modules 並於啟動器啟用；"
                           "詳見「關於」頁的模組狀態檢查。"),
                        "warn_mod")
            if state == "version_mismatch":
                return (tr("⚠ 核心版本不一致"),
                        tr("核心模組版本（v{inst}）與編輯器（v{tool}）不一致 — 請一併更新，"
                           "詳見「關於」頁的模組狀態檢查。").format(
                               inst=st.installed or "?", tool=st.editor or "?"),
                        "warn_mod")
        except Exception:
            pass
        return None

    def _render_status_banner(self) -> None:
        """Repaint the game-status banner from the last-known game status.

        Split out from the heartbeat tick so it can also be called immediately
        when the tool's loaded campaign changes — the match pill then updates at
        once instead of waiting up to ~10 s for the next heartbeat.
        """
        banner = getattr(self, "game_status_banner", None)
        if banner is None:
            return
        warn = self._banner_setup_warning()
        if warn is not None:
            banner.show_warning(*warn)
        else:
            banner.update_status(getattr(self, "_game_status", None),
                                 tool_campaign_id=self._selected_campaign_id())

    def _tick_game_status(self) -> None:
        """Periodic heartbeat (~10 s) that refreshes the game-status banner.

        The banner also hosts the campaign-match pill; we hand it the tool's
        currently-loaded campaign id so it can compare against the heartbeat's
        in-game campaign.
        """
        try:
            status = svc_check_game_status(
                getattr(self, "exports_ids_dir", None),
                save_data_dir=getattr(self, "save_data_dir", None),
            )
            self._game_status = status
            self._render_status_banner()
        except Exception:
            pass
        finally:
            try:
                self._game_status_after_id = self.root.after(
                    3_000, self._tick_game_status
                )
            except Exception:
                pass

    # ── Campaign terminology cache ──────────────────────────────────────
    def _reload_campaign_terminology(self) -> None:
        """Reload the per-campaign terminology cache for the active campaign.

        Safe to call when no campaign is loaded (clears the in-memory map).
        """
        cid = self._current_campaign_id()
        if cid:
            # Terminology is sourced solely from the Story Master core-module
            # export (dependency-free, includes settlements, refreshed every
            # session).  No mod / no export → empty (ids render raw).
            campaign_dir = getattr(self, "campaign_dir", None)
            sm = (svc_load_storymaster_terminology(campaign_dir, cid)
                  if campaign_dir else None)
            if sm is not None:
                self.terminology_campaign = sm
                self.log(tr("已載入核心模組名詞庫（{cid}）").format(cid=cid), "INFO")
            else:
                self.terminology_campaign = {}
        else:
            self.terminology_campaign = {}
        self._term_index_cache = {}  # invalidate name↔ID indices
        # Refresh settings-tab counts if the tab has been built.
        refresh = getattr(self, "_refresh_terminology_counts", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

    # ── Name ↔ ID resolution (M3 terminology linkage) ──────────────────
    def _terminology_index(self, category: str):
        """Return cached ``(id_to_name, name_index)`` for *category*."""
        cached = self._term_index_cache.get(category)
        if cached is None:
            id_to_name = svc_merged_category(
                category,
                campaign=self.terminology_campaign,
                primary=self.terminology_primary,
                fallback=self.terminology_fallback,
            )
            cached = (id_to_name, svc_name_to_ids_index(id_to_name))
            self._term_index_cache[category] = cached
        return cached

    def terminology_suggest(self, category: str, prefix: str, limit: int = 50):
        """Return up to *limit* ``(id, name)`` autocomplete suggestions."""
        id_to_name, _ = self._terminology_index(category)
        return svc_suggest_names(prefix, id_to_name, limit=limit)

    def resolve_name_or_id(self, category: str, text: str):
        """Resolve a name / id / ``"name (id)"`` to ``(resolved_id, candidates)``."""
        id_to_name, name_index = self._terminology_index(category)
        return svc_resolve_name_or_id(text, id_to_name, name_index)

    def terminology_name_for(self, category: str, id_: str) -> str:
        """Display name for *id_* in *category* (or the id itself when unknown)."""
        id_to_name, _ = self._terminology_index(category)
        return id_to_name.get(str(id_), str(id_))

    def reload_terminology(self) -> None:
        """Reload terminology for the active campaign.

        Terminology is sourced solely from the companion mod's per-campaign
        export; the base/primary/fallback layers stay empty (unknown ids render
        as the raw id)."""
        self.terminology_primary = {}
        self.terminology_fallback = {}
        self._reload_campaign_terminology()

    def resolve_display_name(self, sid: str, *, exclude_library: bool = False):
        """Return ``(display_name, source)`` for a character StringId.

        See :func:`services.terminology_service.resolve_character_name` for
        the meaning of the *source* tag; callers can use it to style
        placeholder fallbacks differently.
        """
        return svc_resolve_character_name_lib(
            sid,
            primary=self.terminology_primary,
            fallback=self.terminology_fallback,
            campaign=self.terminology_campaign,
            json_resolver=self._resolve_char_name_from_meta,
            exclude_library=exclude_library,
        )

    def resolve_kingdom_name(self, kid: str) -> str:
        """Return a translated kingdom name or the raw id when unknown.

        Resolution: campaign cache → primary language → en.json fallback → id.
        """
        name = svc_lookup_with_campaign(
            "kingdoms", kid,
            campaign=self.terminology_campaign,
            primary=self.terminology_primary,
            fallback=self.terminology_fallback,
        )
        return name or (kid or "")

    def resolve_culture_name(self, cid: str) -> str:
        """Return a translated culture name or the raw id when unknown."""
        name = svc_lookup_with_campaign(
            "cultures", cid,
            campaign=self.terminology_campaign,
            primary=self.terminology_primary,
            fallback=self.terminology_fallback,
        )
        return name or (cid or "")

    def resolve_clan_name(self, cid: str) -> str:
        """Return a campaign-cached clan name or the raw id when unknown.

        Clans are dynamic (created/destroyed during play) so the base
        terminology files don't ship with translations — this resolver
        is effectively campaign-cache-only, with the language library as
        a courtesy fallback for any user-entered overrides.
        """
        name = svc_lookup_with_campaign(
            "clans", cid,
            campaign=self.terminology_campaign,
            primary=self.terminology_primary,
            fallback=self.terminology_fallback,
        )
        return name or (cid or "")

    def resolve_settlement_name(self, sid: str) -> str:
        """Return a campaign-cached settlement name or the raw id when unknown.

        Settlements (towns / castles / villages) are supplied by the Story
        Master companion mod's per-campaign export — there's no static base
        file (540 settlements per campaign), so this resolver is effectively
        campaign-cache-only.  Falls back to the raw id (e.g. ``town_V9``)
        when no terminology has been loaded yet.
        """
        name = svc_lookup_with_campaign(
            "settlements", sid,
            campaign=self.terminology_campaign,
            primary=self.terminology_primary,
            fallback=self.terminology_fallback,
        )
        return name or (sid or "")

    def resolve_item_name(self, iid: str) -> str:
        """Return a campaign-cached item name or the raw id when unknown.

        Items are similar to clans — primarily resolved from the campaign
        cache populated by ProemConfig export.
        """
        name = svc_lookup_with_campaign(
            "items", iid,
            campaign=self.terminology_campaign,
            primary=self.terminology_primary,
            fallback=self.terminology_fallback,
        )
        return name or (iid or "")

    def log(self, msg: str, level: str = "INFO"):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{now}] [{level}] {msg}"

        self.log_text.configure(state="normal")
        self.log_text.insert("end", full_msg + "\n")

        if level == "ERROR":
            self.log_text.tag_add("error", "end-1l", "end")
            self.log_text.tag_config("error", foreground=tcol("red"))
        elif level == "SUCCESS":
            self.log_text.tag_add("success", "end-1l", "end")
            self.log_text.tag_config("success", foreground=tcol("green"))

        self.log_text.see("end")
        self.log_text.configure(state="disabled")

        self.quick_log_text.configure(state="normal")
        self.quick_log_text.insert("end", full_msg + "\n")

        if level == "ERROR":
            self.quick_log_text.tag_add("error", "end-1l", "end")
            self.quick_log_text.tag_config("error", foreground=tcol("red"))
        elif level == "SUCCESS":
            self.quick_log_text.tag_add("success", "end-1l", "end")
            self.quick_log_text.tag_config("success", foreground=tcol("green"))

        lines = self.quick_log_text.get("1.0", "end").strip().split("\n")
        if len(lines) > 10:
            self.quick_log_text.delete("1.0", "end")
            self.quick_log_text.insert("end", "\n".join(lines[-10:]) + "\n")

        self.quick_log_text.see("end")
        self.quick_log_text.configure(state="disabled")

        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(full_msg + "\n")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log_file.write_text("")
        self.log(tr("日誌已清除"), "INFO")

    def clear_quick_log(self):
        self.quick_log_text.configure(state="normal")
        self.quick_log_text.delete("1.0", "end")
        self.quick_log_text.configure(state="disabled")

    def export_log(self):
        save_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[(tr("文字檔"), "*.txt")])
        if save_path:
            content = self.log_text.get("1.0", "end")
            Path(save_path).write_text(content, encoding="utf-8")
            self.log(tr("日誌匯出到 {save_path}").format(save_path=save_path), "SUCCESS")

    def search_log(self):
        query = self.log_search_var.get().strip()
        if not query:
            return
        self.log_text.tag_remove("highlight", "1.0", "end")
        idx = "1.0"
        while True:
            idx = self.log_text.search(query, idx, nocase=True, stopindex="end")
            if not idx: break
            end = f"{idx}+{len(query)}c"
            self.log_text.tag_add("highlight", idx, end)
            idx = end
        self.log_text.tag_config("highlight", background=tcol("yellow"))

    def _set_status(self):
        # v0.36: the「已選擇 X 位角色」status label was retired; its spot now
        # hosts the global staging bar. Selection changes still route here so
        # the staging UI (bar + dirty markers) stays in sync.
        self._staging_refresh_ui()


def _show_dev_splash(parent):
    """Borderless centered splash for *source* runs (the frozen build uses the
    PyInstaller native splash instead). Returns the Toplevel, or None."""
    try:
        import tkinter as _tk
        from PIL import Image, ImageTk
        img_path = app_paths.resource_dir() / "assets" / "splash.png"
        if not img_path.exists():
            return None
        top = _tk.Toplevel(parent)
        top.overrideredirect(True)
        # Topmost on purpose: the editor is usually launched from the game's MCM
        # page, so without this the whole cold start happens behind a fullscreen
        # Bannerlord and the user sees nothing until they alt-tab.  The splash is
        # destroyed as soon as the UI is built, so it never lingers on top.
        try:
            top.wm_attributes("-topmost", True)
        except Exception:
            pass
        photo = ImageTk.PhotoImage(Image.open(img_path))
        lbl = _tk.Label(top, image=photo, borderwidth=0, highlightthickness=0)
        lbl.image = photo  # keep a reference so it isn't garbage-collected
        lbl.pack()
        w, h = photo.width(), photo.height()
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        top.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        top.update()
        return top
    except Exception:
        return None


def _raise_to_front(win) -> None:
    """Pull the finished main window in front of whatever is on screen.

    Launching from the game's MCM page means Bannerlord owns the foreground; a
    plain ``lift()`` loses to it, so the window is briefly marked topmost and
    then released — permanent topmost would make the editor impossible to put
    behind the game while playing.
    """
    try:
        win.deiconify()
        win.lift()
        win.wm_attributes("-topmost", True)
        win.focus_force()
        # Release once the window manager has actually raised us.  Guarded
        # because the user may close the window inside the delay.
        def _release():
            try:
                win.wm_attributes("-topmost", False)
            except Exception:
                pass
        win.after(800, _release)
    except Exception:
        pass


def main():
    import sys
    # Load saved theme before creating the window — from the same writable
    # config location the app uses (works in a frozen build too).
    from services.settings_service import build_settings as _build_settings
    _cfg_dir = app_paths.ensure_data_dir() / CONFIG_DIR_NAME
    try:
        _cfg_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    _, _s = _build_settings(_cfg_dir, SETTINGS_FILE)
    from ui import theme as _thememod
    _theme = _thememod.normalize_theme(_s.get("theme", "sandstone"))
    # Set the colour mode before any widget is built so c()/tk defaults are
    # correct on first paint (light mode is unchanged; dark maps via DARK_MAP).
    _thememod.set_mode(_thememod.theme_mode(_theme))
    root = ttk_boot.Window(themename=_theme)
    _thememod.apply_tk_widget_defaults(root)

    # Window / taskbar icon (resolved from the bundled assets).
    try:
        _ico = app_paths.resource_dir() / "assets" / "app.ico"
        if _ico.exists():
            root.iconbitmap(default=str(_ico))
    except Exception:
        pass

    def _close_splash():
        # Frozen builds show a PyInstaller splash during cold start; close it
        # once the UI is constructed. No-op when running from source.
        try:
            import pyi_splash  # type: ignore
            pyi_splash.close()
        except Exception:
            pass

    # Non-interactive smoke test for the frozen build: construct the whole UI
    # without entering the event loop, then exit. Verifies the PyInstaller
    # bundle has every import/asset and that paths resolve in frozen mode.
    if "--selftest" in sys.argv:
        root.withdraw()
        app = AIInfluenceStoryToolsApp(root)
        root.update()
        _close_splash()
        print("[selftest] OK — UI constructed; frozen=%s data_dir=%s"
              % (app_paths.is_frozen(), getattr(app, "data_dir", "?")))
        root.destroy()
        return

    # Dev splash (source runs only); frozen builds rely on the native splash.
    dev_splash = _show_dev_splash(root) if not app_paths.is_frozen() else None

    app = AIInfluenceStoryToolsApp(root)

    # Center the main window on screen (slightly above middle).
    try:
        root.update_idletasks()
        w = root.winfo_width() if root.winfo_width() > 1 else root.winfo_reqwidth()
        h = root.winfo_height() if root.winfo_height() > 1 else root.winfo_reqheight()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        root.geometry(f"+{x}+{y}")
    except Exception:
        pass

    if dev_splash is not None:
        try:
            dev_splash.destroy()
        except Exception:
            pass
    _close_splash()
    _raise_to_front(root)
    root.mainloop()

if __name__ == "__main__":
    main()
