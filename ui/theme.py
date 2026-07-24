"""Centralized ttkbootstrap theme configuration and helpers.

Usage::

    from ui.theme import setup_appearance, labeled_frame
    setup_appearance(root)          # call once after creating Window
    frm = labeled_frame(parent, text="Section Title")
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


# ── Dual-mode colour system (v0.39.0) ─────────────────────────────────────
#
# The whole UI historically hard-coded light-mode hex colours.  Rather than
# rename them all to semantic tokens (risky for the working light theme), we
# keep the *light* value as the canonical key and map it to a dark counterpart
# only when dark mode is active.  ``tcol("#hex")`` therefore returns the input
# UNCHANGED in light mode — so light mode is pixel-identical to pre-v0.39 — and
# the mapped value in dark mode.  Unmapped colours fall through unchanged.
#
# The two bundled themes: 明亮 = Sandstone (light), 黑夜 = Darkly (dark).

DARK_THEMES = {"darkly"}          # ttkbootstrap themes that are "dark"
LIGHT_THEME = "sandstone"
DARK_THEME = "darkly"

# light hex → dark hex.  Grouped by role; light keys are lower-case.
DARK_MAP = {
    # ── surfaces / backgrounds (light → dark) ──
    "#ffffff": "#2b2b2b", "#fff7e0": "#3a3423", "#f6f4ee": "#302e2a",
    "#f5f2ea": "#302e29", "#efeae0": "#2e2c27", "#e7f1ff": "#202b3a",
    "#e2e2e2": "#3a3a3a",
    # ── near-black text → near-white ──
    "#000000": "#e8e8e8", "#111111": "#e4e4e4", "#222222": "#dedede",
    "#333333": "#d2d2d2", "#3a3a3a": "#c9c9c9", "#444444": "#bcbcbc",
    # ── mid greys (muted / secondary text) ──
    "#555555": "#a8a8a8", "#5a5a5a": "#acacac", "#666666": "#a2a2a2",
    "#777777": "#9a9a9a", "#808080": "#969696", "#888888": "#9c9c9c",
    "#909090": "#9c9c9c", "#999999": "#909090", "#9a9a9a": "#8e8e8e",
    "#9aa0a6": "#888e94", "#aaaaaa": "#7f7f7f",
    # ── borders (light grey → dark grey) ──
    "#b8b8b8": "#4a4a4a", "#bbbbbb": "#4a4a4a", "#c4c4c4": "#464646",
    "#cccccc": "#464646", "#dddddd": "#404040",
    # ── headings (navy → light blue) ──
    "#1a3a5c": "#9fc0e6",
    # ── captions / tan (brown → light tan) ──
    "#6b5b3e": "#c8b590", "#7b5b2e": "#ccb485", "#8a7a5a": "#cabfa0",
    "#5d4037": "#bcaab4",   # no-speaker plain-text conversation lines
    # ── danger (red — brighten for dark bg) ──
    "#c0392b": "#e74c3c", "#c94a2c": "#e86a4e", "#dc3545": "#e8515f",
    "#a31515": "#e05a5a", "#8e1010": "#dc5555",
    # ── success (green — brighten for contrast) ──
    "#27ae60": "#2ecc71", "#1a7a3f": "#3ecf7f", "#1a8a4a": "#3ed085",
    "#2d6a4f": "#52b98c", "#1f9d55": "#38d278", "#1a9a6c": "#38d29a",
    "#16a34a": "#33d06e", "#098658": "#35c592", "#1f6fb2": "#5aace6",
    # ── warning / orange (brighten dark ones) ──
    "#e67e22": "#ec9350", "#a15c00": "#d9954a", "#a04000": "#d97740",
    "#b5852e": "#d3a552", "#b36b00": "#db9848", "#b26b00": "#db9848",
    "#d97706": "#ea9a46", "#d4ac0d": "#e2c743", "#d35400": "#e5733a",
    "#7d6608": "#d0b040", "#7b5010": "#d0a860",
    # ── accent / links (blue — brighten) ──
    "#1a6fa0": "#5aace6", "#2471a3": "#5aace6", "#1a5276": "#5aa0d8",
    "#5b7fa6": "#8fb4dd", "#0b5ed7": "#5b9bff", "#0451a5": "#5b9bff",
    "#0000ff": "#6d8fff", "#5d6d7e": "#9aa9b8",
    # ── purple ──
    "#884ea0": "#b47fd0", "#7b3f98": "#b47fd0",
    # ── gold (highlight / selection) ──
    "#c49a2d": "#d6b24f",
    # ── 對話歷史 line categories (v1.1.0 rework) ──
    # One colour per line type AI Influence writes.  Dark values are lifted to
    # ~300-level tints so they stay legible on the #2b2b2b list surface while
    # keeping the same hue relationship as the light set.
    "#1565c0": "#64b5f6",   # player
    "#2e7d32": "#81c784",   # the character themself
    "#00695c": "#4db6ac",   # other named characters
    "#6a1b9a": "#ce93d8",   # story tags
    "#b26a00": "#ffb74d",   # overheard
    "#c62828": "#ef9a9a",   # battle shouts
    "#4527a0": "#b39ddb",   # legacy long-term memory
    "#9e9e9e": "#8f8f8f",   # gap notices
    # ── Tk named colours (speaker_color / log tags / hint labels) ──
    # These evade hex-literal migration; tcol() lowercases input so they map
    # here.  Dark values are brightened for contrast on the #2b2b2b surfaces.
    "blue":      "#6db3f2",   # player lines
    "green":     "#4fd07f",   # current NPC (me) / success
    "darkgreen": "#9ecfa4",   # other known speakers (bulk of dialogue text)
    "purple":    "#c39bd3",   # [tag] speakers (e.g. [劇情記憶])
    "red":       "#f28b82",   # unknown speaker / error
    "gray":      "#9c9c9c",   # hints / line numbers
    "grey":      "#9c9c9c",
    "yellow":    "#6b5d1e",   # log-search highlight *background* (dim amber)
}

_MODE = "light"   # "light" | "dark"; set once at startup via set_mode()


def set_mode(mode: str) -> None:
    """Set the active colour mode. Call before building widgets."""
    global _MODE
    _MODE = "dark" if mode == "dark" else "light"


def mode() -> str:
    return _MODE


def is_dark() -> bool:
    return _MODE == "dark"


def theme_mode(theme_name: str) -> str:
    """'dark' if *theme_name* is a dark ttkbootstrap theme, else 'light'."""
    return "dark" if theme_name in DARK_THEMES else "light"


# Legacy ttkbootstrap themes that were offered before v0.39.0 reduced the list
# to two — used to migrate a saved dark theme to 黑夜 rather than forcing light.
_LEGACY_DARK = {"darkly", "solar", "cyborg", "superhero", "vapor", "slate", "cosmo-dark"}


def normalize_theme(name: str) -> str:
    """Map any saved theme name onto one of the two bundled themes."""
    if name in (LIGHT_THEME, DARK_THEME):
        return name
    return DARK_THEME if name in _LEGACY_DARK else LIGHT_THEME


def tcol(hexcolor: str) -> str:
    """Return the themed colour for the active mode (name: *t*heme *col*our).

    Light mode returns *hexcolor* unchanged (pixel-identical to pre-v0.39).
    Dark mode maps via :data:`DARK_MAP`; unmapped colours pass through.
    Non-hex inputs (named colours like ``"gray"``) are also mapped when a
    dark counterpart is registered, otherwise returned unchanged.
    """
    if _MODE != "dark":
        return hexcolor
    return DARK_MAP.get((hexcolor or "").lower(), hexcolor)


def paint(widget, **colours):
    """Apply colour options to a raw ``tk`` widget so they actually stick.

    **Do not pass bg/fg to a tk widget's constructor in this app.**  Under
    ``ttkbootstrap.Window`` the theme re-applies its own widget defaults while
    the widget is being instantiated, so constructor colour options are silently
    discarded — ``tk.Frame(parent, bg="#B8B8B8").cget("bg")`` comes back as the
    surface colour.  A ``configure()`` *after* creation survives, which is what
    this helper does.

    Verified: identical code under a plain ``tk.Tk()`` keeps ``#B8B8B8``.
    Symptoms of getting this wrong are invisible-but-present widgets — popover
    menu separators and the persona editor's drag handles both rendered in the
    background colour until they were repainted this way.

    ttk widgets are unaffected (they colour via styles, not the option DB).

    Usage::

        sep = paint(tk.Frame(parent, height=1), bg=tcol("#B8B8B8"))
    """
    try:
        widget.configure(**colours)
    except tk.TclError:
        pass
    return widget


def apply_tk_widget_defaults(root) -> None:
    """Theme the non-ttk widgets (tk.Text/Listbox/Canvas) that ttkbootstrap
    does not style, in dark mode.  Uses the option database so widgets that
    don't set their own bg/fg pick up the dark surface colours.  A no-op in
    light mode so the light theme stays pixel-identical to pre-v0.39."""
    if _MODE != "dark":
        return
    bg = tcol("#ffffff")
    fg = tcol("#222222")
    sel_bg = tcol("#c49a2d")
    for w in ("Text", "Listbox", "Canvas"):
        root.option_add(f"*{w}.background", bg)
        root.option_add(f"*{w}.foreground", fg)
    root.option_add("*Text.insertBackground", fg)
    root.option_add("*Listbox.selectBackground", sel_bg)
    root.option_add("*Text.selectBackground", sel_bg)


def setup_appearance() -> None:
    """No-op — theme is applied at Window creation time via ttkbootstrap."""
    pass


# ── Widget helpers ────────────────────────────────────────────────────────

def labeled_frame(parent, text: str = "", **kwargs) -> ttk.LabelFrame:
    """Return a ttk.LabelFrame (native bordered section with title)."""
    return ttk.LabelFrame(parent, text=text, **kwargs)


def make_scrollable(parent) -> tuple:
    """Create a Canvas-based scrollable area.

    Returns (outer_frame, inner_frame).
    Pack/grid *outer_frame* into the layout; add children to *inner_frame*.
    """
    outer = ttk.Frame(parent)
    canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
    vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)

    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(e):
        canvas.itemconfig(win_id, width=e.width)

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)
    canvas.configure(yscrollcommand=vsb.set)

    def _on_mousewheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    # Capture mousewheel for all widgets inside the canvas when mouse hovers over it
    def _on_enter(e):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _on_leave(e):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _on_enter)
    canvas.bind("<Leave>", _on_leave)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    # Expose canvas on outer so callers can reset scroll position after reload
    outer.canvas = canvas  # type: ignore[attr-defined]

    return outer, inner
