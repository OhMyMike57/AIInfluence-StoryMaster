"""對話歷史 — list on top, full preview below (v1.1.0 rework).

The old viewer rendered the whole history into one tall ``tk.Text`` with
per-row text checkboxes.  Picking the lines you wanted meant clicking tiny ○
glyphs scattered down a wall of prose, and long lines pushed the next speaker
off-screen.  This page follows 對話觀察 instead:

    ┌ 行 │ 說話者 │ 類型 │ 內容摘要 ────────────┐  ← Treeview, native
    │ … selectable, multi-select, Ctrl+A          │    multi-select
    ├──────────────────────────────────────────── ┤  6:4 split
    │ full text of the highlighted line           │  ← preview, coloured
    └─────────────────────────────────────────────┘

Row colours come from :func:`services.json_utils.line_category`, so every line
type AI Influence writes — player (before and after introducing themselves),
the character's own lines, other NPCs, eavesdropped lines, battle shouts, story
tags, legacy long-term memories, gap notices and un-prefixed plain text — is
distinguishable at a glance in both the light and dark themes.

Edit mode gates the action row (同步 / 編寫 / 導出·導入 / 刪除), exactly like
對話觀察 and 記憶之書.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Dict, List, Optional

from i18n import tr
from services import conversation_transfer as CT
from services import speaker_format as SF
from services import terminology_service as svc_terminology
from services.json_utils import (
    line_category, parse_conversation_line, speaker_display, split_line_prefix,
)
from ui import msgbox as messagebox
from ui import preview_font
from ui.theme import tcol
from ui.tree_helpers import enable_drag_select
from widgets.popover_menu import PopoverMenu, attach_menu
from widgets.speaker_field import SpeakerField

_MONO = ("Microsoft JhengHei", 10)

# Fixed grid rows for the page — see _build_ui for why this is grid and not pack.
_ROW_HEADER, _ROW_PANES, _ROW_EDIT, _ROW_WRITE, _ROW_ACTIONS = range(5)

# category → (light colour, badge).  Dark counterparts are registered in
# ui.theme.DARK_MAP, so tcol() maps them when the dark theme is active.
_CATEGORY_STYLE = {
    "player":    ("#1565C0", "🗣"),
    "self":      ("#2E7D32", "💬"),
    "other":     ("#00695C", "💬"),
    "plain":     ("#5D4037", "💬"),
    "tag":       ("#6A1B9A", "📌"),
    "overheard": ("#B26A00", "👂"),
    "battle":    ("#C62828", "⚔"),
    "memory":    ("#4527A0", "🏅"),
    "gap":       ("#9E9E9E", "⏳"),
    "note":      ("#5D4037", "📝"),
}


def category_label(cat: str) -> str:
    """Localised name of a line category (literal tr() — never tr(variable))."""
    return {
        "player":    tr("玩家"),
        "self":      tr("本人"),
        "other":     tr("其他角色"),
        "plain":     tr("無ID對話"),
        "tag":       tr("劇情標籤"),
        "overheard": tr("旁聽"),
        "battle":    tr("戰場喊話"),
        "memory":    tr("長期記憶"),
        "gap":       tr("間隔提示"),
        "note":      tr("純文本"),
    }.get(cat, tr("其他"))


def _speaker_text(parsed: dict) -> str:
    """Display speaker for a row, resolving the two player placeholders."""
    name, note = speaker_display(parsed)
    if note == "unidentified":
        return tr("玩家（未表明身分）")
    if note == "introduced":
        return f"{name}{tr('（已自報姓名）')}"
    return name or "—"


class ConversationHistoryPage(ttk.Frame):
    def __init__(
        self,
        parent,
        *,
        on_delete: Callable[[List[int]], None],
        on_sync_menu: Callable[[List[int], tk.Widget], None],
        on_sync_all: Callable[[List[int]], None],
        on_insert: Callable[[str, str, int], None],
        on_edit_line: Callable[[int, str, int], None],
        on_replace_all: Optional[Callable[[List[str], str], None]] = None,
        on_patch_lines: Optional[Callable[[Dict[int, str], str], None]] = None,
        on_view_eavesdroppers: Optional[Callable[[int], None]] = None,
        on_view_sharers: Optional[Callable[[int], None]] = None,
        on_clear_eavesdroppers: Optional[Callable[[List[int]], None]] = None,
        edit_variable: Optional[tk.BooleanVar] = None,
        app=None,
        **kw,
    ):
        super().__init__(parent, **kw)
        self._on_delete = on_delete
        self._on_sync_menu = on_sync_menu
        self._on_sync_all = on_sync_all
        self._on_insert = on_insert
        self._on_edit_line = on_edit_line
        self._on_replace_all = on_replace_all
        self._on_patch_lines = on_patch_lines
        self._on_view_eavesdroppers = on_view_eavesdroppers
        self._on_view_sharers = on_view_sharers
        self._on_clear_eavesdroppers = on_clear_eavesdroppers
        self._eaves_counts: List[int] = []      # per-line eavesdropper counts
        self._share_counts: List[int] = []      # per-line sharer counts
        self._rag_status: str = ""
        self._relations = self._on_view_eavesdroppers is not None
        self._app = app

        self._entries: list = []
        self._npc_name: str = ""
        self._npc_id: str = ""
        self._row_to_index: Dict[str, int] = {}
        self._edit_var = (edit_variable if edit_variable is not None
                          else tk.BooleanVar(value=False))
        self._stats_var = tk.StringVar(value="")
        self._insert_open = False
        self._line_edit_open = False
        self._line_edit_index: Optional[int] = None
        self._ctx_menu = None

        self._build_ui()
        self._edit_var.trace_add("write", lambda *_a: self._refresh_edit_state())

    # ── construction ──────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # grid, not pack.  The bottom panels kept colliding with the expanding
        # panedwindow: pack allocates in *call order*, so re-packing the action
        # row (which happens on every selection change) moved it after whatever
        # panel was open, and a manually dragged sash could squeeze a panel to
        # zero height.  Grid rows are positional — showing and hiding with
        # grid()/grid_remove() cannot reorder anything, whatever the call order.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(_ROW_PANES, weight=1)

        header = ttk.Frame(self)
        header.grid(row=_ROW_HEADER, column=0, sticky="ew", padx=6, pady=(4, 2))
        ttk.Checkbutton(header, text=tr("編輯模式"),
                        variable=self._edit_var).pack(side=tk.LEFT)
        self._rag_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self._rag_var,
                  foreground=tcol("#7A6A4A")).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(header, textvariable=self._stats_var,
                  foreground=tcol("#6B5B3E")).pack(side=tk.RIGHT, padx=8)

        # ── bottom panels (hidden until opened) ───────────────────────────
        self._build_insert_panel()
        self._build_line_edit_panel()

        # ── action row (bottom, hidden until edit mode) ───────────────────
        self._action_bar = ttk.Frame(self)
        self._sync_btn = ttk.Button(self._action_bar, text=tr("🔄 同步 ▾"),
                                    style="warning.TButton")
        self._sync_btn.pack(side=tk.LEFT, padx=2, pady=4)
        self._sync_btn.configure(command=self._show_sync_menu)

        self._compose_btn = ttk.Button(self._action_bar, text=tr("✍ 編寫 ▾"),
                                       style="success.TButton")
        self._compose_btn.pack(side=tk.LEFT, padx=2, pady=4)
        attach_menu(self._compose_btn, self._compose_items, direction="up")

        self._transfer_btn = ttk.Button(self._action_bar, text=tr("📤 導出/導入 ▾"),
                                        style="info.TButton")
        self._transfer_btn.pack(side=tk.LEFT, padx=2, pady=4)
        attach_menu(self._transfer_btn, self._transfer_items, direction="up")

        ttk.Button(self._action_bar, text=tr("🗑 刪除"), command=self._delete_selected,
                   style="danger.TButton").pack(side=tk.LEFT, padx=2, pady=4)
        if self._relations:
            ttk.Separator(self._action_bar, orient="vertical").pack(
                side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
            self._relations_btn = ttk.Button(self._action_bar, text=tr("🔗 關聯 ▾"),
                                             style="secondary.TButton")
            self._relations_btn.pack(side=tk.LEFT, padx=2, pady=4)
            attach_menu(self._relations_btn, self._relations_items, direction="up")
        # Discoverability: the fastest routes (double-click, right-click) are
        # invisible without being told they exist.
        ttk.Label(self._action_bar,
                  text=tr("提示：雙擊清單可編輯該行；在清單上按右鍵可開啟操作選單"),
                  foreground=tcol("#9AA0A6")).pack(side=tk.RIGHT, padx=8)
        self._action_bar.grid(row=_ROW_ACTIONS, column=0, sticky="ew", padx=4)
        self._action_bar.grid_remove()

        # ── list (top) + preview (bottom) ─────────────────────────────────
        self._panes = panes = ttk.Panedwindow(self, orient=tk.VERTICAL)
        panes.grid(row=_ROW_PANES, column=0, sticky="nsew", padx=6, pady=(0, 4))

        top = ttk.Frame(panes)
        # 關聯 only appears when the host wired the relations callbacks.
        cols = (("line", "speaker", "kind", "assoc", "text") if self._relations
                else ("line", "speaker", "kind", "text"))
        # height=6 is the *requested* size, not a cap — both panes expand with
        # their weights.  Keeping the request small is what lets the sash move
        # freely: a pane never shrinks below its children's requested height, so
        # a tall default Treeview would pin the split and _apply_split's target
        # would be silently clamped.
        self._tree = ttk.Treeview(top, columns=cols, show="headings",
                                  selectmode="extended", height=6)
        # Widths sum to ~560 so the list fits its pane on a normal window and
        # the focus ring stays inside it; 內容 then stretches into whatever is
        # left.  Oversized fixed widths pushed the last column past the edge.
        col_specs = [("line", tr("行"), 46, 36, "w"),
                     ("speaker", tr("說話者"), 200, 120, "w"),
                     ("kind", tr("類型"), 130, 96, "w")]
        if self._relations:
            col_specs.append(("assoc", tr("關聯"), 92, 70, "w"))
        # 內容 is the stretch column, so it still fills spare width; the smaller
        # base just lets 說話者／類型 stay wide enough for English.
        col_specs.append(("text", tr("內容"), 150, 96, "w"))
        for c, txt, w, minw, anchor in col_specs:
            self._tree.heading(c, text=txt)
            self._tree.column(c, width=w, minwidth=minw, anchor=anchor,
                              stretch=(c == "text"))
        vsb = ttk.Scrollbar(top, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for cat, (colour, _badge) in _CATEGORY_STYLE.items():
            self._tree.tag_configure(cat, foreground=tcol(colour))
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        self._tree.bind("<Double-Button-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)
        # Ctrl+A selects every row — the reason the old 全選/清除 buttons could go.
        self._tree.bind("<Control-a>", self._select_all_event)
        self._tree.bind("<Control-A>", self._select_all_event)
        enable_drag_select(self._tree)
        panes.add(top, weight=6)

        bottom = ttk.Frame(panes)
        self._detail = tk.Text(bottom, wrap="word", font=_MONO, relief="flat",
                               padx=10, pady=8, cursor="arrow", height=4,
                               state="disabled")
        dsb = ttk.Scrollbar(bottom, orient="vertical", command=self._detail.yview)
        self._detail.configure(yscrollcommand=dsb.set)
        dsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._detail.tag_configure("key", font=("Microsoft JhengHei", 10, "bold"),
                                   foreground=tcol("#6B5B3E"))
        self._detail.tag_configure("empty", font=("Microsoft JhengHei", 10, "italic"),
                                   foreground=tcol("#999999"))
        self._detail.tag_configure("eaves", font=("Microsoft JhengHei", 10, "bold"),
                                   foreground=tcol("#B26A00"))
        for cat, (colour, _badge) in _CATEGORY_STYLE.items():
            self._detail.tag_configure(f"body_{cat}", foreground=tcol(colour),
                                       lmargin1=4, lmargin2=4)
        # Registered after the tags exist so their sizes scale together.
        preview_font.register(self._detail)
        panes.add(bottom, weight=4)

        self._refresh_edit_state()

    @staticmethod
    def _panel_title_row(panel, title: str, on_close) -> None:
        """Title + ✕ close button along the top of a bottom panel."""
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, padx=8, pady=(6, 0))
        ttk.Label(row, text=title, font=("Microsoft JhengHei", 10, "bold"),
                  foreground=tcol("#1A3A5C")).pack(side=tk.LEFT)
        ttk.Button(row, text="✕", width=3, command=on_close,   # icon only
                   style="secondary.TButton").pack(side=tk.RIGHT)

    @staticmethod
    def _panel_text_with_button(panel, *, height: int, label: str, command):
        """Text area with the confirm button parked at its bottom-right.

        The button lives in a narrow column beside the box rather than on its
        own row, so it costs a little width instead of a whole row of height —
        this panel shares the window with the list and the preview.
        """
        wrap = ttk.Frame(panel)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        side = ttk.Frame(wrap)
        side.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        ttk.Button(side, text=label, command=command,
                   style="warning.TButton").pack(side=tk.BOTTOM)

        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL)
        txt = tk.Text(wrap, height=height, wrap="word", yscrollcommand=vsb.set)
        vsb.configure(command=txt.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return txt

    def _build_insert_panel(self) -> None:
        """寫入對話行 panel — the single-line writer, opened from 編寫 ▾."""
        self._insert_panel = ttk.Frame(self, relief="groove", borderwidth=1)
        self._panel_title_row(self._insert_panel, tr("✍ 寫入對話行"),
                              self._toggle_insert_panel)

        speaker_row = ttk.Frame(self._insert_panel)
        speaker_row.pack(fill=tk.X, padx=8, pady=(6, 2))
        ttk.Label(speaker_row, text=tr("說話者:")).pack(side=tk.LEFT, anchor="n")
        self._speaker = SpeakerField(
            speaker_row, self._app,
            get_self=self._self_identity, get_day=self._current_day)
        self._speaker.pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)

        pos_row = ttk.Frame(self._insert_panel)
        pos_row.pack(fill=tk.X, padx=8, pady=(2, 4))
        ttk.Label(pos_row, text=tr("插入為第")).pack(side=tk.LEFT)
        self._pos_var = tk.StringVar(value="1")
        self._pos_spinbox = ttk.Spinbox(pos_row, from_=1, to=1,
                                        textvariable=self._pos_var, width=6)
        self._pos_spinbox.pack(side=tk.LEFT, padx=(4, 4))
        self._pos_hint = ttk.Label(pos_row, text=tr("行"), foreground=tcol("#6B5B3E"))
        self._pos_hint.pack(side=tk.LEFT)

        self._insert_text = self._panel_text_with_button(
            self._insert_panel, height=8, label=tr("寫入"),
            command=self._on_insert_confirm)
        self._insert_panel.grid(row=_ROW_WRITE, column=0, sticky="ew", padx=4)
        self._insert_panel.grid_remove()

    def _build_line_edit_panel(self) -> None:
        """快速編輯 — the former modal dialog, now a bottom panel.

        Editing one line is a small, frequent operation; a grab_set modal for it
        meant losing the list, the preview and your place in them every time.

        Laid out like 快速寫入 so the two feel like one tool: speaker on its own
        row, then the content, and where 快速寫入 has 插入位置 this has 變更行數
        — the same control doing the equivalent job (move the line).

        The speaker row holds the line's *whole* prefix verbatim, not a parsed
        name: prefixes are not all "someone speaking" (旁聽 carries the day and
        distance, 戰場喊話 the engagement, MEMORY the day), and re-synthesising
        them from parts would corrupt formats the mod has to read back.
        Round-tripping the prefix unchanged is exact for every line type.
        """
        self._line_edit_panel = ttk.Frame(self, relief="groove", borderwidth=1)
        self._line_edit_title = tk.StringVar(value="")
        row = ttk.Frame(self._line_edit_panel)
        row.pack(fill=tk.X, padx=8, pady=(6, 0))
        ttk.Label(row, textvariable=self._line_edit_title,
                  font=("Microsoft JhengHei", 10, "bold"),
                  foreground=tcol("#1A3A5C")).pack(side=tk.LEFT)
        ttk.Button(row, text="✕", width=3, command=self._close_line_edit,  # icon only
                   style="secondary.TButton").pack(side=tk.RIGHT)

        sp_row = ttk.Frame(self._line_edit_panel)
        sp_row.pack(fill=tk.X, padx=8, pady=(6, 2))
        ttk.Label(sp_row, text=tr("說話者:")).pack(side=tk.LEFT, anchor="n")
        self._le_speaker = SpeakerField(
            sp_row, self._app,
            get_self=self._self_identity, get_day=self._current_day)
        self._le_speaker.pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)

        pos_row = ttk.Frame(self._line_edit_panel)
        pos_row.pack(fill=tk.X, padx=8, pady=(2, 4))
        ttk.Label(pos_row, text=tr("變更為第")).pack(side=tk.LEFT)
        self._le_pos_var = tk.StringVar(value="1")
        self._le_pos_spin = ttk.Spinbox(pos_row, from_=1, to=1,
                                        textvariable=self._le_pos_var, width=6)
        self._le_pos_spin.pack(side=tk.LEFT, padx=(4, 4))
        self._le_pos_hint = ttk.Label(pos_row, text="", foreground=tcol("#6B5B3E"))
        self._le_pos_hint.pack(side=tk.LEFT)

        self._line_edit_text = self._panel_text_with_button(
            self._line_edit_panel, height=7, label=tr("儲存"),
            command=self._on_line_edit_confirm)
        self._line_edit_panel.grid(row=_ROW_EDIT, column=0, sticky="ew", padx=4)
        self._line_edit_panel.grid_remove()

    # ── menus ─────────────────────────────────────────────────────────────
    def _compose_items(self):
        # The bulk multi-line editor on top; the two single-line tools — now
        # full editors in their own right, not just "quick" shortcuts — below.
        n = len(self.selected_indices())
        return [
            (tr("📝 編寫 {n} 個對話行").format(n=n), self._compose_selected),
            None,
            (tr("✏ 編寫對話行"), self._edit_focused_line),
            (tr("✍ 寫入對話行"), self._toggle_insert_panel),
        ]

    # ── 編寫 N 個對話行 ────────────────────────────────────────────────────
    def _compose_selected(self) -> None:
        if self._on_replace_all is None or self._app is None:
            return
        from dialogs.conversation_compose_dialog import open_compose_dialog
        open_compose_dialog(
            self._app, self._entries, npc_name=self._npc_name, npc_id=self._npc_id,
            indices=self.selected_indices(), on_commit=self._on_replace_all)

    def _transfer_items(self):
        n = len(self.selected_indices())
        return [
            (tr("📄 導出全部為 MD"), self._export_md),
            (tr("📋 導出全部到剪貼簿"), self._clip_export_all),
            (tr("📋 導出 {n} 行到剪貼簿").format(n=n), self._clip_export_selected),
            None,
            (tr("📥 從 MD 導入"), self._import_md),
            (tr("📥 從剪貼簿導入"), self._import_clipboard),
        ]

    # ── 導出/導入 ─────────────────────────────────────────────────────────
    def _md_row_label(self, index: int, _text: str) -> str:
        """Readable part of a Markdown heading: badge · category · speaker."""
        p = parse_conversation_line(self._entries[index])
        cat = line_category(p, self._npc_name, self._npc_id)
        badge = _CATEGORY_STYLE.get(cat, ("", ""))[1]
        return f"{badge} {category_label(cat)} · {_speaker_text(p)}".strip()

    def _export_md(self) -> None:
        if not self._require_entries(tr("導出為 MD")):
            return
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(), defaultextension=".md",
            initialfile=tr("{name}_對話記錄").format(name=self._npc_name or "npc"),
            filetypes=[("Markdown", "*.md")],
        )
        if not path:
            return
        text = CT.build_markdown(
            self._npc_name, self._entries,
            header=tr("{name} 的對話記錄").format(name=self._npc_name or "—"),
            note=tr("每個 `## [行號]` 區塊是一行對話，`~~~` 圍欄內是原文。"
                    "導入時整份取代對話歷史，並依區塊順序重新編號——"
                    "刪除整個區塊即刪除該行，不必手動改行號。"),
            row_label=self._md_row_label,
        )
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(tr("導出為 MD"), str(exc))
            return
        messagebox.showinfo(
            tr("導出為 MD"),
            tr("已導出 {n} 行對話至：\n{path}").format(n=len(self._entries), path=path))

    def _clip_export_all(self) -> None:
        if not self._require_entries(tr("導出到剪貼簿")):
            return
        self._to_clipboard(CT.build_clipboard_all(self._entries))
        messagebox.showinfo(
            tr("導出到剪貼簿"),
            tr("已複製 {n} 行（JSON 片段）。").format(n=len(self._entries)))

    def _clip_export_selected(self) -> None:
        idx = self.selected_indices()
        if not idx:
            messagebox.showwarning(tr("導出到剪貼簿"), tr("請先在清單中選取對話行"))
            return
        self._to_clipboard(CT.build_clipboard_selected(self._entries, idx))
        messagebox.showinfo(
            tr("導出到剪貼簿"),
            tr("已複製 {n} 行，每行以 [#行號] 開頭。\n"
               "修改內容後再從剪貼簿導入，即可只覆蓋這些行——"
               "請保留行號標記。").format(n=len(idx)))

    def _import_md(self) -> None:
        if self._on_replace_all is None:
            return
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            filetypes=[("Markdown", "*.md"), (tr("所有檔案"), "*.*")])
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(tr("從 MD 導入"), str(exc))
            return
        try:
            entries = CT.parse_markdown(text)
        except CT.TransferError as exc:
            messagebox.showwarning(tr("從 MD 導入"), self._transfer_error_text(exc))
            return
        if not self._confirm_replace(tr("從 MD 導入"), len(entries)):
            return
        self._on_replace_all(entries, tr("從 MD 導入"))

    def _import_clipboard(self) -> None:
        if self._on_replace_all is None or self._on_patch_lines is None:
            return
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        try:
            res = CT.parse_clipboard(text, len(self._entries))
        except CT.TransferError as exc:
            messagebox.showwarning(tr("從剪貼簿導入"), self._transfer_error_text(exc))
            return
        if res.kind == "patch":
            n = len(res.updates)
            if not messagebox.askyesno(
                tr("從剪貼簿導入"),
                tr("將覆蓋 {n} 行對話（其餘行不變）。\n"
                   "（暫存，按右上「儲存」後才寫入檔案）").format(n=n)):
                return
            self._on_patch_lines(res.updates, tr("從剪貼簿導入"))
            return
        if not self._confirm_replace(tr("從剪貼簿導入"), len(res.entries)):
            return
        self._on_replace_all(res.entries, tr("從剪貼簿導入"))

    def _require_entries(self, title: str) -> bool:
        if not self._entries:
            messagebox.showinfo(title, tr("對話記錄為空"))
            return False
        return True

    def _to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def _confirm_replace(self, title: str, new_len: int) -> bool:
        return bool(messagebox.askyesno(
            title,
            tr("這會整份取代對話歷史：\n\n原 {old} 行 → 新 {new} 行\n\n"
               "（暫存，按右上「儲存」後才寫入檔案）").format(
                   old=len(self._entries), new=new_len)))

    @staticmethod
    def _transfer_error_text(exc) -> str:
        """Literal tr() per failure code — never tr(variable)."""
        code = str(exc)
        if code.startswith("out-of-range:"):
            return tr("有行號超出目前的對話行數（{nums}），沒有任何內容被修改。\n"
                      "請確認是從這個角色導出的內容。").format(
                          nums=code.split(":", 1)[1])
        return {
            "empty": tr("內容是空的。"),
            "no-headings": tr("找不到 `## [行號]` 標題，這不像是本工具導出的 MD。"),
            "unclosed-fence": tr("有一個 `~~~` 圍欄沒有關閉。"),
            "missing-fence": tr("某個 `## [行號]` 區塊裡沒有 `~~~` 圍欄。"),
            "json-without-key": tr("這段 JSON 裡沒有 ConversationHistory 欄位。"),
            "bad-fragment": tr("ConversationHistory 片段的 JSON 格式有誤。"),
            "not-a-list": tr("ConversationHistory 必須是一個陣列。"),
        }.get(code, tr("無法辨識剪貼簿的內容格式。支援：角色 JSON、"
                       "ConversationHistory 片段、JSON 陣列，或以 [#行號] 開頭的文字。"))

    # ── data ──────────────────────────────────────────────────────────────
    def load(self, entries: list, npc_name: str = "", npc_id: str = "",
             rag_status: str = "") -> None:
        self._entries = entries if isinstance(entries, list) else []
        self._npc_name = npc_name or ""
        self._npc_id = npc_id or ""
        # Relation counts arrive asynchronously via set_relation_counts (a
        # campaign-wide scan the app runs off the reload path); clear on load.
        self._eaves_counts = []
        self._share_counts = []
        self._rag_status = rag_status or ""
        self._rag_var.set(self._rag_label(self._rag_status))
        if self._insert_open:
            self._toggle_insert_panel()
        if self._line_edit_open:
            self._close_line_edit()
        changed = npc_name != getattr(self, "_loaded_npc", None)
        self._loaded_npc = npc_name
        self._refresh_list(reset_scroll=changed)
        self._refresh_insert_controls()

    def set_relation_counts(self, eaves_counts, share_counts) -> None:
        """Fill in the 旁聽／共用 badges once the app has scanned the campaign."""
        self._eaves_counts = list(eaves_counts) if isinstance(eaves_counts, list) else []
        self._share_counts = list(share_counts) if isinstance(share_counts, list) else []
        if not self._relations:
            return
        for iid, i in self._row_to_index.items():
            if self._tree.exists(iid):
                self._tree.set(iid, "assoc", self._assoc_cell(i))
        sel = self._tree.selection()
        if sel:
            self._render_detail(self._row_to_index.get(sel[0]))

    @staticmethod
    def _rag_label(status: str) -> str:
        """Literal tr() per status key — never tr(variable)."""
        return {
            "indexed": tr("RAG 索引：已建立"),
            "stale":   tr("RAG 索引：待重建"),
            "none":    "",
        }.get(status, "")

    @staticmethod
    def _count_at(counts, index: int) -> int:
        if 0 <= index < len(counts):
            try:
                return int(counts[index])
            except (TypeError, ValueError):
                return 0
        return 0

    def _eaves_count(self, index: int) -> int:
        return self._count_at(self._eaves_counts, index)

    def _share_count(self, index: int) -> int:
        return self._count_at(self._share_counts, index)

    def _assoc_cell(self, index: int) -> str:
        """The 關聯 column text: 👂 = 旁聽, 🔗 = 共用 (only non-zero shown)."""
        parts = []
        n_e = self._eaves_count(index)
        if n_e:
            parts.append(f"👂{n_e}")
        n_s = self._share_count(index)
        if n_s:
            parts.append(f"🔗{n_s}")
        return "  ".join(parts)

    def clear(self) -> None:
        self._entries = []
        self._eaves_counts = []
        self._share_counts = []
        self._tree.delete(*self._tree.get_children())
        self._row_to_index = {}
        self._render_detail(None)
        self._stats_var.set("")

    # ── list ──────────────────────────────────────────────────────────────
    def _refresh_list(self, reset_scroll: bool = False) -> None:
        prev = set(self._tree.selection())
        top = self._tree.yview()[0]
        self._tree.delete(*self._tree.get_children())
        self._row_to_index = {}
        last_iid = ""
        for i, entry in enumerate(self._entries):
            p = parse_conversation_line(entry)
            cat = line_category(p, self._npc_name, self._npc_id)
            badge = _CATEGORY_STYLE.get(cat, ("", ""))[1]
            text = p.get("text")
            if text is None:
                text = (entry if isinstance(entry, str)
                        else json.dumps(entry, ensure_ascii=False))
            iid = f"ch::{i}"
            kind_cell = f"{badge} {category_label(cat)}".strip()
            body = str(text).replace("\n", " ")[:200]
            if self._relations:
                values = (i + 1, _speaker_text(p), kind_cell,
                          self._assoc_cell(i), body)
            else:
                values = (i + 1, _speaker_text(p), kind_cell, body)
            self._tree.insert("", "end", iid=iid, values=values, tags=(cat,))
            self._row_to_index[iid] = i
            last_iid = iid
        if reset_scroll and last_iid:
            self._tree.see(last_iid)
        else:
            self._tree.yview_moveto(top)
        keep = [i for i in prev if self._tree.exists(i)]
        if keep:
            self._tree.selection_set(keep)
        else:
            self._render_detail(None)
        self._update_stats()
        self._refresh_edit_state()

    def _select_all_event(self, _event=None):
        self._tree.selection_set(self._tree.get_children())
        return "break"

    def selected_indices(self) -> List[int]:
        """Underlying ConversationHistory indices of the selected rows, in order."""
        return sorted(self._row_to_index[i] for i in self._tree.selection()
                      if i in self._row_to_index)

    def _on_select(self) -> None:
        sel = self._tree.selection()
        idx = self._row_to_index.get(sel[0]) if sel else None
        self._render_detail(idx)
        self._update_stats()
        self._refresh_edit_state()

    def _on_double_click(self, _event=None):
        if not self._edit_var.get():
            return None
        self._edit_focused_line()
        return "break"

    def _on_right_click(self, event):
        """Context menu on a row (selects it first if it isn't already)."""
        if not self._edit_var.get():
            return None
        iid = self._tree.identify_row(event.y)
        if iid:
            if iid not in self._tree.selection():
                self._tree.selection_set(iid)
            # Point "this line" actions at the row actually right-clicked, not
            # wherever the last left-click left the focus — otherwise 在此插入／
            # 編寫此對話行 targeted the wrong line.  Focus stays inside the
            # current selection when right-clicking within a multi-selection.
            self._tree.focus(iid)
        picks = self.selected_indices()
        if not picks:
            return "break"
        # One row → act on that row.  Several → act on the selection, with the
        # count in the labels.  No separators: three items don't need grouping.
        if len(picks) == 1:
            items = [
                (tr("🔄 同步至已選角色"), self._sync_all_selected),
                (tr("➕ 在此插入對話行"), self._insert_at_focused),
                (tr("✏ 編寫此對話行"), self._edit_focused_line),
                (tr("🗑 刪除此對話行"), self._delete_focused_line, "danger"),
            ]
            if self._on_clear_eavesdroppers is not None:
                items.append((tr("🧹 清空此對話行旁聽者"),
                              self._clear_focused_eavesdroppers, "danger"))
        else:
            n = len(picks)
            items = [
                (tr("🔄 同步至已選角色"), self._sync_all_selected),
                (tr("📝 編寫 {n} 個對話行").format(n=n), self._compose_selected),
                (tr("🗑 刪除 {n} 個對話行").format(n=n), self._delete_selected, "danger"),
            ]
            if self._on_clear_eavesdroppers is not None:
                items.append((tr("🧹 清空 {n} 個對話行旁聽者").format(n=n),
                              self._clear_focused_eavesdroppers, "danger"))
        self._ctx_menu = PopoverMenu(self._tree, items,
                                     at=(event.x_root, event.y_root))
        self._ctx_menu.show()
        return "break"

    def _focused_index(self) -> Optional[int]:
        """The row the pointer/keyboard is on — the target of "this line" actions."""
        picks = self.selected_indices()
        if not picks:
            return None
        cur = self._tree.focus()
        if cur in self._row_to_index:
            return self._row_to_index[cur]
        return picks[0]

    def _render_detail(self, index: Optional[int]) -> None:
        t = self._detail
        t.configure(state="normal")
        t.delete("1.0", "end")
        if index is None or index >= len(self._entries):
            t.insert("end", tr("（選擇一行以檢視完整內容）"), "empty")
            t.configure(state="disabled")
            return
        entry = self._entries[index]
        p = parse_conversation_line(entry)
        cat = line_category(p, self._npc_name, self._npc_id)
        badge = _CATEGORY_STYLE.get(cat, ("", ""))[1]

        t.insert("end", f"[{index + 1}] ", "key")
        t.insert("end", f"{badge} {category_label(cat)}", f"body_{cat}")
        speaker = _speaker_text(p)
        if speaker and speaker != "—":
            t.insert("end", "　" + tr("說話者") + "：", "key")
            t.insert("end", speaker)
        if p.get("speaker_id"):
            t.insert("end", f"　｜ {p['speaker_id']}", "empty")
        if p.get("day") is not None:
            t.insert("end", "　" + tr("戰役日") + f"：{int(p['day'])}", "key")
        if p.get("distance") is not None:
            t.insert("end", f"　{p['distance']:g}m", "key")
        if p.get("context"):
            t.insert("end", "　" + tr("戰況") + f"：{p['context']}", "key")
        n_eaves = self._eaves_count(index)
        if n_eaves:
            t.insert("end", f"　👂 {tr('{n} 位旁聽').format(n=n_eaves)}", "eaves")
        n_share = self._share_count(index)
        if n_share:
            t.insert("end", f"　🔗 {tr('{n} 位共用').format(n=n_share)}", "eaves")
        t.insert("end", "\n\n")

        text = p.get("text")
        if text is None:
            text = (entry if isinstance(entry, str)
                    else json.dumps(entry, ensure_ascii=False, indent=2))
        t.insert("end", str(text), f"body_{cat}")
        t.configure(state="disabled")

    def _update_stats(self) -> None:
        total = len(self._entries)
        picked = len(self._tree.selection())
        base = f"{tr('對話行')} {total}"
        if picked:
            base += f"　｜　{tr('已選取')} {picked}"
        self._stats_var.set(base)

    # ── edit gating ───────────────────────────────────────────────────────
    def _refresh_edit_state(self) -> None:
        editing = bool(self._edit_var.get())
        try:
            if editing:
                self._action_bar.grid()
            else:
                self._action_bar.grid_remove()
                if self._insert_open:
                    self._toggle_insert_panel()
                if self._line_edit_open:
                    self._close_line_edit()
        except tk.TclError:
            pass

    # ── actions ───────────────────────────────────────────────────────────
    def _require_selection(self, title: str) -> List[int]:
        picks = self.selected_indices()
        if not picks:
            messagebox.showwarning(title, tr("請先在上方清單選取對話行（可按住 Ctrl／Shift 複選，Ctrl+A 全選）"))
        return picks

    def _delete_selected(self) -> None:
        picks = self._require_selection(tr("刪除"))
        if picks:
            self._on_delete(picks)

    def _delete_focused_line(self) -> None:
        i = self._focused_index()
        if i is not None:
            self._on_delete([i])

    # ── 關聯（對話輻射：旁聽＋共用）───────────────────────────────────────
    def _relations_items(self):
        """The 關聯 ▾ menu.  View actions are single-line; 清空 supports multi."""
        n = len(self.selected_indices())
        clear_label = (tr("🧹 清空旁聽者") if n <= 1
                       else tr("🧹 清空 {n} 行旁聽者").format(n=n))
        return [
            (tr("👥 查看共用者"), self._view_selected_sharers),
            (tr("👂 查看旁聽者"), self._view_selected_eavesdroppers),
            None,
            (clear_label, self._clear_selected_eavesdroppers, "danger"),
        ]

    def _require_single(self, title: str):
        picks = self.selected_indices()
        if len(picks) != 1:
            messagebox.showinfo(title, tr("請只選取一行對話。"))
            return None
        return picks[0]

    def _view_selected_eavesdroppers(self) -> None:
        i = self._require_single(tr("旁聽者"))
        if i is not None and self._on_view_eavesdroppers is not None:
            self._on_view_eavesdroppers(i)

    def _view_selected_sharers(self) -> None:
        i = self._require_single(tr("共用者"))
        if i is not None and self._on_view_sharers is not None:
            self._on_view_sharers(i)

    def _clear_selected_eavesdroppers(self) -> None:
        if self._on_clear_eavesdroppers is None:
            return
        picks = self.selected_indices()
        if not picks:
            messagebox.showinfo(tr("清空旁聽者"), tr("請先在清單中選取對話行。"))
            return
        self._on_clear_eavesdroppers(picks)

    def _clear_focused_eavesdroppers(self) -> None:
        """右鍵〔清空此對話行旁聽者〕— clears the focused/selected line(s)."""
        if self._on_clear_eavesdroppers is None:
            return
        picks = self.selected_indices() or (
            [self._focused_index()] if self._focused_index() is not None else [])
        if picks:
            self._on_clear_eavesdroppers(picks)

    def _show_sync_menu(self) -> None:
        picks = self._require_selection(tr("同步"))
        if picks:
            self._on_sync_menu(picks, self._sync_btn)

    def _sync_all_selected(self) -> None:
        """Sync straight to every character ticked in the left-hand list.

        Not the 同步 ▾ menu — that is the "which targets?" chooser; this is the
        menu's first entry (所有已選角色) invoked directly.
        """
        picks = self.selected_indices()
        if picks:
            self._on_sync_all(picks)

    # ── 編輯此對話行 ─────────────────────────────────────────────────────
    def _edit_focused_line(self) -> None:
        i = self._focused_index()
        if i is None or i >= len(self._entries):
            messagebox.showwarning(tr("編輯"), tr("請先在上方清單選取一行對話"))
            return
        if self._insert_open:
            self._toggle_insert_panel()
        entry = self._entries[i]
        raw = entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)
        prefix, content = split_line_prefix(entry)
        self._line_edit_index = i
        self._line_edit_title.set(tr("✏ 編寫第 {n} 行對話").format(n=i + 1))
        self._le_speaker.set_prefix(prefix)
        total = len(self._entries)
        self._le_pos_spin.configure(from_=1, to=max(1, total))
        self._le_pos_var.set(str(i + 1))
        self._le_pos_hint.configure(
            text=tr("行（共 {total} 行；改變數字即移動此行）").format(total=total))
        self._line_edit_text.delete("1.0", tk.END)
        self._line_edit_text.insert("1.0", content if prefix else raw)
        if not self._line_edit_open:
            self._line_edit_panel.grid()
            self._line_edit_open = True
            self._apply_split()
        self._line_edit_text.focus_set()

    def _close_line_edit(self) -> None:
        if not self._line_edit_open:
            return
        self._line_edit_panel.grid_remove()
        self._line_edit_open = False
        self._line_edit_index = None
        self._line_edit_text.delete("1.0", tk.END)
        self._apply_split()

    def _on_line_edit_confirm(self) -> None:
        i = self._line_edit_index
        if i is None:
            return
        content = self._line_edit_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning(tr("編輯"), tr("內容不能為空"))
            return
        prefix = self._le_speaker.get_prefix()
        # compose() also applies the wrapper's text convention (battle shouts
        # are always stored quoted).
        new_line = SF.compose(SF.parse(prefix) if prefix else None, content)
        try:
            position = int(self._le_pos_var.get())
        except ValueError:
            position = i + 1
        position = max(1, min(position, max(1, len(self._entries))))
        self._close_line_edit()
        self._on_edit_line(i, new_line, position)

    # ── 快速寫入 ──────────────────────────────────────────────────────────
    def _refresh_insert_controls(self) -> None:
        total = len(self._entries)
        max_pos = max(1, total + 1)
        self._pos_spinbox.configure(from_=1, to=max_pos)
        self._pos_var.set(str(max_pos))
        self._pos_hint.configure(
            text=tr("行（共 {total} 行，{last} = 末尾）").format(total=total, last=max_pos))

    def _toggle_insert_panel(self) -> None:
        if self._insert_open:
            self._insert_panel.grid_remove()
            self._insert_open = False
            self._insert_text.delete("1.0", tk.END)
        else:
            if self._line_edit_open:
                self._close_line_edit()
            self._insert_panel.grid()
            self._insert_open = True
            self._insert_text.focus_set()
        self._apply_split()

    def _insert_at_focused(self) -> None:
        """右鍵〔在此插入對話行〕— open 寫入對話行 aimed at the picked line.

        Same panel as 寫入對話行, but the position is pre-filled with the
        right-clicked row so the new line lands *there* and pushes it down,
        rather than defaulting to the end.
        """
        i = self._focused_index()
        if i is None or i >= len(self._entries):
            messagebox.showwarning(tr("寫入對話行"), tr("請先在上方清單選取一行對話"))
            return
        if not self._insert_open:
            self._toggle_insert_panel()
        self._speaker.set_prefix("")           # a fresh line, not a copy of this one
        self._insert_text.delete("1.0", tk.END)
        self._pos_var.set(str(i + 1))
        self._insert_text.focus_set()

    # ── list / preview split ──────────────────────────────────────────────
    def _apply_split(self) -> None:
        """Give the preview more room while a bottom panel is open.

        With a panel open the window is doing three jobs at once; the list is
        the one that can spare the space, since you have already picked the row
        you are working on.

        Done by re-weighting the panes rather than calling ``sashpos``: an
        explicit sash position is clamped against the panes' current minimum
        sizes and races the relayout the panel itself triggers, so it landed
        wherever it liked.  Weights are declarative and survive later resizes.
        """
        top_w, bottom_w = ((3, 5) if (self._insert_open or self._line_edit_open)
                           else (6, 4))

        def _place():
            try:
                if not self._panes.winfo_exists():
                    return
                kids = self._panes.panes()
                if len(kids) < 2:
                    return
                self._panes.pane(kids[0], weight=top_w)
                self._panes.pane(kids[1], weight=bottom_w)
            except tk.TclError:
                pass
        self.after_idle(_place)

    def _self_identity(self):
        """(name, id) of the character being edited — what 「自己（I）」 fills in."""
        return (self._npc_name, self._npc_id)

    def _current_day(self) -> float:
        """The campaign day date pickers should default to.

        The game's own last-known day (from the exported world snapshot) is the
        honest "now"; the newest day mentioned in this character's history is the
        fallback for campaigns whose database has not been exported yet.
        """
        try:
            day = float(svc_terminology.campaign_day_now(
                getattr(self._app, "campaign_dir", None)))
            if day:
                return day
        except Exception:
            pass
        best = 0.0
        for entry in self._entries:
            day = parse_conversation_line(entry).get("day")
            if day is not None:
                best = max(best, float(day))
        return best

    def _speaker_prefix(self) -> str:
        return self._speaker.get_prefix()

    def _on_insert_confirm(self) -> None:
        speaker = self._speaker_prefix()      # empty is allowed → plain text
        text = self._insert_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning(tr("寫入"), tr("請輸入對話內容"))
            return
        try:
            position = int(self._pos_var.get())
        except ValueError:
            position = len(self._entries) + 1
        position = max(1, min(position, len(self._entries) + 1))
        self._insert_panel.grid_remove()
        self._insert_open = False
        self._insert_text.delete("1.0", tk.END)
        self._on_insert(speaker, text, position)
