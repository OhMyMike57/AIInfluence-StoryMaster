"""Reader-controlled font size for the preview panes.

The editor's default type size suits dense forms, but the preview panes are
where people actually *read* — a long conversation, a persona, a secret.  In
game those texts are cramped by the HUD, so this tool ends up being how players
re-read their story, and 10pt across a wide pane is tiring.

Rather than enlarge the whole UI (which would break carefully sized forms), every
preview registers here and one preference shifts them together — set in
設定 → 偏好設定 → 預覽字體設定, which previews the change live.

Registration snapshots the widget's own font *and* every tag font it has
configured, so a heading tag keeps its relative weight when everything scales.
Register after the tags are configured.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Dict, List, Optional, Tuple

SETTINGS_KEY = "preview_font_delta"
MIN_DELTA, MAX_DELTA = 0, 7
# +2 by default: the form-sized 10pt is tiring across a wide preview, and this
# tool is where people re-read their story (in game the HUD crowds the text).
DEFAULT_DELTA = 2

# (widget, base widget font, {tag: base font}) for every live preview.
_registry: List[Tuple[tk.Text, Optional[tuple], Dict[str, tuple]]] = []
_delta = 0
_labels: List[tk.Widget] = []


def _spec(value: Any) -> Optional[tuple]:
    """Normalise any Tk font value to ``(family, size, *styles)``.

    Goes through ``tkfont.Font(font=…)`` rather than splitting the string: Tk
    reports a multi-word family brace-quoted (``{Microsoft JhengHei} 10``), so
    naive splitting reads the family as the size and silently gives up — which
    is exactly how this scaled nothing at all the first time.
    """
    if not value:
        return None
    try:
        f = tkfont.Font(font=value)
        family = f.actual("family")
        size = int(f.actual("size"))
        styles = []
        if f.actual("weight") == "bold":
            styles.append("bold")
        if f.actual("slant") == "italic":
            styles.append("italic")
        if not family:
            return None
        return (family, size) + tuple(styles)
    except Exception:
        return None


def _scaled(base: Optional[tuple], delta: int) -> Optional[tuple]:
    if not base:
        return None
    family, size = base[0], base[1]
    # Preserve the sign convention: negative sizes are pixels in Tk.
    new = size + delta if size >= 0 else size - delta
    if size >= 0:
        new = max(6, new)
    return (family, new) + tuple(base[2:])


def current_delta() -> int:
    return _delta


def load(app) -> None:
    """Read the saved delta (call once at startup, before previews register)."""
    global _delta
    try:
        raw = app.settings.get(SETTINGS_KEY, None)
        value = DEFAULT_DELTA if raw is None else int(raw)
        _delta = max(MIN_DELTA, min(MAX_DELTA, value))
    except Exception:
        _delta = DEFAULT_DELTA


def register(widget: tk.Text) -> None:
    """Register a preview Text (after its tags are configured)."""
    try:
        base = _spec(widget.cget("font"))
        tags: Dict[str, tuple] = {}
        for name in widget.tag_names():
            spec = _spec(widget.tag_cget(name, "font"))
            if spec:
                tags[name] = spec
        _registry.append((widget, base, tags))
        _apply_one(widget, base, tags)
    except tk.TclError:
        pass


def _apply_one(widget, base, tags) -> None:
    try:
        if not widget.winfo_exists():
            return
        scaled = _scaled(base, _delta)
        if scaled:
            widget.configure(font=scaled)
        for name, spec in tags.items():
            s = _scaled(spec, _delta)
            if s:
                widget.tag_configure(name, font=s)
    except tk.TclError:
        pass


def apply_all() -> None:
    """Re-apply the current delta to every live preview; drop dead ones."""
    alive = []
    for widget, base, tags in _registry:
        try:
            if not widget.winfo_exists():
                continue
        except tk.TclError:
            continue
        alive.append((widget, base, tags))
        _apply_one(widget, base, tags)
    _registry[:] = alive
    for lbl in list(_labels):
        try:
            if lbl.winfo_exists():
                lbl.configure(text=delta_text())
            else:
                _labels.remove(lbl)
        except tk.TclError:
            _labels.remove(lbl)


def delta_text() -> str:
    return f"+{_delta}" if _delta else "0"


def set_delta(app, value: int) -> None:
    global _delta
    _delta = max(MIN_DELTA, min(MAX_DELTA, int(value)))
    try:
        app.settings[SETTINGS_KEY] = _delta
        app.save_settings()
    except Exception:
        pass
    apply_all()
