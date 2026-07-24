"""Character summary card — rich tk.Text + tags architecture.

Shows a structured, section-filtered view of a character's full state:
  • 基本資訊   — name, ID, party, stats, info/secret/conv counts
  • AI 生成    — CharacterDescription, AIGeneratedPersonality / Backstory / SpeechQuirks
  • 當前狀態   — EmotionalState, NPCForces (party size / wounded)
  • 最後見到的朋友 — LastSeenFriends dict with name resolution + game time
  • 最近 AI 回應 — parsed LastAIResponseJson (internal_thoughts / response / decision fields)
  • 疾病       — IsSick / IsTreated / CurrentDiseases

Section visibility is controlled by top checkboxes (persistent across character switch).

Edit mode (top checkbox) drives a persistent 操作 bar (編輯屬性 / 編輯人設 ▾ /
快速清空 ▾) that greys out — but stays visible — outside edit mode. Persona
editing happens in a dedicated window (dialogs.persona_editor_dialog); the
summary shows the persona read-only. The ⓘ 說明 button (top-right) is always
available.

Callbacks
---------
  on_field_save(field_name, new_value)   — save one AI-generated text field
  on_attr_edit()                          — open the 編輯屬性 dialog
  on_quick_clear(kind, fields)            — 快速清空 dispatch; kind in
      {"attrs","status","diseases","response"}; fields = set|None
  on_persona_edit/export/import()         — persona editor window / export / import
  resolve_character_name(string_id)      — Optional[str] — resolve StringId → display name

Usage::

    card = SummaryCard(parent, on_field_save=app._summary_field_save,
                       on_quick_clear=app._summary_quick_clear,
                       on_attr_edit=app._summary_attr_edit,
                       resolve_character_name=lambda sid: ...)
    card.pack(fill="both", expand=True)
    card.load(character_data, meta, is_favorite=True)
    card.clear()
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

from i18n import tr
from services.json_utils import parse_last_ai_response
from services.time_format import format_game_time
from services.display_labels import mood_label
from ui import preview_font
from widgets.window_center import center_window
from widgets.popover_menu import attach_menu
from dialogs.clear_fields_dialog import open_clear_checklist
from services.character_service import (
    player_trust_level,
    player_interaction_count,
    player_romance_level,
    player_escalation_state,
)
from ui.theme import tcol


# ── Section keys / labels / default visibility ────────────────────────────────
_SECTIONS: List[tuple] = [
    ("basic",    "基本",  True),  # noqa: cjk
    ("ai_gen",   "人設",  True),  # noqa: cjk
    ("status",   "狀態",  True),  # noqa: cjk
    ("diseases", "疾病",  True),  # noqa: cjk
    ("friends",  "好友",  True),  # noqa: cjk
    ("ai_resp",  "回應",  True),  # noqa: cjk
]

# AI-generated text fields (shown as expandable paragraphs, editable in edit mode).
_AI_GEN_FIELDS: List[tuple] = [
    ("CharacterDescription",     "角色描述"),  # noqa: cjk
    ("AIGeneratedPersonality",   "角色性格"),  # noqa: cjk
    ("AIGeneratedBackstory",     "背景故事"),  # noqa: cjk
    ("AIGeneratedSpeechQuirks",  "說話習慣"),  # noqa: cjk
    ("AIGeneratedCognitiveStyle","認知風格"),  # noqa: cjk
]

# LastAIResponseJson decision / effect keys to show (non-empty only).
# internal_thoughts and response handled separately.
_AI_RESP_DECISION_KEYS: List[tuple] = [
    ("tone",                 "語氣"),  # noqa: cjk
    ("threat_level",         "威脅等級"),  # noqa: cjk
    ("escalation_state",     "情緒升降"),  # noqa: cjk
    ("romance_intent",       "浪漫意圖"),  # noqa: cjk
    ("decision",             "決定"),  # noqa: cjk
    ("kingdom_action",       "王國行動"),  # noqa: cjk
    ("kingdom_action_reason", "王國行動理由"),  # noqa: cjk
    ("suspected_lie",        "疑似說謊"),  # noqa: cjk
    ("deescalation_attempt", "降溫嘗試"),  # noqa: cjk
    ("claimed_name",         "自稱姓名"),  # noqa: cjk
    ("claimed_clan",         "自稱氏族"),  # noqa: cjk
    ("claimed_age",          "自稱年齡"),  # noqa: cjk
    ("claimed_gold",         "自稱金錢"),  # noqa: cjk
    ("allows_letters",       "允許書信"),  # noqa: cjk
    ("settlement_id",        "目標領地"),  # noqa: cjk
    ("target_clan_id",       "目標氏族"),  # noqa: cjk
    ("money_transfer",       "金錢轉移"),  # noqa: cjk
    ("item_transfers",       "物品轉移"),  # noqa: cjk
    ("character_death",      "角色死亡"),  # noqa: cjk
    ("technical_action",     "技術動作"),  # noqa: cjk
    ("workshop_action",      "作坊動作"),  # noqa: cjk
    ("workshop_string_id",   "作坊 ID"),  # noqa: cjk
    ("navigate_to_npc",      "導航目標"),  # noqa: cjk
    ("talk_to_npc",          "對話目標"),  # noqa: cjk
    ("follow_npc",           "跟隨目標"),  # noqa: cjk
    ("tts_instructions",     "TTS 指令"),  # noqa: cjk
]

# Values considered "empty" for decision keys (suppressed unless non-empty).
_EMPTY_VALUES = (None, "", "none", "None", False, 0, 0.0, [], {})


def _is_meaningful(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str) and v.strip().lower() in ("", "none"):
        return False
    if isinstance(v, bool):
        return v  # only show True booleans
    if isinstance(v, (int, float)) and v == 0:
        return False
    if isinstance(v, (list, dict)) and len(v) == 0:
        return False
    return True


# ── Main widget ───────────────────────────────────────────────────────────────
class SummaryCard(ttk.Frame):
    """Rich character summary panel backed by a single tk.Text widget."""

    def __init__(
        self,
        parent,
        *,
        on_field_save: Optional[Callable[[str, str], None]] = None,
        on_quick_clear: Optional[Callable[[str, Optional[set]], None]] = None,
        on_attr_edit: Optional[Callable[[], None]] = None,
        resolve_character_name: Optional[Callable[[str], Optional[str]]] = None,
        on_persona_edit: Optional[Callable[[], None]] = None,
        on_persona_export: Optional[Callable[[], None]] = None,
        on_persona_import: Optional[Callable[[], None]] = None,
        edit_variable: Optional[tk.BooleanVar] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._on_field_save = on_field_save
        self._on_quick_clear = on_quick_clear
        self._on_attr_edit = on_attr_edit
        self._resolve_name = resolve_character_name
        self._on_persona_edit = on_persona_edit
        self._on_persona_export = on_persona_export
        self._on_persona_import = on_persona_import

        # State
        self._data: Dict[str, Any] = {}
        self._meta: Dict[str, Any] = {}
        self._is_favorite: bool = False
        # edit_variable: pass the app-wide shared var so edit mode toggles
        # everywhere at once; omit for a standalone per-widget toggle.
        self._editing = edit_variable if edit_variable is not None else tk.BooleanVar(value=False)
        self._editing.trace_add("write", lambda *_: self._re_render())

        # Section visibility vars (default: all visible). Persist across loads.
        self._section_vars: Dict[str, tk.BooleanVar] = {}
        for skey, _, default in _SECTIONS:
            v = tk.BooleanVar(value=default)
            v.trace_add("write", lambda *_: self._re_render())
            self._section_vars[skey] = v

        # Inline edit widgets: AI-gen field key → embedded tk.Text. Rebuilt every re-render.
        self._edit_widgets: Dict[str, tk.Text] = {}

        self._build_header()
        self._build_body()
        # Initial empty state
        self._re_render()

    # ── Public API ──────────────────────────────────────────────────────────
    def load(
        self,
        data: Dict[str, Any],
        meta: Optional[Dict[str, Any]] = None,
        is_favorite: bool = False,
    ) -> None:
        new_data = data or {}
        # Reset scroll only when the character actually changes; same-character
        # reloads (field save / reset) and section toggles keep the position.
        changed = str(new_data.get("StringId", "")) != str((self._data or {}).get("StringId", ""))
        self._data = new_data
        self._meta = meta or {}
        self._is_favorite = bool(is_favorite)
        self._re_render(reset_scroll=changed)

    def clear(self) -> None:
        self._data = {}
        self._meta = {}
        self._is_favorite = False
        self._re_render(reset_scroll=True)

    # ── Build: header & body ────────────────────────────────────────────────
    def _build_header(self) -> None:
        hdr = ttk.Frame(self)
        hdr.pack(fill=tk.X, padx=6, pady=(6, 2))

        # Row 1: edit checkbox (left) + 說明 (right, always available)
        row1 = ttk.Frame(hdr)
        row1.pack(fill=tk.X)
        ttk.Checkbutton(row1, text=tr("編輯模式"),
                        variable=self._editing).pack(side=tk.LEFT)
        ttk.Button(row1, text=tr("ⓘ 說明"), style="secondary.TButton",
                   command=self._show_persona_help).pack(side=tk.RIGHT)

        # Row 2: section filter checkboxes
        row2 = ttk.Frame(hdr)
        row2.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(row2, text=tr("顯示:"),
                  foreground=tcol("#6B5B3E")).pack(side=tk.LEFT, padx=(0, 4))
        for skey, slabel, _ in _SECTIONS:
            ttk.Checkbutton(
                row2, text=tr(slabel),
                variable=self._section_vars[skey],
            ).pack(side=tk.LEFT, padx=2)

        # Row 3: operation bar — greyed (not hidden) outside edit mode.
        row3 = ttk.Frame(hdr)
        row3.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(row3, text=tr("操作:"),
                  foreground=tcol("#6B5B3E")).pack(side=tk.LEFT, padx=(0, 4))
        self._op_buttons: List[ttk.Button] = []
        attr_btn = ttk.Button(row3, text=tr("編輯屬性"), style="info.TButton",
                              command=self._attr_edit)
        attr_btn.pack(side=tk.LEFT, padx=2)
        persona_btn = ttk.Button(row3, text=tr("編輯人設 ▾"), style="info.TButton")
        persona_btn.pack(side=tk.LEFT, padx=2)
        attach_menu(persona_btn, [
            (tr("✏ 編輯"), self._persona_edit),
            (tr("📤 導出"), self._persona_export),
            (tr("📥 導入"), self._persona_import),
        ], direction="down")
        clear_btn = ttk.Button(row3, text=tr("快速清空 ▾"), style="info.TButton")
        clear_btn.pack(side=tk.LEFT, padx=2)
        attach_menu(clear_btn, [
            (tr("清空屬性"), self._open_clear_attrs),
            (tr("清空狀態"), self._open_clear_status),
            (tr("清空疾病"), lambda: self._quick_clear("diseases", None), "danger"),
            (tr("清空回應"), lambda: self._quick_clear("response", None), "danger"),
        ], direction="down")
        self._op_buttons = [attr_btn, persona_btn, clear_btn]

        # Thin separator
        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6, pady=(4, 0))

    # ── Operation-bar actions ─────────────────────────────────────────────────
    def _attr_edit(self) -> None:
        if self._on_attr_edit:
            self._on_attr_edit()

    def _quick_clear(self, kind: str, fields: Optional[set]) -> None:
        if self._on_quick_clear:
            self._on_quick_clear(kind, fields)

    def _open_clear_attrs(self) -> None:
        open_clear_checklist(
            self.winfo_toplevel(), tr("清空屬性"),
            [("romance", tr("浪漫")),
             ("trust", tr("信任")),
             ("relation", tr("關係")),
             ("interaction", tr("互動"))],
            on_confirm=lambda keys: self._quick_clear("attrs", keys),
        )

    def _open_clear_status(self) -> None:
        open_clear_checklist(
            self.winfo_toplevel(), tr("清空狀態"),
            [("mood", tr("情緒")),
             ("party", tr("隊伍規模")),
             ("war", tr("戰爭狀態")),
             ("task", tr("當前任務"))],
            on_confirm=lambda keys: self._quick_clear("status", keys),
        )

    def _show_persona_help(self) -> None:
        """Two-level tabbed help for the whole 摘要 page.

        Outer tabs 概念說明 / 編輯說明; each currently holds a single inner tab
        (角色人設 / 編輯人設).  Framework only for now — more inner tabs can be
        added later without restructuring.
        """
        win = tk.Toplevel(self)
        win.title(tr("摘要說明"))
        win.transient(self.winfo_toplevel())
        win.grab_set()
        center_window(win, 660, 600)

        outer = ttk.Notebook(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

        def _text_tab(nb: ttk.Notebook, title: str, build) -> None:
            f = ttk.Frame(nb)
            nb.add(f, text=title)
            txtf = ttk.Frame(f)
            txtf.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            txt = tk.Text(txtf, wrap="word", font=("Microsoft JhengHei", 10),
                          relief="flat", padx=10, pady=8, spacing1=2, spacing3=4)
            vsb = ttk.Scrollbar(txtf, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=vsb.set)
            txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            txt.tag_configure("h", font=("Microsoft JhengHei", 11, "bold"),
                              foreground=tcol("#1A3A5C"), spacing1=8, spacing3=4)
            txt.tag_configure("warn", foreground=tcol("#A15C00"),
                              font=("Microsoft JhengHei", 10, "bold"))
            build(txt)
            txt.configure(state="disabled")

        def _sub_notebook(parent_title: str):
            f = ttk.Frame(outer)
            outer.add(f, text=parent_title)
            inner = ttk.Notebook(f)
            inner.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
            return inner

        def _fields(txt: tk.Text) -> None:
            txt.insert("end", tr("「角色描述」"), "h")
            txt.insert("end", tr("\n是提供玩家自由編寫的欄位，AI 不會主動寫入。\n常見用途：\n"
                                 "　1. 當「角色性格／背景故事／說話習慣／認知風格」四欄為空時，"
                                 "先填寫「角色描述」，AI 生成人設時會參考它——等於人設草稿。\n"
                                 "　2. 想更深度掌控角色時，可在 AI 生成後於「角色描述」自由補充"
                                 "（外貌、目標、近況、人際關係等）以豐富人設。\n"))
            txt.insert("end", tr("\n「角色性格／背景故事／說話習慣／認知風格」"), "h")
            txt.insert("end", tr("\n是 AI 生成的人設：\n"
                                 "　• 預設會在玩家初次與該 NPC 對話時，由 AI 依世界觀背景、"
                                 "動態事件、角色描述等可用資訊自動生成。\n"
                                 "　• 生成後可自由編輯，也可在 AI 生成前先自行撰寫。\n"))

        def _edit_persona(txt: tk.Text) -> None:
            txt.insert("end", tr("開啟編輯視窗") + "\n", "h")
            txt.insert("end", tr("進入編輯模式後，於「操作 → 編輯人設 ▾ → ✏ 編輯」展開專用編輯視窗：\n　• 預設只顯示編輯欄，視窗維持在剛好夠寫作的寬度。\n　• 支援 Ctrl+Z 復原、Ctrl+Y 重做、Ctrl+A 全選，像一般文字編輯器。\n　• 五組欄位間的灰色拖曳條可上下拖曳，調整該欄高度（各欄同步）。\n　• 整頁可上下捲動；底部操作列固定不動。\n　• 「完成」只寫入你實際改動過的欄位。\n"))
            txt.insert("end", tr("原文參照與第三方參照") + "\n", "h")
            txt.insert("end", tr("底列有兩個參照開關，開啟哪一個視窗就往右加寬多少：\n　•「＋ 原文參照」＝在最左加一欄唯讀原文，方便和你改動後的內容對照。\n　•「＋ 第三方參照」＝在最右加一欄唯讀參照；於「第三方角色：」搜尋並選取\n　　另一位角色（打名字或 ID）→「載入參照」，即可載入該角色的人設。\n因此視窗有三種寬度：僅編輯／編輯＋單一參照／編輯＋雙參照。\n參照欄皆不可編輯；再點同一顆按鈕即可收起。\n（從剪貼簿導入人設時會自動開啟原文參照，方便逐欄核對。）\n"))
            txt.insert("end", tr("導出／導入") + "\n", "h")
            txt.insert("end", tr("底列「📤 導出」＝向上展開面板：勾選要導出的欄位（預設全選）→ 以 JSON\n　複製到剪貼簿（含 _meta：角色名／StringId）。導出內容以編輯欄當前文字為準。\n底列「📥 導入」＝把剪貼簿裡的人設 JSON（或整個角色 JSON）貼回，\n　工具自動解析並覆蓋對應的編輯欄，讓你左右對照後再按「完成」寫入。\n（摘要「操作 → 編輯人設 ▾」的導出／導入為相同功能的快速入口。）\n"))
            txt.insert("end", tr("⚠ 務必在「退出戰役、回到主選單」時編輯，否則戰役進行中"
                                 "存檔會被遊戲覆蓋而遺失。"), "warn")

        concept = _sub_notebook(tr("概念說明"))
        _text_tab(concept, tr("角色人設"), _fields)
        editing = _sub_notebook(tr("編輯說明"))
        _text_tab(editing, tr("編輯人設"), _edit_persona)

        ttk.Button(win, text=tr("關閉"), command=win.destroy,
                   style="secondary.TButton").pack(side=tk.BOTTOM, anchor="e",
                                                    padx=12, pady=(0, 10))

    def _build_body(self) -> None:
        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 6))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._text = tk.Text(
            body, wrap="word", state="disabled",
            font=("Microsoft JhengHei", 10),
            spacing1=2, spacing3=2,
            cursor="arrow", relief="flat",
            padx=8, pady=6,
        )
        vsb = ttk.Scrollbar(body, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        self._text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._configure_tags()
        preview_font.register(self._text)

    def _configure_tags(self) -> None:
        t = self._text
        t.tag_configure("title",
                        font=("Microsoft JhengHei", 14, "bold"),
                        foreground=tcol("#1A3A5C"),
                        spacing3=4)
        t.tag_configure("fav",
                        font=("Microsoft JhengHei", 14, "bold"),
                        foreground=tcol("#D4AC0D"))
        t.tag_configure("section",
                        font=("Microsoft JhengHei", 12, "bold"),
                        foreground=tcol("#2471A3"),
                        spacing1=10, spacing3=4)
        t.tag_configure("sep", foreground=tcol("#BBBBBB"))
        t.tag_configure("key",
                        font=("Microsoft JhengHei", 10, "bold"),
                        foreground=tcol("#6B5B3E"))
        t.tag_configure("val",
                        font=("Microsoft JhengHei", 10),
                        foreground=tcol("#333333"))
        t.tag_configure("body",
                        font=("Microsoft JhengHei", 10),
                        foreground=tcol("#222222"),
                        lmargin1=16, lmargin2=16)
        t.tag_configure("field_label",
                        font=("Microsoft JhengHei", 11, "bold"),
                        foreground=tcol("#884EA0"),
                        spacing1=4, spacing3=2)
        t.tag_configure("empty",
                        font=("Microsoft JhengHei", 10, "italic"),
                        foreground=tcol("#999999"))
        t.tag_configure("mood",
                        font=("Microsoft JhengHei", 10, "bold"),
                        foreground=tcol("#C94A2C"))
        t.tag_configure("friend_line",
                        font=("Microsoft JhengHei", 10),
                        foreground=tcol("#1A5276"),
                        lmargin1=16, lmargin2=16)
        t.tag_configure("friend_sid",
                        font=("Microsoft JhengHei", 9),
                        foreground=tcol("#999999"))
        t.tag_configure("friend_time",
                        font=("Microsoft JhengHei", 9),
                        foreground=tcol("#6B5B3E"))
        t.tag_configure("ai_box",
                        font=("Microsoft JhengHei", 10),
                        foreground=tcol("#222222"),
                        background=tcol("#F5F2EA"),
                        lmargin1=16, lmargin2=16,
                        spacing1=2, spacing3=2)
        t.tag_configure("ai_key",
                        font=("Microsoft JhengHei", 9, "bold"),
                        foreground=tcol("#555555"))
        t.tag_configure("ai_subhead",
                        font=("Microsoft JhengHei", 10, "bold"),
                        foreground=tcol("#884EA0"),
                        spacing1=4)
        t.tag_configure("warn", foreground=tcol("#C0392B"))
        t.tag_configure("ok",   foreground=tcol("#1A8A4A"))
        t.tag_configure("placeholder",
                        font=("Microsoft JhengHei", 9, "italic"),
                        foreground=tcol("#AAAAAA"))

    # ── Re-render ───────────────────────────────────────────────────────────
    def _re_render(self, reset_scroll: bool = False) -> None:
        t = self._text
        prev_top = t.yview()[0]
        t.configure(state="normal")
        # Clearing text also destroys any embedded windows (tk.Text window_create).
        t.delete("1.0", "end")
        self._edit_widgets.clear()

        # Sync header buttons visibility (edit mode controls reset button visibility).
        self._sync_header_buttons()

        if not self._data:
            t.insert("end", tr("（請選擇角色）"), "empty")
            t.configure(state="disabled")
            return

        renderers = {
            "basic":    self._render_basic,
            "ai_gen":   self._render_ai_gen,
            "status":   self._render_status,
            "friends":  self._render_friends,
            "ai_resp":  self._render_ai_resp,
            "diseases": self._render_diseases,
        }
        for skey, _, _ in _SECTIONS:
            if self._section_vars[skey].get():
                renderers[skey](t)

        t.configure(state="disabled")
        # New character → top; same-character re-render (edit / toggle) → stay put.
        if reset_scroll:
            t.see("1.0")
        else:
            t.yview_moveto(prev_top)

    def _sync_header_buttons(self) -> None:
        # Operation bar stays visible but greys out when not in edit mode.
        state = "normal" if self._editing.get() else "disabled"
        for b in getattr(self, "_op_buttons", []):
            try:
                b.configure(state=state)
            except Exception:
                pass

    # ── Section: 基本資訊 ───────────────────────────────────────────────────
    def _render_basic(self, t: tk.Text) -> None:
        data, meta = self._data, self._meta
        name = (data.get("Name") or data.get("DisplayName")
                or data.get("CharacterName") or meta.get("Name") or "")
        t.insert("end", str(name), "title")
        if self._is_favorite:
            t.insert("end", "  ★", "fav")
        t.insert("end", "\n")

        sid     = meta.get("StringId") or data.get("StringId") or ""
        in_p    = bool(meta.get("IsInPlayerParty", data.get("IsInPlayerParty", False)))
        # Read trust/romance/interaction via the schema bridge so 5.0.x
        # (CounterpartySocial / RomancePartners) and 4.1.0 (top-level) both work.
        rom     = meta.get("RomanceLevel",   player_romance_level(data))
        trust   = meta.get("TrustLevel",     player_trust_level(data))
        rel     = meta.get("RelationValue",  0)
        inter   = meta.get("InteractionCount", player_interaction_count(data))

        info_n = len(data.get("KnownInfo", []) or []) if isinstance(data.get("KnownInfo"), list) else 0
        sec_n  = len(data.get("KnownSecrets", []) or []) if isinstance(data.get("KnownSecrets"), list) else 0
        conv_n = len(data.get("ConversationHistory", []) or []) if isinstance(data.get("ConversationHistory"), list) else 0
        rec_n  = len(data.get("RecentEvents", []) or []) if isinstance(data.get("RecentEvents"), list) else 0
        dyn_n  = len(data.get("DynamicEvents", []) or []) if isinstance(data.get("DynamicEvents"), list) else 0

        def kv(k: str, v: str, sep: str = "  ｜  ") -> None:
            t.insert("end", f"{k}: ", "key")
            t.insert("end", v, "val")
            t.insert("end", sep, "val")

        # Line 1: ID + party
        t.insert("end", "ID: ", "key")
        t.insert("end", str(sid), "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('隊伍')}: ", "key")
        t.insert("end", ("✓" if in_p else "✗"), ("ok" if in_p else "warn"))
        t.insert("end", "\n")

        # Line 2: romance / trust / relation / interaction
        t.insert("end", f"{tr('浪漫')}: ", "key")
        t.insert("end", _fmt_num(rom), "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('信任')}: ", "key")
        t.insert("end", _fmt_num(trust), "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('關係')}: ", "key")
        t.insert("end", _fmt_num(rel), "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('互動')}: ", "key")
        t.insert("end", _fmt_num(inter), "val")
        t.insert("end", "\n")

        # Line 3: info / secret / conv / events counts
        t.insert("end", f"{tr('訊息')}: ", "key")
        t.insert("end", str(info_n), "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('秘密')}: ", "key")
        t.insert("end", str(sec_n), "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('對話')}: ", "key")
        t.insert("end", f"{conv_n} {tr('筆')}", "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('近期')}: ", "key")
        t.insert("end", str(rec_n), "val")
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('事件')}: ", "key")
        t.insert("end", str(dyn_n), "val")
        t.insert("end", "\n")

        _insert_sep(t)

    # ── Section: 角色人設 ───────────────────────────────────────────────────
    def _render_ai_gen(self, t: tk.Text) -> None:
        # Persona is shown read-only here; all persona actions (編輯/導出/導入)
        # now live in the header's 操作 → 編輯人設 ▾ menu.
        t.insert("end", f"▋ {tr('人設')}\n", "section")

        any_content = False
        for key, label in _AI_GEN_FIELDS:
            raw = self._data.get(key)
            text_val = str(raw).strip() if raw else ""
            if not text_val:
                continue
            any_content = True
            t.insert("end", f"【{tr(label)}】\n", "field_label")
            t.insert("end", text_val + "\n", "body")
            t.insert("end", "\n")

        if not any_content:
            t.insert("end", tr("（無角色人設資料）") + "\n", "empty")

        _insert_sep(t)

    def _persona_edit(self) -> None:
        if self._on_persona_edit:
            self._on_persona_edit()

    def _persona_export(self) -> None:
        if self._on_persona_export:
            self._on_persona_export()

    def _persona_import(self) -> None:
        if self._on_persona_import:
            self._on_persona_import()

    # ── Section: 當前狀態 ───────────────────────────────────────────────────
    def _render_status(self, t: tk.Text) -> None:
        t.insert("end", f"▋ {tr('當前狀態')}\n", "section")

        data = self._data
        any_shown = False

        # EmotionalState
        emo = data.get("EmotionalState") or {}
        if isinstance(emo, dict) and emo:
            mood   = str(emo.get("Mood", "")).strip()
            reason = str(emo.get("Reason", "")).strip()
            if mood or reason:
                any_shown = True
                t.insert("end", f"  {tr('情緒')}: ", "key")
                if mood:
                    t.insert("end", mood_label(mood), "mood")
                if reason:
                    t.insert("end", f"  （{tr('理由')}: {reason}）", "val")
                t.insert("end", "\n")

        # NPCForces — party size / wounded / has army
        forces = data.get("NPCForces") or {}
        if isinstance(forces, dict) and forces:
            psize = forces.get("PartySize", 0)
            try:
                psize_n = int(psize)
            except (TypeError, ValueError):
                psize_n = 0
            if psize_n > 0 or forces.get("HasArmy"):
                any_shown = True
                wounded = float(forces.get("WoundedPercentage", 0) or 0)
                has_army = bool(forces.get("HasArmy", False))
                t.insert("end", f"  {tr('隊伍規模')}: ", "key")
                t.insert("end", f"{psize_n} {tr('人')}", "val")
                t.insert("end", f"  （{tr('傷兵')} {wounded:.0%}）", "val")
                if has_army:
                    t.insert("end", f"  ⚔ {tr('率領部隊')}", "warn")
                t.insert("end", "\n")

        # WarStatus (single line summary)
        war = str(data.get("WarStatus", "")).strip()
        if war:
            any_shown = True
            # Keep only first sentence / 80 chars to stay compact
            short = war if len(war) <= 100 else war[:97] + "..."
            t.insert("end", f"  {tr('戰爭狀態')}: ", "key")
            t.insert("end", short + "\n", "val")

        # CurrentTask
        task = str(data.get("CurrentTask", "")).strip()
        if task:
            any_shown = True
            t.insert("end", f"  {tr('當前任務')}: ", "key")
            t.insert("end", task + "\n", "val")

        # EscalationState (only if not 'neutral') — 5.0.x nests it under
        # CounterpartySocial.main_hero; 4.1.0 had it top-level.
        esc = str(player_escalation_state(data)).strip()
        if esc and esc.lower() != "neutral":
            any_shown = True
            t.insert("end", f"  {tr('情緒升降')}: ", "key")
            t.insert("end", esc + "\n", "warn")

        if not any_shown:
            t.insert("end", tr("（無狀態資料）") + "\n", "empty")

        _insert_sep(t)

    # ── Section: 最後見到的朋友 ─────────────────────────────────────────────
    def _render_friends(self, t: tk.Text) -> None:
        t.insert("end", f"▋ {tr('最後見到的朋友')}\n", "section")

        friends = self._data.get("LastSeenFriends") or {}
        if not isinstance(friends, dict) or not friends:
            t.insert("end", tr("（無朋友記錄）") + "\n", "empty")
            _insert_sep(t)
            return

        # Sort by days DESC (most recent first).
        try:
            entries = sorted(friends.items(), key=lambda kv: -float(kv[1]))
        except (TypeError, ValueError):
            entries = list(friends.items())

        for sid, days in entries:
            # main_hero is always the player character.
            if str(sid) == "main_hero":
                name: Optional[str] = tr("玩家")
            elif self._resolve_name is not None:
                try:
                    name = self._resolve_name(str(sid))
                except Exception:
                    name = None
            else:
                name = None

            try:
                time_label = format_game_time(float(days))
            except (TypeError, ValueError):
                time_label = str(days)

            t.insert("end", "  • ", "friend_line")
            if name:
                t.insert("end", str(name), "friend_line")
            else:
                t.insert("end", tr("無名詞"), "placeholder")
            t.insert("end", f"  ({sid})", "friend_sid")
            t.insert("end", f"   — {time_label}\n", "friend_time")

        _insert_sep(t)

    # ── Section: 最近 AI 回應 ───────────────────────────────────────────────
    def _render_ai_resp(self, t: tk.Text) -> None:
        t.insert("end", f"▋ {tr('最近 AI 回應')}\n", "section")

        raw = self._data.get("LastAIResponseJson")
        parsed = parse_last_ai_response(raw)

        if not parsed:
            # Fall back to LastDynamicResponse (plain string) if present
            last_dyn = str(self._data.get("LastDynamicResponse", "") or "").strip()
            if last_dyn:
                t.insert("end", f"  【{tr('實際回應')}】\n", "ai_subhead")
                t.insert("end", last_dyn + "\n", "ai_box")
            else:
                t.insert("end", tr("（無 AI 回應記錄）") + "\n", "empty")
            _insert_sep(t)
            return

        # Thoughts
        thoughts = str(parsed.get("internal_thoughts", "") or "").strip()
        if thoughts:
            t.insert("end", f"  【{tr('思考過程')}】\n", "ai_subhead")
            t.insert("end", thoughts + "\n", "ai_box")

        # Actual response
        response = str(parsed.get("response", "") or "").strip()
        if response:
            t.insert("end", f"  【{tr('實際回應')}】\n", "ai_subhead")
            t.insert("end", response + "\n", "ai_box")

        # Decision / effect keys (only meaningful, non-empty ones)
        decision_lines: List[tuple] = []
        for key, label in _AI_RESP_DECISION_KEYS:
            val = parsed.get(key)
            if not _is_meaningful(val):
                continue
            # Special formatting
            if isinstance(val, bool):
                disp = "✓" if val else "✗"
            elif isinstance(val, (list, dict)):
                disp = str(val)
            else:
                disp = str(val)
            decision_lines.append((label, disp))

        if decision_lines:
            t.insert("end", f"  【{tr('決策/效果')}】\n", "ai_subhead")
            for label, disp in decision_lines:
                t.insert("end", f"    {tr(label)}: ", "ai_key")
                t.insert("end", disp + "\n", "ai_box")

        _insert_sep(t)

    # ── Section: 疾病 ──────────────────────────────────────────────────────
    def _render_diseases(self, t: tk.Text) -> None:
        t.insert("end", f"▋ {tr('疾病')}\n", "section")

        data = self._data
        is_sick  = bool(data.get("IsSick", False))
        is_treat = bool(data.get("IsTreated", False))
        progress = float(data.get("DiseaseProgress", 0) or 0)
        current  = data.get("CurrentDiseases") or []

        t.insert("end", f"  {tr('是否生病')}: ", "key")
        t.insert("end", ("✓" if is_sick else "✗"),
                 ("warn" if is_sick else "ok"))
        t.insert("end", "  ｜  ", "val")
        t.insert("end", f"{tr('治療中')}: ", "key")
        t.insert("end", ("✓" if is_treat else "✗"),
                 ("ok" if is_treat else "val"))
        if is_sick:
            t.insert("end", "  ｜  ", "val")
            t.insert("end", f"{tr('進度')}: ", "key")
            t.insert("end", f"{progress:.1f}%", "val")
        t.insert("end", "\n")

        if isinstance(current, list) and current:
            t.insert("end", f"  {tr('當前疾病')}:\n", "key")
            for d in current:
                name = d.get("name", "?")
                sev  = d.get("severity_description", "")
                prog = d.get("progress", 0.0)
                tr_flag = "✓" if d.get("is_treated") else "✗"
                t.insert("end", f"    • {name}", "val")
                if sev:
                    t.insert("end", f"  ({sev})", "friend_sid")
                t.insert("end", f"  {tr('進度')} {prog:.0f}%  ｜  {tr('治療中')}: {tr_flag}\n", "val")
        elif is_sick:
            t.insert("end", f"  {tr('當前疾病')}: ", "key")
            t.insert("end", tr("（無詳細資料）") + "\n", "empty")

        _insert_sep(t)

# ── Module helpers ────────────────────────────────────────────────────────────

def _insert_sep(t: tk.Text) -> None:
    t.insert("end", "─" * 60 + "\n", "sep")


def _fmt_num(v: Any) -> str:
    """Compact number formatter — integer if whole, else one decimal."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return str(int(f))
    return f"{f:.1f}"
