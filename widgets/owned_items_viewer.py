"""Character-centric viewer for owned world info / secrets / dynamic events.

Edit-mode flow (v0.36 — unified doc staging):

  1. User toggles ☐ 編輯模式 → ＋ 加入 / 🔍 有效檢查 buttons appear.
  2. Add or remove operations mutate the app's **staged working copy** of the
     character JSON (no disk write).  Pending items render with visual markers:
       - Pending-add  → green "+ " prefix
       - Pending-remove → strikethrough + grey
  3. Saving happens via the app-global 💾 儲存 / ↩ 取消 (top-right of the main
     workspace) — this viewer only shows an orange pending-count badge.
     Pending changes survive character switches and edit-mode toggles.

Usage::

    viewer = OwnedItemsViewer(
        parent,
        kind="info",                               # "info" / "secrets" / "dynamic_events"
        on_stage_add    = app._owned_stage_add,    # (ids: list, kind: str) -> None
        on_stage_remove = app._owned_stage_remove, # (iid: str, kind: str) -> None
        get_pending     = app._owned_get_pending,  # (kind: str) -> (adds:set, removes:set)
    )
    viewer.pack(fill="both", expand=True)
    viewer.load(owned_ids, all_items, npc_name="Liena")
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Callable, List, Optional, Set, Tuple

from i18n import tr
from ui import preview_font
from ui.theme import paint, tcol

# Fixed pixel height for the add panel (add panel is pack BOTTOM, fixed height)
_ADD_PANEL_H = 270


class OwnedItemsViewer(ttk.Frame):
    """Viewer for one category (info / secrets / events) of a character's owned items."""

    def __init__(
        self,
        parent,
        *,
        kind: str = "info",
        kind_label: str = "",                                 # display name, e.g. "訊息"
        on_stage_add:    Callable[[List[str], str], None],    # (item_ids, kind)
        on_stage_remove: Callable[[str, str], None],          # (item_id, kind)
        on_commit:       Optional[Callable[[str], bool]] = None,           # deprecated (v0.36: global save)
        on_discard:      Optional[Callable[[str], None]] = None,           # deprecated (v0.36: global save)
        get_pending:     Optional[Callable[[str], Tuple[Set[str], Set[str]]]] = None,
        edit_variable:   Optional[tk.BooleanVar] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._shared_edit_var = edit_variable
        self._kind       = kind
        # Fallback to a sensible default when caller does not supply kind_label.
        self._kind_label = kind_label or (tr("訊息") if kind == "info" else (tr("秘密") if kind == "secrets" else kind))
        self._on_stage_add    = on_stage_add
        self._on_stage_remove = on_stage_remove
        self._on_commit       = on_commit
        self._on_discard      = on_discard
        self._get_pending     = get_pending

        self._owned_ids:    List[str]  = []
        self._all_items:    List[dict] = []
        self._npc_name:     str        = ""
        self._add_open:     bool       = False
        self._edit_var:     tk.BooleanVar  # created in _build_ui
        self._avail_map:    List[str]  = []   # listbox index → item_id

        self._stats_var   = tk.StringVar(value="")
        self._pending_var = tk.StringVar(value="")

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Header ────────────────────────────────────────────────────────
        # Shared app-wide var when supplied (global edit mode), else standalone.
        self._edit_var = self._shared_edit_var if self._shared_edit_var is not None \
            else tk.BooleanVar(value=False)
        # External flips (from another tab's checkbox) must sync our UI without
        # running the pending-changes guard — that guard belongs to OUR checkbox
        # only (see _toggle_edit_mode).
        self._edit_var.trace_add("write", lambda *_: self._apply_edit_ui())

        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=6, pady=(4, 0), side=tk.TOP)

        # LEFT: edit mode checkbutton
        self._edit_cb = ttk.Checkbutton(
            header, text=tr("編輯模式"),
            variable=self._edit_var,
            command=self._toggle_edit_mode,
            state="disabled",
        )
        self._edit_cb.pack(side=tk.LEFT)

        # RIGHT (outermost): stats label
        ttk.Label(header, textvariable=self._stats_var, foreground=tcol("#6B5B3E")).pack(
            side=tk.RIGHT, padx=8
        )

        # (v0.36: the per-tab 💾 儲存 / ↩ 取消 buttons were removed — saving is
        #  the app-global bar's job; only the pending badge remains here.)

        # RIGHT (right of stats): pending-count badge
        self._pending_lbl = paint(
            tk.Label(header, textvariable=self._pending_var,
                     font=("", 9, "bold"), padx=6, pady=1),
            foreground=tcol("#FFFFFF"), background=tcol("#E67E22"))
        self._pending_lbl_pack_kwargs = dict(side=tk.RIGHT, padx=(0, 4))
        # Not packed initially.

        # RIGHT: 🔍 有效檢查 — always available (no edit mode requirement)
        self._check_btn = ttk.Button(
            header, text=tr("🔍 有效檢查"),
            command=self._on_check_validity,
            style="secondary.TButton",
            state="disabled",
        )
        self._check_btn.pack(side=tk.RIGHT, padx=(0, 4))

        # RIGHT (leftmost of the row): ＋ 加入 — only packed in edit mode
        self._add_btn = ttk.Button(
            header, text=tr("＋ 加入"),
            command=self._toggle_add_panel,
            style="secondary.TButton",
        )
        self._add_btn_pack_kwargs = dict(side=tk.RIGHT, padx=(0, 4))
        # NOTE: not packed initially — shown only when edit mode is enabled.

        ttk.Separator(self, orient="horizontal").pack(
            fill=tk.X, padx=4, pady=(4, 0), side=tk.TOP
        )

        # ── Add panel (BOTTOM, fixed height, hidden by default) ───────────
        self._add_wrap = ttk.Frame(self, height=_ADD_PANEL_H, relief="groove", borderwidth=1)
        self._add_wrap.pack_propagate(False)

        btn_row = ttk.Frame(self._add_wrap)
        btn_row.pack(fill=tk.X, padx=6, pady=(0, 6), side=tk.BOTTOM)
        # 取消 left, 加入 right — tool-wide button convention.
        ttk.Button(
            btn_row, text=tr("取消"), command=self._toggle_add_panel,
            style="secondary.TButton",
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            btn_row, text=tr("加入"), command=self._on_add_confirm,
            style="warning.TButton",
        ).pack(side=tk.LEFT)

        paned = ttk.PanedWindow(self._add_wrap, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))

        left_frame  = ttk.Frame(paned)
        right_frame = ttk.Frame(paned)
        paned.add(left_frame,  weight=2)
        paned.add(right_frame, weight=3)

        ttk.Label(left_frame, text=tr("搜尋:")).pack(anchor="w", padx=4, pady=(2, 0))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_avail())
        ttk.Entry(left_frame, textvariable=self._search_var).pack(
            fill=tk.X, padx=4, pady=(2, 4)
        )

        lf = ttk.Frame(left_frame)
        lf.pack(fill=tk.BOTH, expand=True, padx=4)
        self._avail_lb  = tk.Listbox(lf, selectmode=tk.EXTENDED, activestyle="none")
        avail_vsb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self._avail_lb.yview)
        self._avail_lb.configure(yscrollcommand=avail_vsb.set)
        self._avail_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        avail_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._avail_lb.bind("<<ListboxSelect>>", self._on_avail_select)

        ttk.Label(right_frame, text=tr("描述:")).pack(anchor="w", padx=4, pady=(2, 0))
        rf = ttk.Frame(right_frame)
        rf.pack(fill=tk.BOTH, expand=True, padx=4)
        self._desc_text = tk.Text(
            rf, wrap="word", state="disabled",
            font=("Microsoft JhengHei", 10),
            relief="flat",
        )
        desc_vsb = ttk.Scrollbar(rf, orient=tk.VERTICAL, command=self._desc_text.yview)
        self._desc_text.configure(yscrollcommand=desc_vsb.set)
        self._desc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        desc_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._add_wrap.pack(fill=tk.X, padx=4, side=tk.BOTTOM)
        self._add_wrap.pack_forget()

        # ── Main text widget (fills remaining space) ──────────────────────
        tc = ttk.Frame(self)
        tc.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self._text = tk.Text(
            tc, wrap="word", state="disabled", cursor="arrow",
            font=("Microsoft JhengHei", 10), spacing1=4, spacing3=4,
            height=1,
        )
        vsb = ttk.Scrollbar(tc, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Tag definitions
        self._text.tag_configure(
            "item_id", foreground=tcol("#0451a5"),
            font=("Microsoft JhengHei", 10, "bold"),
        )
        self._text.tag_configure("desc", foreground=tcol("#333333"))
        self._text.tag_configure(
            "del_btn", foreground=tcol("#C0392B"),
            font=("Microsoft JhengHei", 10, "bold"),
        )
        self._text.tag_configure(
            "sep", foreground=tcol("#cccccc"),
            font=("", 1), spacing1=0, spacing3=0,
        )
        self._text.tag_configure(
            "placeholder", foreground=tcol("#999999"),
            font=("Microsoft JhengHei", 10, "italic"),
        )
        self._text.tag_configure(
            "invalid", foreground=tcol("#C0392B"),
            font=("Microsoft JhengHei", 10, "italic"),
        )
        # Stage-C tags (pending visualisations)
        self._text.tag_configure(
            "pending_add", foreground=tcol("#27AE60"),
            font=("Microsoft JhengHei", 10, "bold"),
        )
        self._text.tag_configure(
            "pending_remove",
            foreground=tcol("#999999"), overstrike=True,
            font=("Microsoft JhengHei", 10),
        )
        self._text.tag_configure(
            "pending_remove_id",
            foreground=tcol("#777777"), overstrike=True,
            font=("Microsoft JhengHei", 10, "bold"),
        )
        self._text.tag_configure(
            "stage_marker", foreground=tcol("#888888"),
            font=("Microsoft JhengHei", 9, "italic"),
        )
        preview_font.register(self._text)

        self._text.tag_bind("del_btn", "<Enter>",
                            lambda e: self._text.configure(cursor="hand2"))
        self._text.tag_bind("del_btn", "<Leave>",
                            lambda e: self._text.configure(cursor="arrow"))
        self._text.tag_bind("del_btn", "<Button-1>", self._on_del_click)

    # ── Edit mode ─────────────────────────────────────────────────────────────

    def _toggle_edit_mode(self) -> None:
        """Called by OUR Checkbutton; _edit_var already reflects the new state.

        v0.36: no pending guard here — staged changes live in the app-global
        doc staging and survive edit-mode toggles; the UI sync happens in
        _apply_edit_ui via the variable trace.
        """
        self._apply_edit_ui()

    def _apply_edit_ui(self) -> None:
        """Idempotent UI sync for the current _edit_var state (no prompts)."""
        editing = self._edit_var.get()
        if editing:
            self._add_btn.pack(**self._add_btn_pack_kwargs)
        else:
            self._add_btn.pack_forget()
            if self._add_open:
                self._add_wrap.pack_forget()
                self._add_open = False
                self._add_btn.configure(text=tr("＋ 加入"))
        self._render()
        self.refresh_pending_visuals()

    # ── Tag click dispatch ────────────────────────────────────────────────────

    def _row_from_event(self, event) -> int:
        idx = self._text.index(f"@{event.x},{event.y}")
        for tag in self._text.tag_names(idx):
            if tag.startswith("row_"):
                try:
                    return int(tag[4:])
                except ValueError:
                    pass
        return -1

    def _on_del_click(self, event) -> None:
        if not self._edit_var.get():
            return "break"
        row = self._row_from_event(event)
        rendered_ids = self._effective_render_ids()
        if 0 <= row < len(rendered_ids):
            item_id = rendered_ids[row]
            # Stage the removal (or cancel a pending add) — no confirm dialog;
            # the user will see/cancel via the save/cancel buttons.
            self._on_stage_remove(item_id, self._kind)
            self._render()
            self.refresh_pending_visuals()
        return "break"

    # ── Validity check ────────────────────────────────────────────────────────

    def _on_check_validity(self) -> None:
        """Scan owned IDs; report and optionally clean up invalid entries.

        Note: the validity check operates against the **on-disk** owned list
        (ignoring pending mutations) to give a clean snapshot.  Cleanup
        operations are staged like any other removal.
        """
        id_map = {str(it.get("id", "")).strip(): it for it in self._all_items}
        invalid = [iid for iid in self._owned_ids if iid not in id_map]
        kind_lbl = self._kind_label
        if not invalid:
            messagebox.showinfo(
                tr("有效檢查"),
                tr("所有{kind_lbl}條目皆有效（共 {n} 條）").format(
                    kind_lbl=kind_lbl, n=len(self._owned_ids)),
                parent=self.winfo_toplevel(),
            )
            return
        listing = "\n".join(f"  • {iid}" for iid in invalid)
        if messagebox.askyesno(
            tr("發現 {n} 個失效條目").format(n=len(invalid)),
            tr("以下 ID 已不存在於世界資料：\n\n{listing}\n\n是否暫存清除？\n（按右上角「💾 儲存」後才寫入檔案）").format(listing=listing),
            parent=self.winfo_toplevel(),
        ):
            for iid in invalid:
                self._on_stage_remove(iid, self._kind)
            self._render()
            self.refresh_pending_visuals()

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, owned_ids: List[str], all_items: List[dict], npc_name: str = "") -> None:
        """Populate the viewer for the given character."""
        self._owned_ids = [str(x) for x in owned_ids if x]
        self._all_items = list(all_items)
        changed = npc_name != getattr(self, "_npc_name", None)
        self._npc_name  = npc_name

        # Do NOT reset the shared edit mode on character switch — it is app-wide
        # and stays sticky across characters (the app checks pending changes
        # before switching).  Fold any add panel left open by the previous char.
        if self._add_open:
            self._add_wrap.pack_forget()
            self._add_open = False
            self._add_btn.configure(text=tr("＋ 加入"))

        self._edit_cb.configure(state="normal")
        self._check_btn.configure(state="normal")
        # Sync the add button to the current (possibly externally-set) edit state.
        if self._edit_var.get():
            self._add_btn.pack(**self._add_btn_pack_kwargs)
        else:
            self._add_btn.pack_forget()

        self._render(reset_scroll=changed)
        self._update_stats()
        self.refresh_pending_visuals()

    def show_no_data(self) -> None:
        """Display a placeholder when world data has not been loaded yet."""
        # Keep the shared edit mode sticky; with no data the add/edit affordances
        # below are hidden regardless of edit state.
        if self._add_open:
            self._add_wrap.pack_forget()
            self._add_open = False
            self._add_btn.configure(text=tr("＋ 加入"))

        self._owned_ids = []
        self._all_items = []

        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", tr("尚未載入世界資料"), "placeholder")
        self._text.configure(state="disabled")

        self._stats_var.set("")
        self._add_btn.pack_forget()
        self._check_btn.configure(state="disabled")
        self._edit_cb.configure(state="disabled")
        self.refresh_pending_visuals()

    def clear(self) -> None:
        self.show_no_data()

    def refresh_pending_visuals(self) -> None:
        """Update the pending-count badge (saving is the global bar's job)."""
        n = self._pending_count()
        if n > 0:
            self._pending_var.set(f" {n} {tr('暫存')} ")
            try:
                self._pending_lbl.pack(**self._pending_lbl_pack_kwargs)
            except Exception:
                pass
        else:
            self._pending_var.set("")
            try:
                self._pending_lbl.pack_forget()
            except Exception:
                pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _pending(self) -> Tuple[Set[str], Set[str]]:
        if self._get_pending is None:
            return (set(), set())
        try:
            adds, removes = self._get_pending(self._kind)
            return (set(adds or ()), set(removes or ()))
        except Exception:
            return (set(), set())

    def _pending_count(self) -> int:
        adds, removes = self._pending()
        return len(adds) + len(removes)

    def _effective_render_ids(self) -> List[str]:
        """Compute the on-screen row order: existing items + pending adds."""
        adds, removes = self._pending()
        # Existing items: keep order; do NOT skip pending-removes (we render
        # them with strikethrough so the user can see them about to vanish).
        out: List[str] = list(self._owned_ids)
        existing = set(out)
        for new_id in sorted(adds):
            if new_id not in existing:
                out.append(new_id)
                existing.add(new_id)
        return out

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, reset_scroll: bool = False) -> None:
        prev_top = self._text.yview()[0]
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")

        editing = self._edit_var.get()
        adds, removes = self._pending()

        id_map: dict = {str(it.get("id", "")).strip(): it for it in self._all_items}
        rendered_ids = self._effective_render_ids()

        for i, item_id in enumerate(rendered_ids):
            if i > 0:
                self._text.insert("end", "─" * 100 + "\n", "sep")

            row_tag = f"row_{i}"
            del_tag = f"del_{i}"
            item = id_map.get(item_id)
            is_pending_add    = item_id in adds
            is_pending_remove = item_id in removes

            # ── Title line ─────────────────────────────────────────────
            if is_pending_add:
                self._text.insert("end", "+ ", ("pending_add", row_tag))
            if is_pending_remove:
                self._text.insert("end", item_id, ("pending_remove_id", row_tag))
            else:
                self._text.insert("end", item_id, ("item_id", row_tag))

            if item is None:
                self._text.insert("end", "　" + tr("(已失效)"), ("invalid", row_tag))

            # Stage marker
            if is_pending_add:
                self._text.insert("end", "  ", row_tag)
                self._text.insert("end", tr("[暫存新增]"), ("stage_marker", row_tag))
            elif is_pending_remove:
                self._text.insert("end", "  ", row_tag)
                self._text.insert("end", tr("[暫存移除]"), ("stage_marker", row_tag))

            # Delete button (visible only in edit mode)
            if editing:
                self._text.insert("end", "  ")
                # Label depends on staged state:
                #   pending_remove → [↩ 復原]
                #   pending_add or normal → [✗]
                btn_text = tr("[↩ 復原]") if is_pending_remove else tr("[✗]")
                self._text.insert("end", btn_text, ("del_btn", del_tag, row_tag))
            self._text.insert("end", "\n")

            # ── Description ────────────────────────────────────────────
            if item:
                desc = str(item.get("description", "")).strip()
                display_text = desc if desc else tr("（此條目無描述：{id}）").format(id=item_id)
            else:
                display_text = tr("（找不到此條目的內容：{id}）").format(id=item_id)
            desc_tag = "pending_remove" if is_pending_remove else "desc"
            self._text.insert("end", display_text + "\n", desc_tag)

        if not rendered_ids:
            kind_lbl = self._kind_label
            self._text.insert("end", tr("（此角色尚未擁有任何{k}）").format(k=kind_lbl), "placeholder")

        self._text.configure(state="disabled")
        # New character → top; edit re-render (stage/cancel/validate) → stay put.
        if reset_scroll:
            self._text.see("1.0")
        else:
            self._text.yview_moveto(prev_top)

    def _update_stats(self) -> None:
        kind_lbl = self._kind_label
        self._stats_var.set(tr("擁有{k} {n} 條").format(k=kind_lbl, n=len(self._owned_ids)))

    # ── Add panel ─────────────────────────────────────────────────────────────

    def _toggle_add_panel(self) -> None:
        if self._add_open:
            self._add_wrap.pack_forget()
            self._add_open = False
            self._add_btn.configure(text=tr("＋ 加入"))
        else:
            self._search_var.set("")
            self._refresh_avail()
            self._add_wrap.pack(fill=tk.X, padx=4, side=tk.BOTTOM)
            self._add_open = True
            self._add_btn.configure(text=tr("▲ 收起"))

    def _refresh_avail(self) -> None:
        """Rebuild the candidate listbox: items not yet owned (incl. pending adds)."""
        adds, _removes = self._pending()
        owned_set = set(self._owned_ids) | set(adds)  # exclude pending adds too
        term = self._search_var.get().strip().lower()

        self._avail_lb.delete(0, tk.END)
        self._avail_map.clear()
        self._show_preview("")

        for item in self._all_items:
            item_id = str(item.get("id", "")).strip()
            if not item_id or item_id in owned_set:
                continue
            desc = str(item.get("description", ""))
            if term and term not in item_id.lower() and term not in desc.lower():
                continue
            self._avail_lb.insert(tk.END, item_id)
            self._avail_map.append(item_id)

    def _on_avail_select(self, event=None) -> None:
        sel = self._avail_lb.curselection()
        if not sel:
            return
        item_id = self._avail_map[sel[-1]] if sel[-1] < len(self._avail_map) else ""
        if not item_id:
            return
        id_map = {str(it.get("id", "")).strip(): it for it in self._all_items}
        item = id_map.get(item_id)
        self._show_preview(str(item.get("description", "")) if item else "")

    def _show_preview(self, text: str) -> None:
        self._desc_text.configure(state="normal")
        self._desc_text.delete("1.0", "end")
        if text:
            self._desc_text.insert("1.0", text)
        self._desc_text.configure(state="disabled")

    def _on_add_confirm(self) -> None:
        sel = self._avail_lb.curselection()
        if not sel:
            return
        ids = [self._avail_map[i] for i in sel if i < len(self._avail_map)]
        if not ids:
            return
        # No confirm dialog — staging is reversible via the cancel button.
        self._add_wrap.pack_forget()
        self._add_open = False
        self._add_btn.configure(text=tr("＋ 加入"))
        self._on_stage_add(ids, self._kind)
        self._render()
        self.refresh_pending_visuals()
