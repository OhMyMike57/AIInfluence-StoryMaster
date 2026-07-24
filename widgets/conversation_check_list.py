"""Scrollable conversation entry list with checkboxes.

Shared by sync_dialog (precise mode) and trim_dialog. Each row shows a
checkbox, line number, speaker-colored label, and character count.

Usage::

    widget = ConversationCheckList(parent, entries, npc_name, default_checked=set())
    widget.pack(fill="both", expand=True)

    indices = widget.checked_indices()          # [0, 3, 5]
    entries  = widget.checked_entries()          # original entry objects
    widget.select_last_n(10)
    widget.select_all()
    widget.clear_all()
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Set

from services.json_utils import entry_speaker, speaker_color
from i18n import tr
from ui.theme import paint, make_scrollable


class ConversationCheckList(ttk.Frame):
    """Scrollable list of conversation entries with per-row checkboxes."""

    def __init__(
        self,
        parent,
        entries: list,
        npc_name: str,
        *,
        default_checked: Optional[Set[int]] = None,
        on_count_change: Optional[Callable[[int, int], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._entries = entries
        self._npc_name = npc_name
        self._on_count_change = on_count_change
        self._check_vars: List[tk.BooleanVar] = []

        if default_checked is None:
            default_checked = set()

        self._outer, self._inner = make_scrollable(self)
        self._outer.pack(fill=tk.BOTH, expand=True)

        for i, entry in enumerate(entries):
            row = ttk.Frame(self._inner)
            row.pack(fill=tk.X, pady=2, padx=5)

            var = tk.BooleanVar(value=(i in default_checked))
            self._check_vars.append(var)

            ttk.Checkbutton(
                row, variable=var,
                command=self._fire_count_change,
            ).pack(side=tk.LEFT, padx=(0, 2))

            tk.Label(row, text=f"[{i + 1}]", width=5, anchor="e").pack(side=tk.LEFT)

            sp = entry_speaker(entry) or tr("未知")
            text = entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)
            display_text = text[:70] + ("..." if len(text) > 70 else "")
            label_text = tr("{sp}: {text} (共{n}字)").format(sp=sp, text=display_text, n=len(text))
            fg = speaker_color(sp, npc_name)

            paint(tk.Label(row, text=label_text,
                           wraplength=850, justify="left"),
                  fg=fg).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self._entries)

    def checked_count(self) -> int:
        return sum(1 for v in self._check_vars if v.get())

    def checked_indices(self) -> List[int]:
        return [i for i, v in enumerate(self._check_vars) if v.get()]

    def checked_entries(self) -> list:
        return [self._entries[i] for i in self.checked_indices()]

    def select_last_n(self, n: int) -> None:
        for var in self._check_vars:
            var.set(False)
        start = max(0, len(self._entries) - n)
        for i in range(start, len(self._entries)):
            self._check_vars[i].set(True)
        self._fire_count_change()

    def select_all(self) -> None:
        for var in self._check_vars:
            var.set(True)
        self._fire_count_change()

    def clear_all(self) -> None:
        for var in self._check_vars:
            var.set(False)
        self._fire_count_change()

    # ── Internal ──────────────────────────────────────────────────────────

    def _fire_count_change(self) -> None:
        if self._on_count_change:
            self._on_count_change(self.checked_count(), self.total)
