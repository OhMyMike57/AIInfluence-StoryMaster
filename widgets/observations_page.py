"""對話觀察 — the character's ``DialogueObservations`` log.

Every spoken line is recorded into each present character: the speaker and the
person addressed get ``direct``, bystanders get ``overheard`` with a distance and
a **distorted** transcript.  The mod never prunes this list, so it is the長期
record of "what this character actually witnessed" — and the data the
dynamic-event generator reads.

Read-only plus delete: there is no reliable way to synthesise a new observation
from outside the game (the mod hashes it with encrypted separators), so新增 is
deliberately absent — see ``services/observation_service`` for the details.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

from i18n import tr
from services import observation_service as O
from services.time_format import format_game_time
from ui import msgbox as messagebox
from ui import preview_font
from ui.theme import tcol
from ui.tree_helpers import make_sortable

_MONO = ("Microsoft JhengHei", 10)


class ObservationsPage(ttk.Frame):
    def __init__(
        self,
        parent,
        *,
        on_delete: Callable[[int], None],
        edit_variable: Optional[tk.BooleanVar] = None,
        resolve_name: Optional[Callable[[str], str]] = None,
        **kw,
    ):
        super().__init__(parent, **kw)
        self._on_delete = on_delete
        self._edit_var = edit_variable if edit_variable is not None else tk.BooleanVar(value=False)
        self._resolve_name = resolve_name

        self._obs: List[Dict[str, Any]] = []
        self._filter_var = tk.StringVar(value=tr("全部"))
        self._search_var = tk.StringVar()
        # tree iid -> index into self._obs (the tree is filtered/sorted, so the
        # row order never matches the underlying list; iid is the only safe key).
        self._row_to_index: Dict[str, int] = {}

        self._build_ui()
        self._edit_var.trace_add("write", lambda *_a: self._refresh_edit_state())

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=6, pady=(6, 2))
        # Own 編輯模式 toggle (shared app-level var) so the page is usable without
        # switching to another tab first — same as 記憶之書.
        ttk.Checkbutton(header, text=tr("編輯模式"),
                        variable=self._edit_var).pack(side=tk.LEFT, padx=(0, 10))
        self._summary_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self._summary_var,
                  font=("Microsoft JhengHei", 10, "bold"),
                  foreground=tcol("#1A3A5C")).pack(side=tk.LEFT)
        ttk.Label(header, text=tr("　（此紀錄不會過期，是動態事件生成的依據）"),
                  foreground=tcol("#9AA0A6"),
                  font=("Microsoft JhengHei", 9)).pack(side=tk.LEFT)

        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=6, pady=(0, 4))
        ttk.Label(bar, text=tr("聽取方式:")).pack(side=tk.LEFT)
        cb = ttk.Combobox(bar, textvariable=self._filter_var, state="readonly", width=10,
                          values=[tr("全部"), tr("直接聽到"), tr("旁聽")])
        cb.pack(side=tk.LEFT, padx=(4, 10))
        cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh_list())
        ttk.Label(bar, text="🔍").pack(side=tk.LEFT)   # icon only — nothing to translate
        ent = ttk.Entry(bar, textvariable=self._search_var, width=24)
        ent.pack(side=tk.LEFT, padx=(2, 0))
        self._search_var.trace_add("write", lambda *_a: self._refresh_list())
        self._del_btn = ttk.Button(bar, text=tr("🗑 刪除觀察"), command=self._delete_selected,
                                   style="danger.TButton")
        self._del_btn.pack(side=tk.RIGHT)

        panes = ttk.Panedwindow(self, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        top = ttk.Frame(panes)
        cols = ("day", "speaker", "role", "distance", "line")
        # extended: eavesdropped chatter arrives in bulk, so clearing it one row
        # at a time was the slowest possible way to do the most common job.
        # make_sortable() binds Ctrl+A for select-all.
        self._tree = ttk.Treeview(top, columns=cols, show="headings", selectmode="extended")
        for c, txt, w in (("day", tr("戰役日"), 110), ("speaker", tr("說話者"), 130),
                          ("role", tr("聽取方式"), 90), ("distance", tr("距離"), 70),
                          ("line", tr("內容"), 420)):
            self._tree.heading(c, text=txt)
            self._tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(top, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.tag_configure("overheard", foreground=tcol("#8A6D3B"))
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        make_sortable(self._tree, numeric_cols=("day", "distance"))
        panes.add(top, weight=3)

        bottom = ttk.Frame(panes)
        self._detail = tk.Text(bottom, wrap="word", font=_MONO, relief="flat",
                               padx=10, pady=8, cursor="arrow", height=10)
        dsb = ttk.Scrollbar(bottom, orient="vertical", command=self._detail.yview)
        self._detail.configure(yscrollcommand=dsb.set, state="disabled")
        dsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._detail.tag_configure("key", font=("Microsoft JhengHei", 10, "bold"),
                                   foreground=tcol("#6B5B3E"))
        self._detail.tag_configure("section", font=("Microsoft JhengHei", 11, "bold"),
                                   foreground=tcol("#2471A3"), spacing1=10, spacing3=4)
        self._detail.tag_configure("body", foreground=tcol("#222222"), lmargin1=12, lmargin2=12)
        self._detail.tag_configure("warn", foreground=tcol("#8A6D3B"))
        self._detail.tag_configure("empty", font=("Microsoft JhengHei", 10, "italic"),
                                   foreground=tcol("#999999"))
        preview_font.register(self._detail)
        panes.add(bottom, weight=2)

        self._refresh_edit_state()

    # ── data ──────────────────────────────────────────────────────────────
    def load(self, data: dict, npc_name: str = "") -> None:
        self._obs = O.observations(data)
        s = O.summarize(data)
        self._summary_var.set(
            tr("共 {total} 筆觀察（直接 {direct}／旁聽 {overheard}）・{scenes} 場對話")
            .format(**s))
        # New character → show the latest observation (same as 對話歷史);
        # same-character reloads keep the scroll position.
        changed = npc_name != getattr(self, "_loaded_npc", None)
        self._loaded_npc = npc_name
        self._refresh_list(reset_scroll=changed)

    def clear(self) -> None:
        self._obs = []
        self._summary_var.set("")
        self._refresh_list()

    # ── list ──────────────────────────────────────────────────────────────
    def _passes_filter(self, obs: Dict[str, Any]) -> bool:
        f = self._filter_var.get()
        if f == tr("直接聽到") and O.is_overheard(obs):
            return False
        if f == tr("旁聽") and not O.is_overheard(obs):
            return False
        needle = self._search_var.get().strip().lower()
        if not needle:
            return True
        haystack = " ".join(str(obs.get(k) or "") for k in
                            ("speaker_name", "speaker_hero_id", "canonical_line", "heard_line"))
        return needle in haystack.lower()

    def _refresh_list(self, reset_scroll: bool = False) -> None:
        prev = set(self._tree.selection())
        top = self._tree.yview()[0]
        last_iid = ""
        self._tree.delete(*self._tree.get_children())
        self._row_to_index = {}
        for i, obs in enumerate(self._obs):
            if not self._passes_filter(obs):
                continue
            day = O.campaign_day_of(obs)
            dist = O.distance_of(obs)
            over = O.is_overheard(obs)
            heard = str(obs.get("heard_line") or obs.get("canonical_line") or "")
            iid = f"obs::{i}"
            self._tree.insert(
                "", "end", iid=iid,
                values=(format_game_time(day) if day is not None else "—",
                        O.speaker_label(obs, self._resolve_name),
                        tr("旁聽") if over else tr("直接聽到"),
                        f"{dist:.1f}m" if dist is not None else "—",
                        heard.replace("\n", " ")[:160]),
                tags=("overheard",) if over else (),
            )
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
        self._refresh_edit_state()

    def _selected_index(self) -> Optional[int]:
        """Index of the row whose detail is shown (the first of the selection)."""
        sel = self._tree.selection()
        return self._row_to_index.get(sel[0]) if sel else None

    def selected_indices(self) -> List[int]:
        return sorted(self._row_to_index[i] for i in self._tree.selection()
                      if i in self._row_to_index)

    def _on_select(self) -> None:
        i = self._selected_index()
        self._render_detail(self._obs[i] if i is not None else None)
        self._refresh_edit_state()

    def _render_detail(self, obs: Optional[Dict[str, Any]]) -> None:
        t = self._detail
        t.configure(state="normal")
        t.delete("1.0", "end")
        if obs is None:
            t.insert("end", tr("（選擇一筆觀察以檢視內容）"), "empty")
            t.configure(state="disabled")
            return

        day = O.campaign_day_of(obs)
        dist = O.distance_of(obs)
        over = O.is_overheard(obs)
        t.insert("end", tr("說話者") + "：", "key")
        t.insert("end", O.speaker_label(obs, self._resolve_name) + "\n")
        t.insert("end", tr("戰役日") + "：", "key")
        t.insert("end", (format_game_time(day) if day is not None else "—") + "\n")
        t.insert("end", tr("聽取方式") + "：", "key")
        t.insert("end", (tr("旁聽") if over else tr("直接聽到"))
                 + (f"　{dist:.2f}m" if dist is not None else "") + "\n")
        t.insert("end", tr("場景 ID") + "：", "key")
        t.insert("end", O.scene_key(obs) + "\n")

        canon = str(obs.get("canonical_line") or "")
        heard = str(obs.get("heard_line") or "")
        if over and O.is_distorted(obs):
            # The two texts genuinely differ — show both so the player can see
            # exactly how much this listener missed.
            t.insert("end", "\n▋ " + tr("聽到的內容（已失真）") + "\n", "section")
            t.insert("end", (heard or tr("（無）")) + "\n", "warn" if heard else "empty")
            t.insert("end", "\n▋ " + tr("原本說的話") + "\n", "section")
            t.insert("end", (canon or tr("（無）")), "body" if canon else "empty")
        else:
            t.insert("end", "\n▋ " + tr("內容") + "\n", "section")
            t.insert("end", (canon or heard or tr("（無）")),
                     "body" if (canon or heard) else "empty")
        t.configure(state="disabled")

    # ── edit gating / delete ──────────────────────────────────────────────
    def _refresh_edit_state(self) -> None:
        picks = self.selected_indices()
        can = bool(self._edit_var.get()) and bool(picks)
        try:
            self._del_btn.configure(state=("normal" if can else "disabled"))
            self._del_btn.configure(
                text=(tr("🗑 刪除觀察") if len(picks) <= 1
                      else tr("🗑 刪除 {n} 筆").format(n=len(picks))))
        except tk.TclError:
            pass

    def _delete_selected(self) -> None:
        picks = self.selected_indices()
        if not picks or not self._edit_var.get():
            return
        if not messagebox.askyesno(
                tr("刪除觀察"),
                tr("確定刪除已選取的 {n} 筆對話觀察嗎？\n\n"
                   "刪除後這個角色就「沒有目擊過」這些話，動態事件不會再依它們生成。"
                   "（暫存，按右上「儲存」後寫入存檔）").format(n=len(picks))):
            return
        self._on_delete(picks)
