"""Themed, localized modal dialogs that stand in for tkinter's ``messagebox``
and ``simpledialog.askstring`` with **identical signatures and return values**.

Migration is import-only — ``from ui import msgbox as messagebox`` — so the
existing call sites stay byte-for-byte.  ``filedialog`` stays native (the OS
file picker is the right UX there).

Return-value contract (must match tkinter exactly so call sites don't change):
    showinfo/showwarning/showerror  -> "ok"   (Enter/Esc/✕ all close with "ok")
    askyesno                        -> True/False   (Esc/✕ == False)
    askokcancel                     -> True/False   (Esc/✕ == False)
    askstring                       -> str | None   (Cancel/Esc/✕ == None)

Design notes:
  * Buttons follow the tool-wide convention — 取消/否 left, 確定/是 right (D3) —
    with button text tr()-localized (the whole point over native messagebox,
    whose OS buttons can't be translated).  Initial focus is the confirm button.
  * Icon colour goes through ui.theme.tcol so it reads on both light and dark.
  * Long messages (a validity report can be dozens of lines) switch to a
    read-only scrolling Text; short ones use a wrapping Label.
  * Build / run are separated: the window is built in __init__; ``run()`` does
    ``wait_window``.  A ``_test_hook`` lets headless tests drive a button and
    read ``.result`` without entering the event loop.
  * No usable root at all (very early startup) -> fall back to native
    messagebox so nothing can dead-lock before the app window exists.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from i18n import tr
from ui.theme import tcol
from widgets.window_center import center_window

# icon glyph + light-mode colour (mapped through tcol at build time)
_ICONS = {
    "info":     ("ℹ", "#1A6FA0"),
    "warning":  ("⚠", "#B5852E"),
    "error":    ("⛔", "#C0392B"),
    "question": ("❓", "#1A6FA0"),
}

# Sentinel meaning "confirm pressed" for the askstring entry path.
_ENTRY_CONFIRM = object()

# Test hook: callable(dialog) -> None. When set, run() invokes it (to click a
# button) and returns immediately instead of blocking on wait_window.
_test_hook = None


def _long(message: str) -> bool:
    m = message or ""
    return m.count("\n") > 15 or len(m) > 1200


class _MessageDialog:
    """One modal dialog. ``.result`` holds the return value once finished."""

    def __init__(self, parent, kind, title, message, buttons, default_result,
                 *, entry=False, initialvalue="", show=None):
        self.result = default_result
        self._entry = entry
        self._entry_widget = None
        self._confirm_btn = None

        win = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
        self.win = win
        win.title(title or "")
        win.resizable(False, False)
        try:
            if parent is not None:
                win.transient(parent)
        except Exception:
            pass

        outer = ttk.Frame(win, padding=(18, 16, 18, 12))
        outer.pack(fill=tk.BOTH, expand=True)

        # ── icon + message row ────────────────────────────────────────────
        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True)
        glyph, colour = _ICONS.get(kind, _ICONS["info"])
        ttk.Label(body, text=glyph, foreground=tcol(colour),
                  font=("Segoe UI Emoji", 22)).pack(side=tk.LEFT, anchor="n", padx=(0, 14))

        msg = "" if message is None else str(message)
        if _long(msg):
            txt_wrap = ttk.Frame(body)
            txt_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            t = tk.Text(txt_wrap, wrap="word", width=62,
                        height=min(24, msg.count("\n") + 2), relief="flat",
                        highlightthickness=0)
            vsb = ttk.Scrollbar(txt_wrap, orient="vertical", command=t.yview)
            t.configure(yscrollcommand=vsb.set)
            t.insert("1.0", msg)
            t.configure(state="disabled")
            t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            ttk.Label(body, text=msg, wraplength=460, justify="left").pack(
                side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── optional entry (askstring) ────────────────────────────────────
        if entry:
            self._entry_widget = ttk.Entry(outer, width=40,
                                           show=(show if show else ""))
            if initialvalue:
                self._entry_widget.insert(0, initialvalue)
            self._entry_widget.pack(fill=tk.X, pady=(12, 0))

        # ── buttons (left→right visual order; pack side=RIGHT reversed) ────
        btnbar = ttk.Frame(outer)
        btnbar.pack(fill=tk.X, pady=(14, 0))
        widgets = []
        for label, value, is_confirm in buttons:   # label is pre-translated
            b = ttk.Button(
                btnbar, text=label, width=8,
                style=("success.TButton" if is_confirm else "secondary.TButton"),
                command=(lambda v=value: self._finish(v)),
            )
            widgets.append(b)
            if is_confirm:
                self._confirm_btn = b
        for b in reversed(widgets):
            b.pack(side=tk.RIGHT, padx=(6, 0))

        # ── focus + key bindings ──────────────────────────────────────────
        if entry:
            self._entry_widget.focus_set()
        elif self._confirm_btn is not None:
            self._confirm_btn.focus_set()
        win.bind("<Return>", self._on_return)
        win.bind("<Escape>", lambda e: self._on_escape())
        win.protocol("WM_DELETE_WINDOW", self._on_escape)

        win.update_idletasks()
        center_window(win, win.winfo_reqwidth(), win.winfo_reqheight())
        try:
            win.grab_set()
        except Exception:
            pass

    # ── internals ─────────────────────────────────────────────────────────
    def _finish(self, value):
        if self._entry and value is _ENTRY_CONFIRM:
            self.result = self._entry_widget.get()
        else:
            self.result = value
        try:
            self.win.destroy()
        except Exception:
            pass

    def _on_escape(self):
        # result stays at default_result (native semantics)
        try:
            self.win.destroy()
        except Exception:
            pass

    def _on_return(self, _e=None):
        w = None
        try:
            w = self.win.focus_get()
        except Exception:
            pass
        if isinstance(w, ttk.Button):
            w.invoke()
        elif self._confirm_btn is not None:
            self._confirm_btn.invoke()

    def run(self):
        if _test_hook is not None:
            _test_hook(self)
            return self.result
        self.win.wait_window()
        return self.result


def _root_available() -> bool:
    return tk._default_root is not None


def _dialog(kind, title, message, buttons, default_result, parent, **kw):
    if parent is None and not _root_available():
        return None  # signal: caller falls back to native
    return _MessageDialog(parent, kind, title, message, buttons,
                          default_result, **kw).run()


# ── public API (tkinter-compatible signatures) ────────────────────────────
def _ok_buttons():
    return [(tr("確定"), "ok", True)]


def showinfo(title=None, message=None, **options):
    parent = options.get("parent")
    if parent is None and not _root_available():
        from tkinter import messagebox as _m
        return _m.showinfo(title, message, **options)
    _dialog("info", title, message, _ok_buttons(), "ok", parent)
    return "ok"


def showwarning(title=None, message=None, **options):
    parent = options.get("parent")
    if parent is None and not _root_available():
        from tkinter import messagebox as _m
        return _m.showwarning(title, message, **options)
    _dialog("warning", title, message, _ok_buttons(), "ok", parent)
    return "ok"


def showerror(title=None, message=None, **options):
    parent = options.get("parent")
    if parent is None and not _root_available():
        from tkinter import messagebox as _m
        return _m.showerror(title, message, **options)
    _dialog("error", title, message, _ok_buttons(), "ok", parent)
    return "ok"


def askyesno(title=None, message=None, **options):
    parent = options.get("parent")
    if parent is None and not _root_available():
        from tkinter import messagebox as _m
        return _m.askyesno(title, message, **options)
    return bool(_dialog("question", title, message,
                        [(tr("否"), False, False), (tr("是"), True, True)], False, parent))


def askokcancel(title=None, message=None, **options):
    parent = options.get("parent")
    if parent is None and not _root_available():
        from tkinter import messagebox as _m
        return _m.askokcancel(title, message, **options)
    return bool(_dialog("question", title, message,
                        [(tr("取消"), False, False), (tr("確定"), True, True)], False, parent))


def ask_choice(title=None, message=None, *, buttons, default=None,
               kind="question", parent=None):
    """Modal dialog with custom buttons (beyond the tkinter-standard sets).

    *buttons* is a list of ``(label, value)`` pairs — labels must be
    pre-translated; the last pair is styled as the confirm button and takes
    initial focus.  Returns the chosen *value*, or *default* on Esc / ✕ / no
    usable root.
    """
    if parent is None and not _root_available():
        return default
    n = len(buttons)
    btns = [(label, value, i == n - 1) for i, (label, value) in enumerate(buttons)]
    return _dialog(kind, title, message, btns, default, parent)


def askstring(title=None, prompt=None, **kw):
    parent = kw.get("parent")
    if parent is None and not _root_available():
        from tkinter import simpledialog as _sd
        return _sd.askstring(title, prompt, **kw)
    return _dialog("question", title, prompt,
                   [(tr("取消"), None, False), (tr("確定"), _ENTRY_CONFIRM, True)], None,
                   parent, entry=True,
                   initialvalue=kw.get("initialvalue", ""), show=kw.get("show"))
