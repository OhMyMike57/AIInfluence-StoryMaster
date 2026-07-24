"""Character-centric viewer for the RecentEvents array.

Displays events with type-coloured tags, game-date formatting, checkboxes
for bulk-delete, and a "clear all" action.  All interactive elements use a
single tk.Text with embedded checkboxes (ttk.Checkbutton via window_create)
so the list stays scrollable and consistent with other viewers.

Usage::

    viewer = RecentEventsViewer(
        parent,
        on_delete=app._recent_event_delete,   # (checked_indices: List[int]) -> None
        on_clear=app._recent_event_clear,     # () -> None
    )
    viewer.pack(fill="both", expand=True)
    viewer.load(events_list)    # list of {Type, Description, EventTimeDays}
    viewer.clear()
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Callable, List, Optional

from i18n import tr
from services.time_format import format_game_time
from services.display_labels import recent_event_label
from ui import preview_font
from ui.theme import tcol

# ── Event-type colour map (light values; adapt at use via _type_colors()) ────
_TYPE_COLORS: dict = {
    "WarDeclared":    "#C0392B",   # 深紅
    "PeaceMade":      "#27AE60",   # 深綠
    "HeroKilled":     "#8E1010",   # 暗紅
    "Battle":         "#D35400",   # 橘
    "Tournament":     "#2471A3",   # 藍
    "Default":        "#6B5B3E",   # 棕（fallback）
}


def _type_colors() -> dict:
    """Event-type colours adapted to the active theme (light returns as-is)."""
    return {k: tcol(v) for k, v in _TYPE_COLORS.items()}

_SEPARATOR = "─" * 80


class RecentEventsViewer(ttk.Frame):
    """Scrollable viewer for a character's RecentEvents list.

    Header layout (same as OwnedItemsViewer / ConversationViewer):
      LEFT:  [□ 編輯模式]
      RIGHT: 總筆數 N ｜ 已勾選 M
    """

    def __init__(
        self,
        parent,
        *,
        on_delete: Callable[[List[int]], None],
        on_clear: Callable[[], None],
        edit_variable: Optional[tk.BooleanVar] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._on_delete = on_delete
        self._on_clear  = on_clear

        self._events:    List[dict] = []
        self._check_vars: List[tk.BooleanVar] = []

        # edit_variable: pass the app-wide shared var so edit mode toggles
        # everywhere at once; omit for a standalone per-widget toggle.
        self._edit_var  = edit_variable if edit_variable is not None else tk.BooleanVar(value=False)
        self._stats_var = tk.StringVar(value="")

        self._build_ui()
        # React to external flips of a shared variable (not just our checkbox).
        self._edit_var.trace_add("write", lambda *_: self._toggle_edit_mode())

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Header ────────────────────────────────────────────────────────────
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=6, pady=(4, 0))

        self._edit_cb = ttk.Checkbutton(
            header,
            text=tr("編輯模式"),
            variable=self._edit_var,
            state="disabled",
        )
        self._edit_cb.pack(side=tk.LEFT)

        ttk.Label(header, textvariable=self._stats_var, foreground=tcol("#6B5B3E")).pack(
            side=tk.RIGHT, padx=8
        )

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=4, pady=(4, 0))

        # ── Action bar (edit-mode only) ───────────────────────────────────────
        self._action_bar = ttk.Frame(self)
        ttk.Button(
            self._action_bar,
            text=tr("✗ 刪除勾選"),
            command=self._on_delete_checked,
            style="secondary.TButton",
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            self._action_bar,
            text=tr("🗑 全部清空"),
            command=self._on_clear_all,
            style="danger.TButton",
        ).pack(side=tk.LEFT)
        # Initially hidden; shown when edit mode enabled.

        # ── Main scrollable text ──────────────────────────────────────────────
        tc = ttk.Frame(self)
        tc.pack(fill=tk.BOTH, expand=True)

        self._text = tk.Text(
            tc,
            wrap="word",
            state="disabled",
            cursor="arrow",
            font=("Microsoft JhengHei", 10),
            spacing1=2,
            spacing3=2,
        )
        vsb = ttk.Scrollbar(tc, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Tag definitions
        self._text.tag_configure("desc",  foreground=tcol("#333333"))
        self._text.tag_configure("time",  foreground=tcol("#555555"), font=("Microsoft JhengHei", 9))
        self._text.tag_configure("sep",   foreground=tcol("#cccccc"), font=("", 1),
                                  spacing1=0, spacing3=0)
        self._text.tag_configure("placeholder", foreground=tcol("#999999"),
                                  font=("Microsoft JhengHei", 10, "italic"))
        # Dynamic type-colour tags created on first render to avoid stale configs.
        for etype, color in _type_colors().items():
            self._text.tag_configure(
                f"type_{etype}", foreground=color,
                font=("Microsoft JhengHei", 10, "bold"),
            )
        preview_font.register(self._text)

    # ── Edit mode ─────────────────────────────────────────────────────────────

    def _toggle_edit_mode(self) -> None:
        if self._edit_var.get():
            # Bottom-docked action bar (aligns with the 對話 tab).
            self._action_bar.pack(fill=tk.X, padx=6, pady=(4, 6), side=tk.BOTTOM)
        else:
            self._action_bar.pack_forget()
        self._render()

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, events: List[dict], npc_name: str = "") -> None:
        """Populate the viewer with a character's RecentEvents list."""
        self._events = list(events) if isinstance(events, list) else []
        changed = npc_name != getattr(self, "_loaded_npc", None)
        self._loaded_npc = npc_name
        # Do NOT reset the shared edit mode on character switch — it is app-wide
        # and must stay sticky across characters.  Just re-sync the action bar
        # to whatever the (possibly externally-set) edit state currently is.
        self._edit_cb.configure(state="normal" if self._events else "disabled")
        if self._edit_var.get():
            self._action_bar.pack(fill=tk.X, padx=6, pady=(4, 6), side=tk.BOTTOM)
        else:
            self._action_bar.pack_forget()
        self._render(reset_scroll=changed)
        self._update_stats()

    def clear(self) -> None:
        """Remove all displayed content."""
        self._events = []
        self._check_vars = []
        # Keep the shared edit mode sticky; just hide the action bar while empty.
        self._action_bar.pack_forget()
        self._edit_cb.configure(state="disabled")
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._stats_var.set("")

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, reset_scroll: bool = False) -> None:
        prev_top = self._text.yview()[0]
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._check_vars = []

        editing = self._edit_var.get()

        if not self._events:
            self._text.insert("end", tr("（此角色尚無近期事件）"), "placeholder")
            self._text.configure(state="disabled")
            return

        for i, ev in enumerate(self._events):
            if i > 0:
                self._text.insert("end", _SEPARATOR + "\n", "sep")

            etype = str(ev.get("Type", ev.get("type", "Default")))
            desc  = str(ev.get("Description", ev.get("description", ""))).strip()
            days  = ev.get("EventTimeDays", ev.get("eventTimeDays"))

            # ── Row: [checkbox]  [TYPE]  time ─────────────────────────────
            if editing:
                var = tk.BooleanVar(value=False)
                self._check_vars.append(var)
                var.trace_add("write", lambda *_, _i=i: self._on_check_change())
                cb = ttk.Checkbutton(self._text, variable=var)
                self._text.window_create("end", window=cb)
                self._text.insert("end", "  ")
            else:
                self._check_vars.append(tk.BooleanVar(value=False))  # placeholder

            tag = f"type_{etype}" if f"type_{etype}" in self._text.tag_names() else "type_Default"
            self._text.insert("end", f"[{recent_event_label(etype)}]", tag)

            if days is not None:
                try:
                    time_str = format_game_time(float(days))
                except (TypeError, ValueError):
                    time_str = str(days)
                self._text.insert("end", f"  {time_str}\n", "time")
            else:
                self._text.insert("end", "\n")

            # ── Description ───────────────────────────────────────────────
            if desc:
                self._text.insert("end", desc + "\n", "desc")

        self._text.configure(state="disabled")
        # New character → top; edit re-render (delete / toggle) → stay put.
        if reset_scroll:
            self._text.see("1.0")
        else:
            self._text.yview_moveto(prev_top)

    def _update_stats(self) -> None:
        checked = sum(1 for v in self._check_vars if v.get())
        total   = len(self._events)
        self._stats_var.set(tr("總筆數 {total}　｜　已勾選 {checked}").format(total=total, checked=checked))

    def _on_check_change(self) -> None:
        self._update_stats()

    # ── Action handlers ───────────────────────────────────────────────────────

    def _on_delete_checked(self) -> None:
        indices = [i for i, v in enumerate(self._check_vars) if v.get()]
        if not indices:
            messagebox.showinfo(tr("刪除勾選"), tr("請先勾選要刪除的事件。"),
                                parent=self.winfo_toplevel())
            return
        if messagebox.askyesno(
            tr("確認刪除"),
            tr("確定要刪除勾選的 {n} 條近期事件？").format(n=len(indices)),
            parent=self.winfo_toplevel(),
        ):
            self._on_delete(indices)

    def _on_clear_all(self) -> None:
        if not self._events:
            return
        if messagebox.askyesno(
            tr("全部清空"),
            tr("確定要清空此角色所有 {n} 條近期事件？（暫存，按右上「儲存」後生效）").format(n=len(self._events)),
            parent=self.winfo_toplevel(),
        ):
            self._on_clear()
