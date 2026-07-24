"""Read-only JSON preview widget with optional edit mode.

Usage::

    preview = JsonPreview(parent, on_save=app._json_edit_save, on_revert=app._json_edit_revert)
    preview.pack(fill="both", expand=True)
    preview.load({"id": "secret_01", "description": "..."})
    preview.load_text("raw json text")
    preview.clear()
"""
from __future__ import annotations

from i18n import tr

import json
import re
import tkinter as tk
from tkinter import ttk
from ui import msgbox as messagebox
from typing import Callable, Optional
from ui.theme import tcol


class JsonPreview(ttk.Frame):
    """JSON viewer backed by a tk.Text widget, with an optional edit mode."""

    def __init__(
        self,
        parent,
        *,
        on_save: Optional[Callable[[dict], None]] = None,
        on_revert: Optional[Callable[[], None]] = None,
        edit_variable: Optional[tk.BooleanVar] = None,
        read_only: bool = False,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._on_save_cb = on_save
        self._on_revert_cb = on_revert
        self._original_data: Optional[dict] = None
        # read_only: pure viewer — no edit-mode header, no valid-JSON indicator,
        # no inline editing.  Used where editing happens through a dedicated
        # dialog (e.g. the 訊息與秘密 previews).
        self._read_only = read_only
        # edit_variable: pass the app-wide shared var so edit mode toggles
        # everywhere at once; omit for a standalone per-widget toggle.
        self._edit_var = edit_variable if edit_variable is not None else tk.BooleanVar(value=False)
        self._valid_var = tk.StringVar(value="")
        self._validate_after_id: Optional[str] = None

        self._build_ui()
        # React to external flips of a shared variable (not just our checkbox).
        if not read_only:
            self._edit_var.trace_add("write", lambda *_: self._apply_edit_mode(self._edit_var.get()))

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Header bar + edit affordances are skipped entirely in read-only mode.
        if not self._read_only:
            header = ttk.Frame(self)
            header.pack(fill=tk.X, padx=6, pady=(4, 0))

            ttk.Checkbutton(
                header,
                text=tr("編輯模式"),
                variable=self._edit_var,
            ).pack(side=tk.LEFT)

            self._valid_label = ttk.Label(header, textvariable=self._valid_var)
            self._valid_label.pack(side=tk.RIGHT, padx=8)

            # Warning label (hidden by default)
            self._warning_label = ttk.Label(
                self,
                text=tr("⚠ 直接編輯 JSON 可能導致資料損毀，請謹慎操作"),
                foreground=tcol("#b36b00"),
            )

            ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=4, pady=(4, 0))

        # Text area + scrollbar
        text_frame = ttk.Frame(self)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self._text = tk.Text(
            text_frame,
            wrap="word",
            state="disabled",
            font=("Microsoft JhengHei", 10),
        )
        self._scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=self._scroll.set)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure JSON syntax colors
        self._text.tag_configure("key",    foreground=tcol("#0451a5"))
        self._text.tag_configure("string", foreground=tcol("#a31515"))
        self._text.tag_configure("number", foreground=tcol("#098658"))
        self._text.tag_configure("bool",   foreground=tcol("#0000ff"))
        self._text.tag_configure("null",   foreground=tcol("#808080"))

        # Action bar (hidden by default)
        self._action_bar = ttk.Frame(self)
        ttk.Button(
            self._action_bar,
            text=tr("💾 儲存"),
            command=self._on_save,
            style="warning.TButton",
        ).pack(side=tk.RIGHT, padx=4, pady=4)
        ttk.Button(
            self._action_bar,
            text=tr("取消"),
            command=self._on_revert,
            style="secondary.TButton",
        ).pack(side=tk.RIGHT, padx=4, pady=4)

    # ── Public API ────────────────────────────────────────────────────────

    def load(self, data) -> None:
        """Format and display a Python dict/list as pretty JSON.

        Edit mode state is preserved across character switches.
        """
        self._original_data = data
        text = json.dumps(data, ensure_ascii=False, indent=2)

        # Update text content while respecting current edit mode state
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)
        self._apply_syntax_highlight()
        if self._read_only or not self._edit_var.get():
            self._text.configure(state="disabled")
        self._valid_var.set("")

    def load_text(self, text: str) -> None:
        """Display pre-formatted text."""
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)
        self._apply_syntax_highlight()
        if self._read_only or not self._edit_var.get():
            self._text.configure(state="disabled")
        self._valid_var.set("")

    def _apply_syntax_highlight(self) -> None:
        """Apply JSON syntax colours using regex + tag_add().

        Works while text widget is in either normal or disabled state
        (tag_add does not require the widget to be editable).
        """
        for tag in ("key", "string", "number", "bool", "null"):
            self._text.tag_remove(tag, "1.0", "end")

        content = self._text.get("1.0", "end-1c")
        if not content.strip():
            return

        # Build a fast offset → (line, col) converter.
        # Pre-compute line-start positions so we don't re-scan on every match.
        line_starts: list[int] = [0]
        for i, ch in enumerate(content):
            if ch == "\n":
                line_starts.append(i + 1)

        def to_index(pos: int) -> str:
            # Binary-search for the line that contains pos
            lo, hi = 0, len(line_starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if line_starts[mid] <= pos:
                    lo = mid
                else:
                    hi = mid - 1
            return f"{lo + 1}.{pos - line_starts[lo]}"

        # ── Keys ─────────────────────────────────────────────────────────────
        # Match the quoted string that is immediately followed (with optional
        # whitespace) by a colon — this is the key in  "key": value.
        key_pat = re.compile(r'"(?:[^"\\]|\\.)*"(?=\s*:)')
        key_positions: set[int] = set()
        for m in key_pat.finditer(content):
            self._text.tag_add("key", to_index(m.start()), to_index(m.end()))
            key_positions.update(range(m.start(), m.end()))

        # ── String values ────────────────────────────────────────────────────
        str_pat = re.compile(r'"(?:[^"\\]|\\.)*"')
        for m in str_pat.finditer(content):
            if m.start() not in key_positions:
                self._text.tag_add("string", to_index(m.start()), to_index(m.end()))

        # ── Numbers ──────────────────────────────────────────────────────────
        for m in re.finditer(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', content):
            self._text.tag_add("number", to_index(m.start()), to_index(m.end()))

        # ── Booleans ─────────────────────────────────────────────────────────
        for m in re.finditer(r'\b(?:true|false)\b', content):
            self._text.tag_add("bool", to_index(m.start()), to_index(m.end()))

        # ── Null ─────────────────────────────────────────────────────────────
        for m in re.finditer(r'\bnull\b', content):
            self._text.tag_add("null", to_index(m.start()), to_index(m.end()))

    def clear(self) -> None:
        """Clear all content."""
        self._original_data = None
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._valid_var.set("")

    def get_text_widget(self) -> tk.Text:
        """Return the underlying Text widget for advanced operations."""
        return self._text

    # ── Edit mode ─────────────────────────────────────────────────────────

    def _toggle_edit_mode(self) -> None:
        self._apply_edit_mode(self._edit_var.get())

    def _apply_edit_mode(self, editing: bool) -> None:
        if self._read_only:
            return
        if editing:
            self._text.configure(state="normal")
            self._warning_label.pack(fill=tk.X, padx=8, pady=(2, 0))
            self._action_bar.pack(fill=tk.X, padx=4, pady=0)
            self._text.bind("<KeyRelease>", self._debounced_validate)
            self._validate_json()
        else:
            self._text.configure(state="disabled")
            self._warning_label.pack_forget()
            self._action_bar.pack_forget()
            self._text.unbind("<KeyRelease>")
            if self._validate_after_id:
                self.after_cancel(self._validate_after_id)
                self._validate_after_id = None
            self._valid_var.set("")

    def _debounced_validate(self, event=None) -> None:
        if self._validate_after_id:
            self.after_cancel(self._validate_after_id)
        self._validate_after_id = self.after(500, self._validate_json)

    def _validate_json(self) -> None:
        text = self._text.get("1.0", "end-1c")
        try:
            json.loads(text)
            self._valid_var.set(tr("✅ 有效 JSON"))
            self._valid_label.configure(foreground=tcol("green"))
        except json.JSONDecodeError as e:
            self._valid_var.set(tr("❌ 第 {line} 行語法錯誤").format(line=e.lineno))
            self._valid_label.configure(foreground=tcol("red"))

    # ── Action callbacks ──────────────────────────────────────────────────

    def _on_save(self) -> None:
        text = self._text.get("1.0", "end-1c")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            messagebox.showerror(tr("錯誤"), tr("JSON 格式無效，無法儲存\n第 {v0} 行：{v1}").format(v0=e.lineno, v1=e.msg))
            return
        if self._on_save_cb:
            self._on_save_cb(data)

    def _on_revert(self) -> None:
        if self._on_revert_cb:
            self._on_revert_cb()
