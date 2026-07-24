"""角色屬性 editor — a small modal for the 摘要 tab's 「編輯屬性」 action.

Lists identity/social attributes; only 浪漫 / 信任 / 互動 / 最後互動時間 are
editable.  關係 (real game relation) and 情緒升降 (AI-managed escalation string)
are shown read-only.  On save it hands the app a minimal ``changes`` dict of the
values that actually changed; the app writes them via the
``services.character_service`` setters.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from i18n import tr
from widgets.game_date_field import GameDateField
from widgets.window_center import center_window
from services.character_service import (
    player_romance_level,
    player_trust_level,
    player_interaction_count,
    player_escalation_state,
)
from ui.theme import tcol


class _AttrEditor:
    def __init__(self, app, path: Path, data: dict,
                 on_save: Callable[[Path, Dict[str, Any]], None]):
        self.app = app
        self.path = path
        self.data = data or {}
        self.on_save = on_save

        self._orig_romance = float(player_romance_level(self.data))
        self._orig_trust = float(player_trust_level(self.data))
        self._orig_inter = float(player_interaction_count(self.data))
        self._orig_eligible = bool(self.data.get("IsRomanceEligible", False))
        li = self.data.get("LastInteractionTimeDays")
        try:
            self._orig_li = float(li) if li is not None else -1.0
        except (TypeError, ValueError):
            self._orig_li = -1.0
        self._never_interacted = self._orig_li < 0

        self._build()

    def _build(self):
        win = tk.Toplevel(self.app.root)
        self.win = win
        name = self.data.get("Name") or self.path.stem
        win.title(tr("編輯屬性") + f" — {name}")
        win.transient(self.app.root)
        win.grab_set()
        # Wide enough that the 最後互動 date preview never clips — even with the
        # longer English month/season labels.
        center_window(win, 640, 430)

        # Header
        ttk.Label(win, text=name, font=("Microsoft JhengHei", 13, "bold"),
                  foreground=tcol("#1A3A5C")).pack(anchor="w", padx=14, pady=(12, 0))
        ttk.Label(win, text=f"ID：{self.data.get('StringId') or ''}",
                  foreground=tcol("#9A9A9A")).pack(anchor="w", padx=14, pady=(0, 8))
        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=12)

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=16, pady=10)
        body.columnconfigure(1, weight=1)
        self._err = tk.StringVar(value="")
        self._syncing = False   # guards slider ↔ entry two-way updates
        r = 0

        # 允許浪漫 (IsRomanceEligible) — above 浪漫; auto-enables when a positive
        # romance value is entered on a not-yet-eligible character.
        self._eligible_var = tk.BooleanVar(value=self._orig_eligible)
        ttk.Label(body, text=tr("允許浪漫"), font=("Microsoft JhengHei", 10, "bold"),
                  foreground=tcol("#6B5B3E")).grid(row=r, column=0, sticky="w", pady=4)
        ttk.Checkbutton(body, variable=self._eligible_var).grid(
            row=r, column=1, sticky="w", pady=4)
        r += 1

        # 浪漫 / 信任 / 互動 — editable numeric entries (mod-defined ranges)
        self._romance_var = tk.StringVar(value=_fmt(self._orig_romance))
        self._trust_var = tk.StringVar(value=_fmt(self._orig_trust))
        self._inter_var = tk.StringVar(value=_fmt(self._orig_inter))
        self._e_romance = self._num_row(body, r, tr("浪漫"), self._romance_var,
                                        lo=0.0, hi=100.0, hint=tr("0～100"),
                                        slider=True); r += 1
        self._e_trust = self._num_row(body, r, tr("信任"), self._trust_var,
                                      lo=0.0, hi=1.0, hint=tr("0～1"),
                                      slider=True); r += 1

        # Entering a positive romance auto-enables 允許浪漫 (never auto-disables).
        self._romance_var.trace_add("write", lambda *_: self._maybe_enable_romance())

        # 關係 — read-only (real game relation value)
        rel = 0
        pr = self.data.get("PlayerRelation")
        if isinstance(pr, dict):
            rel = pr.get("Value", 0)
        self._ro_row(body, r, tr("關係"), _fmt(rel),
                     hint=tr("遊戲真實關係值，不可於此編輯")); r += 1

        self._e_inter = self._num_row(body, r, tr("互動"), self._inter_var,
                                      integer=True, hint=tr("與玩家的互動次數")); r += 1

        # 最後互動時間 — GameDateField (Q1: editable)
        ttk.Label(body, text=tr("最後互動"), font=("Microsoft JhengHei", 10, "bold"),
                  foreground=tcol("#6B5B3E")).grid(row=r, column=0, sticky="nw", pady=(8, 2))
        li_wrap = ttk.Frame(body)
        li_wrap.grid(row=r, column=1, sticky="w", pady=(8, 2))
        self._li_enable_var = tk.BooleanVar(value=not self._never_interacted)
        if self._never_interacted:
            ttk.Checkbutton(li_wrap, text=tr("設定最後互動時間（標記為已互動）"),
                            variable=self._li_enable_var).pack(anchor="w")
        self._li_field = GameDateField(li_wrap, max(0.0, self._orig_li), show_raw=False)
        self._li_field.frame.pack(anchor="w", pady=(2, 0))
        r += 1

        # 情緒升降 — read-only (AI-managed)
        esc = player_escalation_state(self.data).strip() or "neutral"
        self._ro_row(body, r, tr("情緒升降"), esc,
                     hint=tr("AI 自行管理，僅供檢視")); r += 1

        # Footer
        ttk.Label(win, textvariable=self._err, foreground=tcol("#C0392B")).pack(
            anchor="w", padx=16)
        foot = ttk.Frame(win)
        foot.pack(fill="x", padx=12, pady=(4, 10), side=tk.BOTTOM)
        ttk.Button(foot, text=tr("儲存"), command=self._save,
                   style="success.TButton").pack(side=tk.RIGHT, padx=4)
        ttk.Button(foot, text=tr("取消"), command=win.destroy,
                   style="secondary.TButton").pack(side=tk.RIGHT, padx=4)

    def _num_row(self, parent, row, label, var, *, integer=False,
                 lo=None, hi=None, hint="", slider=False):
        ttk.Label(parent, text=label, font=("Microsoft JhengHei", 10, "bold"),
                  foreground=tcol("#6B5B3E")).grid(row=row, column=0, sticky="w", pady=4)
        cell = ttk.Frame(parent)
        cell.grid(row=row, column=1, sticky="w", pady=4)
        scale = None
        if slider and lo is not None and hi is not None:
            scale = ttk.Scale(cell, from_=lo, to=hi, orient="horizontal",
                              length=170)
            scale.pack(side=tk.LEFT, padx=(0, 8))
        # Narrower than before — these numbers need only a few characters, and a
        # slider now covers coarse adjustment (浪漫 / 信任).
        e = ttk.Entry(cell, textvariable=var, width=8)
        e.pack(side=tk.LEFT)
        e._is_integer = integer
        e._lo = lo
        e._hi = hi
        e._scale = scale
        if scale is not None:
            try:
                scale.set(float(var.get()))
            except (TypeError, ValueError):
                pass
            # Wire AFTER the initial set() so it doesn't fire a spurious sync.
            scale.configure(command=lambda v, en=e, va=var: self._on_slide(en, va, v))
            var.trace_add("write",
                          lambda *_a, en=e, va=var: self._on_entry_change(en, va))
        if hint:
            ttk.Label(cell, text=f"  （{hint}）", foreground=tcol("#999999"),
                      font=("Microsoft JhengHei", 9)).pack(side=tk.LEFT)
        return e

    def _on_slide(self, entry, var, raw):
        """Slider dragged → write the entry (guarded against the echo trace)."""
        if self._syncing:
            return
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return
        self._syncing = True
        try:
            if getattr(entry, "_is_integer", False):
                var.set(str(int(round(val))))
            elif entry._hi is not None and entry._hi <= 1.0:
                var.set(f"{val:.2f}")     # 信任 (0–1): keep 2 decimals
            else:
                var.set(str(int(round(val))))   # 浪漫 (0–100): whole numbers
        finally:
            self._syncing = False

    def _on_entry_change(self, entry, var):
        """Entry typed → move the slider (only when parseable & in range)."""
        if self._syncing:
            return
        scale = getattr(entry, "_scale", None)
        if scale is None:
            return
        try:
            val = float(var.get().strip())
        except (TypeError, ValueError):
            return
        lo, hi = entry._lo, entry._hi
        if (lo is not None and val < lo) or (hi is not None and val > hi):
            return
        self._syncing = True
        try:
            scale.set(val)
        finally:
            self._syncing = False

    def _maybe_enable_romance(self):
        """Auto-check 允許浪漫 when a positive romance is typed (never auto-uncheck)."""
        try:
            if float(self._romance_var.get().strip()) > 0 and not self._eligible_var.get():
                self._eligible_var.set(True)
        except (TypeError, ValueError):
            pass

    def _ro_row(self, parent, row, label, value, *, hint=""):
        ttk.Label(parent, text=label, font=("Microsoft JhengHei", 10, "bold"),
                  foreground=tcol("#6B5B3E")).grid(row=row, column=0, sticky="w", pady=4)
        cell = ttk.Frame(parent)
        cell.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Label(cell, text=str(value), foreground=tcol("#333333")).pack(side=tk.LEFT)
        if hint:
            ttk.Label(cell, text=f"  （{hint}）", foreground=tcol("#999999"),
                      font=("Microsoft JhengHei", 9)).pack(side=tk.LEFT)

    # ── save ──────────────────────────────────────────────────────────
    def _parse(self, entry, var, integer):
        raw = var.get().strip()
        try:
            val = float(raw)
        except (TypeError, ValueError):
            entry.configure(foreground=tcol("#C0392B"))
            raise ValueError(tr("數值格式不正確"))
        lo, hi = getattr(entry, "_lo", None), getattr(entry, "_hi", None)
        if (lo is not None and val < lo) or (hi is not None and val > hi):
            entry.configure(foreground=tcol("#C0392B"))
            raise ValueError(tr("數值超出範圍 {lo}～{hi}").format(lo=_fmt(lo), hi=_fmt(hi)))
        entry.configure(foreground=tcol("#000000"))
        return int(round(val)) if integer else val

    def _save(self):
        try:
            romance = self._parse(self._e_romance, self._romance_var, False)
            trust = self._parse(self._e_trust, self._trust_var, False)
            inter = self._parse(self._e_inter, self._inter_var, True)
        except ValueError as exc:
            self._err.set(str(exc))
            return

        changes: Dict[str, Any] = {}
        if romance != self._orig_romance:
            changes["romance"] = romance
        if trust != self._orig_trust:
            changes["trust"] = trust
        if inter != int(round(self._orig_inter)):
            changes["interaction"] = inter
        # 允許浪漫: honour the (possibly auto-checked) toggle.
        if self._eligible_var.get() != self._orig_eligible:
            changes["romance_eligible"] = self._eligible_var.get()
        # Last-interaction: only when enabled (never-interacted needs the checkbox)
        if self._li_enable_var.get():
            try:
                li = self._li_field.get()
            except (ValueError, tk.TclError):
                self._err.set(tr("最後互動時間格式不正確"))
                return
            if li != self._orig_li:
                changes["last_interaction"] = li

        if not changes:
            self.win.destroy()
            return
        self.win.destroy()
        self.on_save(self.path, changes)


def _fmt(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}"


def open_attr_editor(app, path, data, on_save) -> None:
    _AttrEditor(app, Path(path), data, on_save)
