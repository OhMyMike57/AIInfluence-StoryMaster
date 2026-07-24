"""Name↔ID autocomplete field (M3 — terminology linkage).

Lets the user type a *name* (e.g. settlement "鄧葛蘭尼") instead of a game id
("town_B2").  As they type, a status label shows the resolved id.

Two presentation modes:

* **default** (``autocomplete=False``) — a ``ttk.Combobox`` whose values update
  as you type; the user opens the dropdown manually with the arrow.
* **autocomplete** (``autocomplete=True``) — a plain entry with a live results
  list that **auto-expands and filters as you type** (a click or ↑/↓+Enter
  picks).  This is far more discoverable: the user immediately sees that typing
  a keyword narrows the character/settlement list, without knowing in advance
  that the field is searchable.

The widget is data-source-agnostic: it calls three methods on *app* (provided by
the main application, backed by the companion-mod terminology library):

    app.terminology_suggest(category, prefix, limit) -> [(id, name), ...]
    app.resolve_name_or_id(category, text)           -> (resolved_id|None, [candidates])
    app.terminology_name_for(category, id)           -> display name

``get_id()`` returns the resolved id, or the raw text when it can't be resolved
(so user input — e.g. a modded id not in the library — is never silently lost).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from i18n import tr
from ui.theme import tcol


class NameIdCombo(ttk.Frame):
    def __init__(self, parent, app, category, *, initial_id: str = "",
                 width: int = 22, allow_empty: bool = True,
                 autocomplete: bool = False, popup_rows: int = 8, **kw):
        super().__init__(parent, **kw)
        self.app = app
        self.category = category
        self.allow_empty = allow_empty
        self.autocomplete = autocomplete
        self._popup_rows = popup_rows
        self._suppress = False

        self.var = tk.StringVar()
        if autocomplete:
            # Plain entry — the live results list replaces the native popdown.
            self.combo = ttk.Entry(self, textvariable=self.var, width=width)
        else:
            self.combo = ttk.Combobox(self, textvariable=self.var, width=width, state="normal")
        self.combo.pack(side=tk.LEFT)
        self._status = ttk.Label(self, text="", foreground=tcol("#888888"))
        self._status.pack(side=tk.LEFT, padx=(4, 0))

        # Autocomplete popup state (created lazily on first keystroke).
        self._popup = None
        self._popup_lb = None
        self._popup_ids: list = []
        self._hide_after_id = None

        self.set_id(initial_id)

        self.combo.bind("<KeyRelease>", self._on_key)
        if not autocomplete:
            self.combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_status())
        self.combo.bind("<FocusOut>", self._on_focus_out)
        if autocomplete:
            self.combo.bind("<Down>", self._nav_down)
            self.combo.bind("<Up>", self._nav_up)
            self.combo.bind("<Return>", self._nav_return)
            self.combo.bind("<Escape>", self._nav_escape)
            self.bind("<Destroy>", lambda e: self._destroy_popup())

    # ── formatting ────────────────────────────────────────────────────
    @staticmethod
    def _fmt(id_: str, name: str) -> str:
        return f"{name} ({id_})" if name and name != id_ else str(id_)

    # ── public API ────────────────────────────────────────────────────
    def set_id(self, id_: str) -> None:
        """Set the field from a game id (shown as ``name (id)``)."""
        self._suppress = True
        try:
            id_ = str(id_ or "")
            if id_:
                self.var.set(self._fmt(id_, self.app.terminology_name_for(self.category, id_)))
            else:
                self.var.set("")
        finally:
            self._suppress = False
        self._refresh_status()

    def get_id(self) -> str:
        """Resolve the current text to a game id (raw text when unresolved)."""
        text = self.var.get().strip()
        if not text:
            return ""
        rid, _cands = self.app.resolve_name_or_id(self.category, text)
        return rid if rid else text

    def set_category(self, category: str) -> None:
        """Switch the resolution category, preserving the current id."""
        if category == self.category:
            return
        cur = self.get_id()
        self.category = category
        self.set_id(cur)

    def set_state(self, state: str) -> None:
        """Enable ('normal'/'readonly') or disable ('disabled') the field."""
        try:
            self.combo.configure(state=state)
            self._status.configure(foreground=tcol("#888888") if state == "disabled" else self._status.cget("foreground"))
        except Exception:
            pass

    def is_resolved(self) -> bool:
        text = self.var.get().strip()
        if not text:
            return self.allow_empty
        rid, _ = self.app.resolve_name_or_id(self.category, text)
        return rid is not None

    # ── internals ─────────────────────────────────────────────────────
    def _on_key(self, event) -> None:
        if self._suppress:
            return
        if event.keysym in ("Up", "Down", "Return", "Tab", "Left", "Right", "Escape"):
            return
        if self.autocomplete:
            self._show_suggestions()
        else:
            prefix = self.var.get().strip()
            try:
                sugg = self.app.terminology_suggest(self.category, prefix, 40)
                self.combo["values"] = [self._fmt(i, n) for i, n in sugg]
            except Exception:
                pass
        self._refresh_status()

    def _refresh_status(self) -> None:
        try:
            text = self.var.get().strip()
            if not text:
                self._status.configure(text="", foreground=tcol("#888888"))
                return
            rid, cands = self.app.resolve_name_or_id(self.category, text)
            if rid:
                self._status.configure(text="→ " + rid, foreground=tcol("#1F9D55"))
            elif len(cands) > 1:
                self._status.configure(text=tr("⚠ {v0} 筆同名，請從清單選").format(v0=len(cands)),
                                       foreground=tcol("#E67E22"))
            else:
                self._status.configure(text=tr("⚠ 未知 id"), foreground=tcol("#C0392B"))
        except Exception:
            pass

    # ── autocomplete popup ────────────────────────────────────────────
    def _ensure_popup(self) -> None:
        if self._popup is not None:
            return
        top = tk.Toplevel(self)
        top.wm_overrideredirect(True)
        try:
            top.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        lb = tk.Listbox(top, exportselection=False, activestyle="none",
                        height=self._popup_rows, highlightthickness=1,
                        font=("Microsoft JhengHei", 10))
        lb.pack(fill="both", expand=True)
        lb.bind("<ButtonRelease-1>", self._on_popup_click)
        lb.bind("<Motion>", self._on_popup_motion)
        self._popup = top
        self._popup_lb = lb
        top.withdraw()

    def _cancel_pending_hide(self) -> None:
        if self._hide_after_id is not None:
            try:
                self.after_cancel(self._hide_after_id)
            except Exception:
                pass
            self._hide_after_id = None

    def _show_suggestions(self) -> None:
        self._cancel_pending_hide()
        prefix = self.var.get().strip()
        try:
            sugg = self.app.terminology_suggest(self.category, prefix, 50)
        except Exception:
            sugg = []
        self._ensure_popup()
        lb = self._popup_lb
        lb.delete(0, tk.END)
        self._popup_ids = []
        for i, n in sugg:
            lb.insert(tk.END, self._fmt(i, n))
            self._popup_ids.append(i)
        if not self._popup_ids:
            self._hide_popup()
            return
        lb.configure(height=min(self._popup_rows, lb.size()))
        self.update_idletasks()
        x = self.combo.winfo_rootx()
        y = self.combo.winfo_rooty() + self.combo.winfo_height()
        w = max(self.combo.winfo_width(), lb.winfo_reqwidth())
        h = lb.winfo_reqheight()
        self._popup.wm_geometry(f"{w}x{h}+{x}+{y}")
        self._popup.deiconify()
        self._popup.lift()

    def _hide_popup(self) -> None:
        if self._popup is not None:
            self._popup.withdraw()

    def _destroy_popup(self) -> None:
        self._cancel_pending_hide()
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

    def _popup_visible(self) -> bool:
        try:
            return self._popup is not None and self._popup.state() == "normal"
        except Exception:
            return False

    def _move_sel(self, delta: int) -> None:
        lb = self._popup_lb
        if lb is None or lb.size() == 0:
            return
        cur = lb.curselection()
        i = (cur[0] if cur else -1) + delta
        i = max(0, min(lb.size() - 1, i))
        lb.selection_clear(0, tk.END)
        lb.selection_set(i)
        lb.see(i)

    def _accept(self, idx: int) -> None:
        if 0 <= idx < len(self._popup_ids):
            self.set_id(self._popup_ids[idx])
        self._hide_popup()
        self.combo.focus_set()
        try:
            self.combo.icursor(tk.END)
        except Exception:
            pass

    def _on_popup_click(self, event) -> None:
        self._cancel_pending_hide()
        self._accept(self._popup_lb.nearest(event.y))

    def _on_popup_motion(self, event) -> None:
        lb = self._popup_lb
        idx = lb.nearest(event.y)
        lb.selection_clear(0, tk.END)
        lb.selection_set(idx)

    def _nav_down(self, event):
        if not self._popup_visible():
            self._show_suggestions()
        else:
            self._move_sel(1)
        return "break"

    def _nav_up(self, event):
        if self._popup_visible():
            self._move_sel(-1)
            return "break"
        return None

    def _nav_return(self, event):
        if self._popup_visible():
            cur = self._popup_lb.curselection()
            self._accept(cur[0] if cur else 0)
            return "break"
        return None

    def _nav_escape(self, event):
        if self._popup_visible():
            self._hide_popup()
            return "break"
        return None

    def _on_focus_out(self, event) -> None:
        # Delay the hide so a click on the popup list registers first.
        if self.autocomplete:
            self._cancel_pending_hide()
            self._hide_after_id = self.after(160, self._hide_popup)
        self._refresh_status()
