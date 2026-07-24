"""Reusable campaign-day ↔ year/season/day picker.

Pairs a raw campaign-day float with a human-readable 年/季/日 picker and a live
preview (e.g. ``1085年秋3日``).  Editing either side updates the other, with a
re-entrancy guard so trace callbacks don't loop, and the fractional time-of-day
component is preserved across round-trips.

Extracted from ``dialogs/dynamic_event_editor_dialog`` (v0.31.1) so the plot /
memory insert dialog can reuse the exact same date UX instead of showing a raw
campaign-day number players can't read.

Usage::

    df = GameDateField(parent, initial_value=91163.56)
    df.frame.pack(...)
    df.get()   # -> float campaign day (raises ValueError if unparseable)
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from i18n import tr
from services.time_format import (
    DAYS_PER_SEASON,
    date_to_game_days,
    format_game_time,
    game_days_to_date,
    season_display_options,
    season_key_from_label,
    season_label,
)
from ui.theme import tcol


def fmt_day(v: Any) -> str:
    """Format a campaign day number as a stable plain string for the entry box."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v) if v is not None else ""
    # Keep up to 2 decimals; trim trailing zeros for readability.
    s = f"{f:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


class GameDateField:
    """Compound widget pairing a raw campaign-day float with a 年/季/日 picker.

    Layout: ``[float entry] · 年 [spin] 季 [combo] 日 [spin]  → preview``
    """

    def __init__(self, parent, initial_value: Any = 0.0, *, show_raw: bool = True):
        self._suppress = False
        # Optional zero-arg callback fired whenever the value settles, so a host
        # widget can react (the 說話者 field rewrites its prefix from it).
        self.on_change = None
        try:
            init_float = float(initial_value)
        except (TypeError, ValueError):
            init_float = 0.0

        self.frame = ttk.Frame(parent)

        # Raw float entry (optional — hidden for player-facing dialogs where the
        # bare campaign-day number is just noise).
        self.float_var = tk.StringVar(value=fmt_day(init_float))
        if show_raw:
            ttk.Entry(self.frame, textvariable=self.float_var, width=12).pack(side=tk.LEFT)
            ttk.Label(self.frame, text="·", foreground=tcol("#888888")).pack(
                side=tk.LEFT, padx=(4, 4))

        # Year / Season / Day picker
        y, s, d = game_days_to_date(init_float)
        self._frac = max(0.0, init_float - int(init_float))

        ttk.Label(self.frame, text=tr("年")).pack(side=tk.LEFT)
        self.year_var = tk.StringVar(value=str(y))
        ttk.Spinbox(
            self.frame, textvariable=self.year_var,
            from_=0, to=99999, width=6,
            command=self._on_date_changed,
        ).pack(side=tk.LEFT, padx=(2, 6))

        ttk.Label(self.frame, text=tr("季")).pack(side=tk.LEFT)
        self.season_var = tk.StringVar(value=season_label(s))
        ttk.Combobox(
            self.frame, textvariable=self.season_var,
            values=season_display_options(), state="readonly", width=8,
        ).pack(side=tk.LEFT, padx=(2, 6))

        ttk.Label(self.frame, text=tr("日")).pack(side=tk.LEFT)
        self.day_var = tk.StringVar(value=str(d))
        ttk.Spinbox(
            self.frame, textvariable=self.day_var,
            from_=1, to=DAYS_PER_SEASON, width=4,
            command=self._on_date_changed,
        ).pack(side=tk.LEFT, padx=(2, 6))

        ttk.Label(self.frame, text="→", foreground=tcol("#888888")).pack(
            side=tk.LEFT, padx=(4, 4))
        self.preview_var = tk.StringVar(value=format_game_time(init_float))
        ttk.Label(
            self.frame, textvariable=self.preview_var,
            foreground=tcol("#1A6FA0"),
            font=("Microsoft JhengHei", 10, "bold"),
        ).pack(side=tk.LEFT)

        # Wire bidirectional sync.  trace_add covers typed input and combobox
        # selection; spinbox arrow-clicks already fire `command=` above.
        self.float_var.trace_add("write", lambda *_: self._on_float_changed())
        self.season_var.trace_add("write", lambda *_: self._on_date_changed())
        self.year_var.trace_add("write", lambda *_: self._on_date_changed())
        self.day_var.trace_add("write", lambda *_: self._on_date_changed())

    # ── Sync handlers ────────────────────────────────────────────────────

    def _on_float_changed(self) -> None:
        if self._suppress:
            return
        try:
            v = float(self.float_var.get())
        except (TypeError, ValueError):
            self.preview_var.set(tr("（無法解析）"))
            return
        if v < 0:
            v = 0.0
        y, s, d = game_days_to_date(v)
        self._frac = max(0.0, v - int(v))
        self._suppress = True
        try:
            self.year_var.set(str(y))
            self.season_var.set(season_label(s))
            self.day_var.set(str(d))
            self.preview_var.set(format_game_time(v))
        finally:
            self._suppress = False
        self._notify()

    def _on_date_changed(self) -> None:
        if self._suppress:
            return
        try:
            y = int(self.year_var.get())
            d = int(self.day_var.get())
        except (TypeError, ValueError):
            return    # mid-typing; ignore until value parses
        s = season_key_from_label(self.season_var.get())
        v = date_to_game_days(y, s, d, fraction=self._frac)
        self._suppress = True
        try:
            self.float_var.set(fmt_day(v))
            self.preview_var.set(format_game_time(v))
        finally:
            self._suppress = False
        self._notify()

    def _notify(self) -> None:
        if callable(self.on_change):
            try:
                self.on_change()
            except Exception:
                pass

    # ── Public ───────────────────────────────────────────────────────────

    def get(self) -> float:
        """Return the current campaign-day value (raises ValueError if unparseable)."""
        return float(self.float_var.get())

    def set_value(self, value) -> None:
        """Set the field from a campaign-day number (syncs the 年/季/日 picker)."""
        self.float_var.set(fmt_day(value))  # trace → _on_float_changed syncs pickers
