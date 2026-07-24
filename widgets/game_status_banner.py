"""Game-status banner widget.

Displays a compact, colour-coded status strip that tells the user whether
Bannerlord is running, whether the tool's campaign matches the one loaded
in-game, and context-appropriate workflow guidance.

Layout (single row, full-width)::

    [ 🎮 遊戲未啟動 ]  ·  [✔ 戰役匹配]  ·  指引文字 …  ·  (檢查: HH:MM:SS)

The middle "match" pill only appears when the connector heartbeat is fresh
(so we actually know the in-game campaign); otherwise it is hidden and the
banner reads ``[狀態] · 指引``.

Colours:
    ⚙️ 已載入戰役   — amber/orange background (campaign detected, editing risky)
    🎮 遊戲啟動中   — green background (game up, no campaign detected)
    🎮 遊戲未啟動   — light grey (safe to edit)
    ❓ 狀態未知      — dark grey (psutil unavailable)
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple

from i18n import tr
from ui.theme import is_dark


# ── Colour palette ────────────────────────────────────────────────────────
# The banner draws its OWN backgrounds, so the vivid alert states (amber/green/
# red) stay as-is in both modes — only the neutral grey states need a dark
# variant (a light-grey banner on a dark theme looks out of place).

_PALETTE = {
    # state key: (frame_bg, status_fg, status_font_weight)
    "campaign_active": ("#E67E22", "#FFFFFF", "bold"),   # amber — editing risky
    "main_menu":       ("#1F9D55", "#FFFFFF", "bold"),   # green — safe to edit (precise)
    "running":         ("#27AE60", "#FFFFFF", "bold"),   # green — game up, state unknown
    "not_running":     ("#CCCCCC", "#333333", "normal"), # light grey
    "unknown":         ("#555555", "#DDDDDD", "normal"), # dark grey (psutil N/A)
    "warn_mod":        ("#E67E22", "#FFFFFF", "bold"),   # amber — companion mod missing
    "warn_path":       ("#C0392B", "#FFFFFF", "bold"),   # red — game/campaign path unset
}

# Dark mode: keep the vivid alert states, darken only the neutral greys.
_PALETTE_DARK = dict(_PALETTE)
_PALETTE_DARK["not_running"] = ("#3a3a3a", "#d0d0d0", "normal")
_PALETTE_DARK["unknown"]     = ("#333333", "#c8c8c8", "normal")


def _palette() -> dict:
    return _PALETTE_DARK if is_dark() else _PALETTE


# Built as functions (not module-level dicts) so the tr() literals are picked up
# by the i18n coverage checker and re-evaluated per call for the active language.
# Unified "遊戲狀態：X" left-segment text.
def _status_text(key: str) -> str:
    return {
        "campaign_active": tr("🎮 遊戲狀態：戰役中"),
        "main_menu":       tr("🎮 遊戲狀態：主選單"),
        "running":         tr("🎮 遊戲狀態：執行中"),
        "not_running":     tr("🎮 遊戲狀態：未啟動"),
        "unknown":         tr("❓ 遊戲狀態：未知"),
    }.get(key, tr("❓ 遊戲狀態：未知"))


# Guide shown when there is no fresh heartbeat (the match pill is hidden, so the
# guide falls back to a game-state-based hint). With a fresh heartbeat the guide
# comes from _match_state instead.
def _guide_text(key: str) -> str:
    return {
        "campaign_active": tr("請先退出回到主選單再編輯，否則變更會被遊戲覆寫"),
        "main_menu":       tr("目前在主選單，可安全編輯，存檔後載入戰役即生效"),
        "running":         tr("編輯完成後驗證 JSON 再載入存檔"),
        "not_running":     tr("編輯完成後驗證 JSON 再載入存檔"),
        "unknown":         tr("無法偵測遊戲狀態（psutil 未安裝）"),
    }.get(key, "")


def _state_key(status) -> str:
    """Map a :class:`~services.game_status_service.GameStatus` to a palette key."""
    if status is None:
        return "unknown"
    # Precise state from the companion-mod heartbeat takes priority.
    st = getattr(status, "state", None)
    if getattr(status, "heartbeat_fresh", False) and st:
        if st == "main_menu":
            return "main_menu"
        if st in ("in_campaign", "paused"):
            return "campaign_active"
    # Fallback: export-mtime heuristic + psutil.
    if status.campaign_active:
        return "campaign_active"
    running = status.running
    if running is None:
        return "unknown"
    return "running" if running else "not_running"


def _match_state(status, tool_campaign_id: Optional[str]) -> Optional[Tuple[str, str, bool]]:
    """Return ``(pill_text, guide_text, is_risky)`` describing *which* campaign
    the tool is editing relative to the game, or ``None`` when the pill should be
    hidden (no fresh heartbeat → we can't know the in-game campaign).

    Framed as "正在編輯：…" so the user always knows the edit target's safety:

    * game in a campaign, tool has the SAME one   → ⚠ editing the live campaign
      (risky: the game will overwrite it)
    * game in a campaign, tool has a DIFFERENT one → ✔ editing another campaign
    * main menu, tool has the LAST-PLAYED one      → ✔ editing the last-played
    * main menu, tool has some OTHER one            → ✔ editing another campaign
    """
    if status is None or not getattr(status, "heartbeat_fresh", False):
        return None
    st = getattr(status, "state", None)
    tool_cid = (tool_campaign_id or "").strip()
    if st in ("in_campaign", "paused"):
        game_cid = getattr(status, "campaign_id", None)
        if game_cid and tool_cid and game_cid == tool_cid:
            return (tr("⚠ 正在編輯：遊戲進行中的戰役"),
                    tr("⚠ 此戰役正在遊戲中進行，變更會被遊戲覆寫——請先退回主選單再編輯"),
                    True)
        return (tr("✔ 正在編輯：其他戰役"),
                tr("✔ 此戰役未在遊戲中載入，可安全編輯；下次於遊戲載入時生效"),
                False)
    if st == "main_menu":
        last_cid = getattr(status, "last_campaign_id", None)
        if last_cid and tool_cid and last_cid == tool_cid:
            return (tr("✔ 正在編輯：最後遊玩的戰役"),
                    tr("✔ 遊戲在主選單，此為最近遊玩的戰役，可安全編輯；重新載入後生效"),
                    False)
        return (tr("✔ 正在編輯：其他戰役"),
                tr("✔ 此戰役未在遊戲中載入，可安全編輯；下次於遊戲載入時生效"),
                False)
    return None


class GameStatusBanner(ttk.Frame):
    """A single-row, full-width banner that reflects the current game state.

    Usage::

        banner = GameStatusBanner(parent)
        banner.pack(fill=tk.X, padx=8, pady=(0, 4))
        # Later, on heartbeat:
        banner.update_status(game_status, tool_campaign_id=app._selected_campaign_id())
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)

        # Inner frame carries the background colour.
        self._inner = tk.Frame(self, bd=0, highlightthickness=0)
        self._inner.pack(fill=tk.X, ipady=3)

        self._status_var = tk.StringVar(value=_status_text("not_running"))
        self._match_var  = tk.StringVar(value="")
        self._guide_var  = tk.StringVar(value="")
        self._time_var   = tk.StringVar(value="")

        # Status pill label
        self._status_lbl = tk.Label(
            self._inner, textvariable=self._status_var,
            font=("", 9, "bold"), padx=8, pady=2, bd=0,
        )
        self._status_lbl.pack(side=tk.LEFT, padx=(6, 4))

        # Separator dot 1 (status ↔ rest) — always shown.
        self._sep1 = tk.Label(self._inner, text="·")
        self._sep1.pack(side=tk.LEFT)

        # Campaign-match pill + its trailing separator dot (packed on demand).
        self._match_lbl = tk.Label(
            self._inner, textvariable=self._match_var,
            font=("", 9, "bold"), padx=4, pady=2, bd=0,
        )
        self._match_sep = tk.Label(self._inner, text="·")

        # Guide text
        self._guide_lbl = tk.Label(
            self._inner, textvariable=self._guide_var,
            font=("", 9), padx=4, pady=2, bd=0,
        )
        self._guide_lbl.pack(side=tk.LEFT, padx=(4, 0))

        # Check-time label (right-aligned)
        self._time_lbl = tk.Label(
            self._inner, textvariable=self._time_var,
            font=("", 8), padx=6, bd=0,
        )
        self._time_lbl.pack(side=tk.RIGHT)

        self._match_shown = False
        # Initialise with default (not_running) appearance.
        self._apply_palette("not_running")

    # ── Public API ─────────────────────────────────────────────────────

    def update_status(self, status=None, tool_campaign_id: Optional[str] = None) -> None:
        """Refresh the banner from a :class:`~services.game_status_service.GameStatus`.

        Safe to call from the main thread inside a ``root.after`` callback.
        ``tool_campaign_id`` is the campaign id the tool currently has loaded,
        used to decide the match pill. Passing ``None`` status → "unknown".
        """
        key = _state_key(status)
        self._status_var.set(_status_text(key))

        match = _match_state(status, tool_campaign_id)
        self._set_match(match)

        # With a fresh heartbeat the guide is tied to the edit-target match;
        # otherwise fall back to a game-state-based hint.
        if match is not None:
            self._guide_var.set(match[1])
        else:
            self._guide_var.set(_guide_text(key))

        if status is not None and hasattr(status, "detected_at") and status.detected_at:
            self._time_var.set(tr("檢查：") + status.detected_at.strftime('%H:%M:%S'))
        else:
            self._time_var.set("")
        self._apply_palette(key)

    def show_warning(self, pill: str, message: str, key: str = "warn_mod") -> None:
        """Override the banner with a setup warning (mod missing / paths unset).

        Higher priority than game state — these block the tool's core features,
        so they replace the normal status until resolved.
        """
        self._status_var.set(pill)
        self._set_match(None)
        self._guide_var.set(message)
        self._time_var.set("")
        self._apply_palette(key if key in _palette() else "warn_mod")

    # ── Internal ───────────────────────────────────────────────────────

    def _set_match(self, match: Optional[Tuple] = None) -> None:
        """Show/hide the match pill (and its separator dot). *match* is the
        ``(pill, guide, is_risky)`` tuple from :func:`_match_state`, or ``None``."""
        if match is not None:
            self._match_var.set(match[0])
            if not self._match_shown:
                self._match_lbl.pack(side=tk.LEFT, before=self._guide_lbl)
                self._match_sep.pack(side=tk.LEFT, before=self._guide_lbl)
                self._match_shown = True
        else:
            self._match_var.set("")
            if self._match_shown:
                self._match_lbl.pack_forget()
                self._match_sep.pack_forget()
                self._match_shown = False

    def _apply_palette(self, key: str) -> None:
        pal = _palette()
        bg, fg, weight = pal.get(key, pal["unknown"])
        sep_fg = "#DDDDDD" if fg.upper() == "#FFFFFF" else "#888888"
        self._inner.configure(bg=bg)
        self._status_lbl.configure(bg=bg, fg=fg, font=("", 9, weight))
        self._match_lbl.configure(bg=bg, fg=fg)
        self._guide_lbl.configure(bg=bg, fg=fg)
        self._sep1.configure(bg=bg, fg=sep_fg)
        self._match_sep.configure(bg=bg, fg=sep_fg)
        self._time_lbl.configure(bg=bg, fg="#DDDDDD" if bg < "#888888" else "#666666")
