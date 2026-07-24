"""記憶之書 — the character JSON ``Memories[]`` entries the in-game Memory Book shows.

Two-row list (date / title) plus a rich preview styled like the 摘要 tab, with the
Player2 illustration and the 6.0 ``scene`` description.

The old **AI 記憶** track (the ``MEMORY (day N): …`` lines inside
ConversationHistory) was removed in v1.1.0: AI Influence 6.0 replaced memory
consolidation with retrieval, so those lines are just ordinary history the RAG
index may surface — editing them as a separate "memory" concept only confused
people.  ``memory_service.parse_memory_lines`` is still used elsewhere to
recognise legacy lines in old saves.

Editing goes through modal dialogs and persists via app callbacks (immediate
write + reload).  Read-only unless the page's own 編輯模式 toggle is on.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from pathlib import Path
from typing import Any, Callable, List, Optional

from i18n import tr
from services import memory_service as M
from services.terminology_service import campaign_day_now
from services.time_format import CAMPAIGN_START_DAY, format_game_time
from widgets.game_date_field import GameDateField
from widgets.image_view import ImageThumbnail
from widgets.image_picker import open_image_picker, PICKER_REMOVE
from widgets.window_center import center_window
from ui import preview_font
from ui.theme import tcol

_MONO = ("Microsoft JhengHei", 10)


class MemoryPage(ttk.Frame):
    def __init__(
        self,
        parent,
        *,
        on_entry_save: Callable[[Optional[int], dict], None],
        on_entry_delete: Callable[[int], None],
        edit_variable: Optional[tk.BooleanVar] = None,
        resolve_name: Optional[Callable[[str], Optional[str]]] = None,
        **kw,
    ):
        super().__init__(parent, **kw)
        self._on_entry_save = on_entry_save
        self._on_entry_delete = on_entry_delete
        self._resolve_name = resolve_name
        self._edit_var = edit_variable if edit_variable is not None else tk.BooleanVar(value=False)

        self._entries: List[dict] = []        # Memories[]
        self._campaign_dir: Optional[Path] = None
        self._npc_name: str = ""

        # two-row book list bookkeeping
        self._book_pos_to_entry: List[int] = []
        self._book_first_pos: dict = {}
        self._book_selecting = False

        self._build_ui()
        self._edit_var.trace_add("write", lambda *_: self._refresh_edit_state())

    # ── construction ──────────────────────────────────────────────────
    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=6, pady=(4, 0))
        ttk.Checkbutton(header, text=tr("編輯模式"), variable=self._edit_var).pack(side=tk.LEFT)
        ttk.Label(header, text=tr("　遊戲「記憶之書」顯示的條目"),
                  foreground=tcol("#8A7A5A")).pack(side=tk.LEFT)

        self._build_book_tab(self)
        self._refresh_edit_state()

    def _build_book_tab(self, parent) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, padx=6, pady=(6, 2))
        self._entry_add = ttk.Button(bar, text=tr("＋ 新增條目"), style="success.TButton",
                                     command=self._add_entry)
        self._entry_add.pack(side=tk.LEFT, padx=2)
        ttk.Label(bar, text=tr("選取條目："), foreground=tcol("#5A5A5A")).pack(side=tk.LEFT, padx=(10, 2))
        self._entry_edit = ttk.Button(bar, text=tr("✏ 編輯"), style="info.TButton",
                                      command=self._edit_entry)
        self._entry_edit.pack(side=tk.LEFT, padx=2)
        self._entry_del = ttk.Button(bar, text=tr("🗑 刪除"), style="danger.TButton",
                                     command=self._delete_entry)
        self._entry_del.pack(side=tk.LEFT, padx=2)

        body = ttk.Frame(parent)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        body.columnconfigure(0, weight=3, uniform="mbk")
        body.columnconfigure(1, weight=7, uniform="mbk")
        body.rowconfigure(0, weight=1)
        bf = ttk.Frame(body)
        bf.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._entry_lb = tk.Listbox(bf, exportselection=False, font=_MONO)
        bsb = ttk.Scrollbar(bf, orient="vertical", command=self._entry_lb.yview)
        self._entry_lb.configure(yscrollcommand=bsb.set)
        bsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._entry_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._entry_lb.bind("<<ListboxSelect>>", lambda e: self._on_entry_select())
        self._entry_lb.bind("<Double-Button-1>", lambda e: self._edit_entry())

        detail = ttk.Frame(body)
        detail.grid(row=0, column=1, sticky="nsew")
        self._thumb = ImageThumbnail(detail, thumb_size=(320, 180))
        self._thumb.pack(fill=tk.X, pady=(0, 4))
        self._entry_detail = self._make_preview(detail, pack=True)

    def _make_preview(self, parent, pack: bool = False) -> tk.Text:
        """A read-only rich Text preview styled like the 摘要 tab."""
        t = tk.Text(parent, wrap="word", state="disabled", font=_MONO,
                    relief="flat", padx=8, pady=6, spacing1=2, spacing3=2, cursor="arrow")
        t.tag_configure("title", font=("Microsoft JhengHei", 14, "bold"),
                        foreground=tcol("#1A3A5C"), spacing3=4)
        t.tag_configure("idline", font=("Microsoft JhengHei", 9), foreground=tcol("#9A9A9A"))
        t.tag_configure("key", font=("Microsoft JhengHei", 10, "bold"), foreground=tcol("#6B5B3E"))
        t.tag_configure("section", font=("Microsoft JhengHei", 11, "bold"),
                        foreground=tcol("#2471A3"), spacing1=10, spacing3=4)
        t.tag_configure("body", font=_MONO, foreground=tcol("#222222"), lmargin1=12, lmargin2=12)
        t.tag_configure("empty", font=("Microsoft JhengHei", 10, "italic"), foreground=tcol("#999999"))
        preview_font.register(t)
        if pack:
            t.pack(fill=tk.BOTH, expand=True)
        return t

    # ── public API ────────────────────────────────────────────────────
    def load(self, data: dict, campaign_dir=None, npc_name: str = "") -> None:
        self._campaign_dir = Path(campaign_dir) if campaign_dir else None
        self._npc_name = npc_name or ""
        self._entries = M.memory_entries(data)
        self._refresh_entry_list()
        self._refresh_edit_state()

    def clear(self) -> None:
        self._entries = []
        self._campaign_dir = None
        self._entry_lb.delete(0, tk.END)
        self._book_pos_to_entry = []
        self._book_first_pos = {}
        self._set_text(self._entry_detail, "")
        self._thumb.clear()

    # ── memory-book list (two rows per entry) ─────────────────────────
    def _refresh_entry_list(self) -> None:
        prev = self._book_selected_index()
        top = self._entry_lb.yview()[0]
        self._entry_lb.delete(0, tk.END)
        self._book_pos_to_entry = []
        self._book_first_pos = {}
        for i, e in enumerate(self._entries):
            self._book_first_pos[i] = self._entry_lb.size()
            self._entry_lb.insert(tk.END, format_game_time(M.entry_day(e)))
            title = str(e.get("title") or tr("（無標題）")).replace("\n", " ")
            self._entry_lb.insert(tk.END, f"　　{title}")
            self._book_pos_to_entry.append(i)
            self._book_pos_to_entry.append(i)
        self._entry_lb.yview_moveto(top)
        if prev is not None and prev < len(self._entries):
            self._select_book_entry(prev)
        else:
            self._on_entry_select()

    def _book_selected_index(self) -> Optional[int]:
        s = self._entry_lb.curselection()
        if not s:
            return None
        pos = s[0]
        return self._book_pos_to_entry[pos] if pos < len(self._book_pos_to_entry) else None

    def _select_book_entry(self, i: int) -> None:
        first = self._book_first_pos.get(i)
        if first is None:
            return
        self._book_selecting = True
        try:
            self._entry_lb.selection_clear(0, tk.END)
            self._entry_lb.selection_set(first, first + 1)
            self._entry_lb.see(first)
        finally:
            self._book_selecting = False
        self._on_entry_select()

    def _on_entry_select(self) -> None:
        if self._book_selecting:
            return
        i = self._book_selected_index()
        # snap the highlight to both rows of the entry
        if i is not None:
            first = self._book_first_pos.get(i)
            cur = self._entry_lb.curselection()
            if first is not None and set(cur) != {first, first + 1}:
                self._select_book_entry(i)
                return
        t = self._entry_detail
        t.configure(state="normal")
        t.delete("1.0", "end")
        if i is None:
            t.insert("end", tr("（請選取左側條目）"), "empty")
            self._thumb.clear()
        else:
            e = self._entries[i]
            t.insert("end", str(e.get("title") or tr("（無標題）")) + "\n", "title")
            t.insert("end", f"ID：{e.get('id') or ''}\n", "idline")
            t.insert("end", f"{tr('日期')}：{format_game_time(M.entry_day(e))}\n", "key")
            has_image = M.resolve_memory_image(e, self._campaign_dir) is not None
            # 6.0's Memory Book renders `summary` — this IS the memory as the
            # player reads it, so it leads.
            summ = str(e.get("summary") or "").strip()
            t.insert("end", f"\n▋ {tr('記憶內容')}\n", "section")
            t.insert("end", (summ or tr("（無）")) + "\n", "body" if summ else "empty")
            # 6.0: the scene line is what the Memory Book feeds to image
            # generation, so it explains why an entry can still be illustrated
            # later even though it has no picture yet.
            scene = str(e.get("scene") or "").strip()
            t.insert("end", f"\n▋ {tr('場景描述')}\n", "section")
            t.insert("end", (scene or tr("（無）")) + "\n", "body" if scene else "empty")
            if scene and not has_image:
                t.insert("end", tr("（此條目有場景描述但尚無插圖；可在遊戲的記憶之書中補生成）") + "\n",
                         "empty")
            who = self._involved_display(e)
            t.insert("end", f"\n▋ {tr('涉及角色')}\n", "section")
            t.insert("end", (who or tr("（無）")) + "\n", "body" if who else "empty")
            # 5.0.x wrote the full text here and 6.0 stopped; show it read-only
            # so an old save's content isn't invisible, but never offer to edit
            # a field the game no longer reads.
            legacy = M.legacy_memory_text(e)
            if legacy:
                t.insert("end", f"\n▋ {tr('舊版完整記憶（唯讀）')}\n", "section")
                t.insert("end", legacy + "\n", "body")
            self._thumb.load(M.resolve_memory_image(e, self._campaign_dir))
        t.configure(state="disabled")
        self._refresh_edit_state()

    def _involved_display(self, entry: dict) -> str:
        """``involved_hero_ids`` as readable names, falling back to the raw id."""
        ids = entry.get("involved_hero_ids")
        if not isinstance(ids, list):
            return ""
        out = []
        for raw in ids:
            sid = str(raw or "").strip()
            if not sid:
                continue
            name = None
            if self._resolve_name:
                try:
                    name = self._resolve_name(sid)
                except Exception:
                    name = None
            out.append(f"{name} (`{sid}`)" if name else f"`{sid}`")
        return "、".join(out)

    # ── edit-mode gating ──────────────────────────────────────────────
    def _refresh_edit_state(self) -> None:
        editing = bool(self._edit_var.get())
        has_entry = self._book_selected_index() is not None
        self._set_state(self._entry_add, editing)
        self._set_state(self._entry_edit, editing and has_entry)
        self._set_state(self._entry_del, editing and has_entry)

    @staticmethod
    def _set_state(btn, enabled: bool) -> None:
        btn.configure(state=("normal" if enabled else "disabled"))

    # ── helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _sel_index(lb: tk.Listbox) -> Optional[int]:
        s = lb.curselection()
        return s[0] if s else None

    @staticmethod
    def _set_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _current_day_default(self) -> int:
        """Absolute campaign day to seed a new entry with.

        The campaign's current day if the connector exported one, else the
        newest memory — a new entry almost always describes something that
        just happened, not the day of the last one.
        """
        now = campaign_day_now(self._campaign_dir)
        if now:
            return int(round(now))
        if self._entries:
            return max(M.entry_day(e) for e in self._entries)
        return CAMPAIGN_START_DAY

    def _used_by_folder(self) -> dict:
        try:
            return {"memory_images": M.used_memory_image_ids(self._campaign_dir)}
        except Exception:
            return {}

    def _pick_image(self, parent, initial_filter: str = "all"):
        """Open the image picker; returns Path / None / PICKER_REMOVE."""
        return open_image_picker(
            parent, campaign_dir=self._campaign_dir, title=tr("選擇圖像"),
            used_by_folder=self._used_by_folder(), initial_filter=initial_filter,
            allow_remove=True,
        )

    # ── memory-book entry actions ─────────────────────────────────────
    def _add_entry(self) -> None:
        self._open_entry_dialog(None, {
            "campaign_day": self._current_day_default(), "title": "",
            "summary": "", "scene": "", "image_path": "",
        })

    def _edit_entry(self) -> None:
        i = self._book_selected_index()
        if i is None:
            return
        self._open_entry_dialog(i, self._entries[i])

    def _delete_entry(self) -> None:
        i = self._book_selected_index()
        if i is None:
            return
        if messagebox.askyesno(tr("刪除記憶條目"),
                               tr("確定刪除這則記憶之書條目嗎？（暫存，按右上「儲存」後寫入存檔）")):
            self._on_entry_delete(i)

    # ── image-row helper (shared by both dialogs) ─────────────────────
    def _build_image_row(self, win, entry: dict, is_new: bool) -> dict:
        """Build an image chooser row; return a state dict with mode/path.

        state = {"mode": keep|set|clear, "path": Path|None}
        """
        state = {"mode": "keep", "path": M.resolve_memory_image(entry, self._campaign_dir)}
        row = ttk.Frame(win)
        row.pack(fill=tk.X, padx=12, pady=(0, 4))
        ttk.Label(row, text=tr("圖像:")).pack(side=tk.LEFT, padx=(0, 6))
        name = tk.StringVar(value=(state["path"].name if state["path"] else tr("（無）")))
        ttk.Label(row, textvariable=name, foreground=tcol("#6B5B3E")).pack(side=tk.LEFT)

        def _pick(flt):
            p = self._pick_image(win, flt)
            if p is None:
                return
            if p is PICKER_REMOVE:
                state["mode"] = "clear"
                state["path"] = None
                name.set(tr("（已移除）"))
            else:
                state["mode"] = "set"
                state["path"] = p
                name.set(p.name)

        if is_new:
            ttk.Button(row, text=tr("選擇圖像（未使用）"), command=lambda: _pick("unused"),
                       style="secondary.TButton").pack(side=tk.LEFT, padx=(8, 2))
            ttk.Button(row, text=tr("選擇圖像（已使用）"), command=lambda: _pick("used"),
                       style="secondary.TButton").pack(side=tk.LEFT, padx=2)
        else:
            ttk.Button(row, text=tr("編輯圖像"), command=lambda: _pick("all"),
                       style="secondary.TButton").pack(side=tk.LEFT, padx=(8, 2))

        def _remove():
            state["mode"] = "clear"
            state["path"] = None
            name.set(tr("（已移除）"))
        ttk.Button(row, text=tr("🚫 移除圖像"), command=_remove,
                   style="danger.TButton").pack(side=tk.LEFT, padx=2)
        return state

    def _apply_image_state(self, fields: dict, state: dict, is_new: bool) -> None:
        """Fold the image chooser state into *fields* (image_path / _image_stem)."""
        if state["mode"] == "clear":
            fields["image_path"] = ""
        elif state["mode"] == "set" and state["path"] is not None:
            p = state["path"]
            fields["image_path"] = str(p)
            if is_new and self._campaign_dir and p.parent.name == "memory_images":
                fields["_image_stem"] = p.stem
        # mode == keep → leave image_path untouched (edit) / empty (new)

    # ── modal editors ─────────────────────────────────────────────────
    def _open_entry_dialog(self, index: Optional[int], entry: dict) -> None:
        is_new = index is None
        win = tk.Toplevel(self)
        win.title(tr("新增記憶條目") if is_new else tr("編輯記憶條目"))
        win.transient(self.winfo_toplevel())
        win.grab_set()
        center_window(win, 700, 700)

        ttk.Label(win, text=f"ID：{entry.get('id') or tr('（儲存後自動產生）')}",
                  foreground=tcol("#9A9A9A")).pack(anchor="w", padx=12, pady=(10, 0))

        drow = ttk.Frame(win)
        drow.pack(fill=tk.X, padx=12, pady=(6, 4))
        ttk.Label(drow, text=tr("記憶日期:")).pack(side=tk.LEFT, padx=(0, 6))
        date_field = GameDateField(drow, initial_value=M.entry_day(entry), show_raw=False)
        date_field.frame.pack(side=tk.LEFT)

        trow = ttk.Frame(win)
        trow.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(trow, text=tr("標題:")).pack(side=tk.LEFT, padx=(0, 6))
        title_var = tk.StringVar(value=str(entry.get("title") or ""))
        ttk.Entry(trow, textvariable=title_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 記憶內容 is the on-disk ``summary`` — 6.0's Memory Book displays this
        # field and nothing else, so it gets the room the old 完整記憶 box had.
        ttk.Label(win, text=tr("記憶內容:")).pack(anchor="w", padx=12)
        summary_txt = tk.Text(win, wrap="word", height=8, font=_MONO)
        summary_txt.pack(fill=tk.BOTH, expand=True, padx=12, pady=(2, 6))
        summary_txt.insert("1.0", str(entry.get("summary") or ""))

        ttk.Label(win, text=tr("場景描述:")).pack(anchor="w", padx=12)
        ttk.Label(win, text=tr("請以英文描述畫面，供遊戲的記憶之書補生成插圖；留空則不影響其他功能"),
                  foreground=tcol("#8A7A5A")).pack(anchor="w", padx=12)
        scene_txt = tk.Text(win, wrap="word", height=4, font=_MONO)
        scene_txt.pack(fill=tk.X, padx=12, pady=(2, 6))
        scene_txt.insert("1.0", str(entry.get("scene") or ""))

        legacy = M.legacy_memory_text(entry)
        if legacy:
            ttk.Label(win, text=tr("此條目另有舊版「完整記憶」文字，遊戲已不再顯示，故此處不提供編輯（保留原值）"),
                      foreground=tcol("#8A7A5A"), wraplength=620,
                      justify="left").pack(anchor="w", padx=12, pady=(0, 4))

        img_state = self._build_image_row(win, entry, is_new)

        # The picker works in absolute campaign days; 6.0 stores memory days as
        # elapsed-since-campaign-start.  Convert back on the way out, keeping
        # whichever convention this entry (or, for a new one, this book) uses.
        elapsed = M.book_uses_elapsed(self._entries) if is_new else M.entry_uses_elapsed(entry)

        def _ok():
            try:
                d = float(date_field.get())
            except (TypeError, ValueError):
                d = float(M.entry_day(entry))
            fields = {
                "campaign_day": M.to_stored_day(d, elapsed),
                "title": title_var.get().strip(),
                "summary": summary_txt.get("1.0", "end").strip(),
                "scene": scene_txt.get("1.0", "end").strip(),
            }
            # memory_text is deliberately absent: update_memory_entry only
            # touches keys it is given, so an old save keeps its legacy text.
            self._apply_image_state(fields, img_state, is_new)
            win.destroy()
            self._on_entry_save(index, fields)

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=12, pady=(0, 10))
        ttk.Button(btns, text=tr("確定"), command=_ok, style="success.TButton").pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text=tr("取消"), command=win.destroy, style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
