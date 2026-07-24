"""角色人設 editor window — side-by-side original / edit (+ optional third-party
reference), a real text-editing experience (Ctrl+Z/Y, click-to-copy), and
clipboard export/import.

Opened from the 摘要 tab's persona heading buttons.  Layout:

    原文（唯讀）  │  編輯          │  [第三方參照（唯讀）]
    ─ 5 field rows, single vertical scroll ─
    [＋第三方參照] [第三方角色: 🔍]                 [確定][取消]   ← fixed bottom
"""
from __future__ import annotations

import json
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from ui import msgbox as messagebox
from pathlib import Path
from typing import Any, Dict, List, Optional

from i18n import tr
from services import persona_transfer as PT
from widgets.name_id_combo import NameIdCombo
from widgets.popover_menu import PopoverPanel
from widgets.toast import show_toast
from widgets.window_center import center_window
from ui.theme import paint, tcol

# (field key, zh-Hant label) — labels wrapped in tr() at render.
_FIELDS = [
    ("CharacterDescription",      "角色描述"),   # noqa: cjk
    ("AIGeneratedPersonality",    "角色性格"),   # noqa: cjk
    ("AIGeneratedBackstory",      "背景故事"),   # noqa: cjk
    ("AIGeneratedSpeechQuirks",   "說話習慣"),   # noqa: cjk
    ("AIGeneratedCognitiveStyle", "認知風格"),   # noqa: cjk
]
_MONO = ("Microsoft JhengHei", 10)


def _make_text(parent, *, readonly: bool, height: int = 10):
    """A Text + scrollbar cell.  Readonly cells block edits but allow selection,
    copy, and click-to-copy-all (with a toast)."""
    frame = ttk.Frame(parent)
    # Border via highlightbackground, NOT relief="solid": a solid relief is
    # drawn from the widget's own background, so on the dark theme the frame
    # vanished into the surface and the field boundaries were invisible.
    # highlightthickness paints an explicitly themed colour in both modes.
    txt = paint(
        tk.Text(frame, wrap="word", height=height, font=_MONO,
                undo=not readonly, autoseparators=True, maxundo=-1,
                relief="flat", borderwidth=0, highlightthickness=1,
                padx=6, pady=4),
        highlightbackground=tcol("#b8b8b8"), highlightcolor=tcol("#c49a2d"))
    sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    if readonly:
        txt.configure(background=tcol("#F6F4EE"))

        def _block(e):
            if (e.state & 0x4) and e.keysym.lower() in ("c", "a"):
                return None  # allow Ctrl+C / Ctrl+A (select-all + copy)
            if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                            "Prior", "Next"):
                return None
            return "break"
        txt.bind("<KeyPress>", _block)
    else:
        def _redo(_e):
            try:
                txt.edit_redo()
            except tk.TclError:
                pass
            return "break"

        def _sel_all(_e):
            txt.tag_add("sel", "1.0", "end-1c")
            return "break"
        txt.bind("<Control-y>", _redo)
        txt.bind("<Control-Y>", _redo)
        txt.bind("<Control-a>", _sel_all)
        txt.bind("<Control-A>", _sel_all)

    # Wheel over a field scrolls ONLY that field.  The handler MUST return the
    # string "break" (not a tuple) so propagation to the outer canvas' 'all'
    # bindtag stops — otherwise the whole page scrolls too.
    def _wheel(e):
        txt.yview_scroll(int(-1 * (e.delta / 120)), "units")
        return "break"
    txt.bind("<MouseWheel>", _wheel)
    return frame, txt


def _set_text(txt: tk.Text, value: str, readonly: bool) -> None:
    txt.configure(state="normal")
    txt.delete("1.0", "end")
    txt.insert("1.0", str(value or ""))
    if not readonly:
        txt.edit_reset()   # start a clean undo stack at the loaded value
        txt.edit_modified(False)


class _PersonaEditor:
    def __init__(self, app, path: Path, data: dict, import_fields: Optional[dict]):
        self.app = app
        self.path = path
        self.data = data or {}
        self.import_fields = import_fields
        # Both reference columns start collapsed so the plain editing case gets a
        # window only as wide as it needs.  Clipboard-import is the exception:
        # comparing against the current text is the whole point there.
        self._orig_active = import_fields is not None
        self._third_active = False
        self._orig: Dict[str, tk.Text] = {}
        self._edit: Dict[str, tk.Text] = {}
        self._third: Dict[str, tk.Text] = {}
        self._orig_frames: Dict[str, ttk.Frame] = {}
        self._third_frames: Dict[str, ttk.Frame] = {}
        self._content_rows: Dict[str, int] = {}
        self._heights: Dict[str, int] = {f: 10 for f, _ in _FIELDS}
        self._drag: Optional[dict] = None

        # StringId → character file path (for the third-party picker).
        self._sid_to_path: Dict[str, Path] = {}
        for disp, meta in (getattr(app, "character_meta", {}) or {}).items():
            sid = str((meta or {}).get("StringId") or "")
            p = getattr(app, "plain_to_path", {}).get(disp)
            if sid and p:
                self._sid_to_path[sid] = p

        self._build()

    # ── construction ──────────────────────────────────────────────────
    def _build(self):
        win = tk.Toplevel(self.app.root)
        self.win = win
        is_import = self.import_fields is not None
        name = self.data.get("Name") or self.path.stem
        win.title((tr("導入人設（剪貼簿）") if is_import else tr("編輯角色人設")) + f" — {name}")
        win.transient(self.app.root)
        win.grab_set()

        # Header
        ttk.Label(win, text=f"ID：{self.data.get('StringId') or ''}",
                  foreground=tcol("#9A9A9A")).pack(anchor="w", padx=12, pady=(10, 0))
        ttk.Label(win, text=name, font=("Microsoft JhengHei", 13, "bold"),
                  foreground=tcol("#1A3A5C")).pack(anchor="w", padx=12)

        # ── fixed bottom bar (packed FIRST so it never gets clipped) ──
        bottom = ttk.Frame(win)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(6, 10))
        ttk.Separator(win, orient="horizontal").pack(side=tk.BOTTOM, fill=tk.X)

        # Left group: 導出 / 導入 ｜ ＋第三方參照 …（第三方控件）
        self._export_btn = ttk.Button(bottom, text=tr("📤 導出"), style="secondary.TButton")
        self._export_btn.pack(side=tk.LEFT)
        ttk.Button(bottom, text=tr("📥 導入"), command=self._import_clipboard,
                   style="secondary.TButton").pack(side=tk.LEFT, padx=(4, 0))
        ttk.Separator(bottom, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)
        # 原文參照 sits left of 第三方參照: both are optional reference columns,
        # and the window only widens for the ones actually opened.
        self._orig_btn = ttk.Button(bottom, text=tr("＋ 原文參照"),
                                    command=self._toggle_orig, style="secondary.TButton")
        self._orig_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._third_btn = ttk.Button(bottom, text=tr("＋ 第三方參照"),
                                     command=self._toggle_third, style="secondary.TButton")
        self._third_btn.pack(side=tk.LEFT)
        self._third_lbl = ttk.Label(bottom, text=tr("第三方角色："))
        self._third_combo = NameIdCombo(bottom, self.app, "characters", width=22,
                                        allow_empty=False, autocomplete=True)
        self._third_load_btn = ttk.Button(bottom, text=tr("載入參照"),
                                          command=self._load_third, style="info.TButton")

        # Right group: 完成（success，最右）/ 取消 — aligns with 動態事件編輯器.
        ttk.Button(bottom, text=tr("完成"), command=self._confirm,
                   style="success.TButton").pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text=tr("取消"), command=self._cancel,
                   style="secondary.TButton").pack(side=tk.RIGHT, padx=4)

        # 導出 → upward-expanding panel (checkboxes + 全選 + 導出), toggled by the button.
        self._export_panel = PopoverPanel(self._export_btn, direction="up",
                                          builder=self._build_export_panel)
        self._export_btn.configure(command=self._export_panel.toggle)

        # ── scrollable body ──
        body = ttk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
        self._canvas = tk.Canvas(body, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = ttk.Frame(self._canvas)
        self._inner = inner
        self._inner_id = self._canvas.create_window((0, 0), window=inner, anchor="nw")
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfigure(self._inner_id, width=e.width))
        inner.bind("<Configure>",
                   lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

        # Only the edit column is laid out up front; the two reference columns
        # are gridded on demand (see _toggle_orig / _toggle_third).
        inner.columnconfigure(1, weight=1, uniform="pc")

        # Pixel height of one text line — for the drag-to-resize sashes.
        try:
            self._line_h = tkfont.Font(font=_MONO).metrics("linespace") or 18
        except Exception:
            self._line_h = 18

        # Resting colour of the drag strips = the surrounding surface, so they
        # only light up under the pointer (see _sash_hover).
        try:
            self._sash_rest = (ttk.Style().lookup("TFrame", "background")
                               or tcol("#f6f4ee"))
        except tk.TclError:
            self._sash_rest = tcol("#f6f4ee")

        self._cap_orig = ttk.Label(inner, text=tr("原文（唯讀）"), foreground=tcol("#6B5B3E"),
                                   font=("Microsoft JhengHei", 10, "bold"))
        self._cap_edit = ttk.Label(inner, text=tr("編輯"), foreground=tcol("#2D6A4F"),
                                   font=("Microsoft JhengHei", 10, "bold"))
        self._cap_third = ttk.Label(inner, text=tr("第三方參照（唯讀）"), foreground=tcol("#7B5010"),
                                    font=("Microsoft JhengHei", 10, "bold"))
        self._cap_edit.grid(row=0, column=1, sticky="w", padx=4)

        r = 1
        for field, label in _FIELDS:
            ttk.Label(inner, text=f"【{tr(label)}】",
                      font=("Microsoft JhengHei", 11, "bold"), foreground=tcol("#884EA0")
                      ).grid(row=r, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 2))
            r += 1
            of, ot = _make_text(inner, readonly=True)
            ef, et = _make_text(inner, readonly=False)
            tf, tt = _make_text(inner, readonly=True)
            ef.grid(row=r, column=1, sticky="nsew", padx=(8, 8), pady=(0, 2))
            self._orig[field], self._edit[field], self._third[field] = ot, et, tt
            self._orig_frames[field] = of
            self._third_frames[field] = tf
            self._content_rows[field] = r   # so _toggle_third grids the 3rd column here
            cur = str(self.data.get(field, "") or "")
            _set_text(ot, cur, readonly=True)
            init_edit = (self.import_fields or {}).get(field, cur) if self.import_fields else cur
            _set_text(et, init_edit, readonly=False)
            r += 1

            # Draggable sash: resize this field's height across all columns so
            # original / edit / reference stay aligned.  It used to be a 3px
            # #C4C4C4 line, which was invisible on the dark theme and nearly
            # impossible to hit — now it is a taller grab strip with a grip
            # marker and a hover highlight, so it can actually be found.
            # paint(): constructor colours are dropped under ttkbootstrap.
            sash = paint(tk.Frame(inner, height=7, cursor="sb_v_double_arrow"),
                         bg=self._sash_rest)
            sash.grid(row=r, column=0, columnspan=3, sticky="ew", padx=8, pady=(4, 9))
            sash.grid_propagate(False)
            grip = paint(tk.Label(sash, text="⋯⋯⋯",
                                  font=("Microsoft JhengHei", 7),
                                  cursor="sb_v_double_arrow"),
                         bg=self._sash_rest, fg=tcol("#999999"))
            grip.place(relx=0.5, rely=0.5, anchor="center")
            for w in (sash, grip):
                w.bind("<Button-1>", lambda e, f=field: self._sash_start(e, f))
                w.bind("<B1-Motion>", lambda e, f=field: self._sash_drag(e, f))
                w.bind("<Enter>", lambda e, s=sash, g=grip: self._sash_hover(s, g, True))
                w.bind("<Leave>", lambda e, s=sash, g=grip: self._sash_hover(s, g, False))
            r += 1

        # Grid the 原文 column when it starts open (clipboard-import), then size
        # + center according to how many reference columns are showing.
        if self._orig_active:
            self._orig_active = False        # _toggle_orig flips it back on
            self._toggle_orig()
        else:
            self._resize()

    # ── behaviours ────────────────────────────────────────────────────
    def _on_wheel(self, e):
        # Fallback for wheel over non-field areas (labels / gaps / canvas bg);
        # field Text widgets handle their own wheel and 'break' before this.
        try:
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:
            pass

    def _sash_hover(self, sash, grip, on: bool) -> None:
        """Highlight a drag strip only while the pointer is over it.

        At rest the strip carries the container's own background so it reads as
        empty space with a faint grip marker; a filled band would draw a heavy
        grey rule between every field.
        """
        try:
            sash.configure(bg=tcol("#c49a2d") if on else self._sash_rest)
            grip.configure(bg=tcol("#c49a2d") if on else self._sash_rest,
                           fg=tcol("#555555") if on else tcol("#999999"))
        except tk.TclError:
            pass

    def _sash_start(self, e, field: str):
        self._drag = {"field": field, "y": e.y_root, "h": self._heights.get(field, 10)}

    def _sash_drag(self, e, field: str):
        if not self._drag or self._drag.get("field") != field:
            return
        delta = round((e.y_root - self._drag["y"]) / max(1, self._line_h))
        new_h = max(4, min(48, self._drag["h"] + delta))
        if new_h == self._heights.get(field):
            return
        self._heights[field] = new_h
        for t in (self._orig[field], self._edit[field], self._third[field]):
            try:
                t.configure(height=new_h)
            except Exception:
                pass

    def _resize(self):
        """Size the window for the number of open reference columns.

        Three states: edit only / edit + one reference / edit + both.  The
        editing column keeps roughly the same width in all three, so opening a
        reference grows the window instead of squeezing what you were writing.
        """
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        refs = int(self._orig_active) + int(self._third_active)
        w = min(int(sw * 0.92), (740, 1480, 1980)[refs])
        h = min(int(sh * 0.92), 820)
        center_window(self.win, w, h)

    def _toggle_orig(self):
        self._orig_active = not self._orig_active
        if self._orig_active:
            self._inner.columnconfigure(0, weight=1, uniform="pc")
            self._cap_orig.grid(row=0, column=0, sticky="w", padx=4)
            for field, _label in _FIELDS:
                self._orig_frames[field].grid(row=self._content_rows[field], column=0,
                                              sticky="nsew", padx=(8, 8), pady=(0, 2))
            self._orig_btn.configure(text=tr("－ 收起原文"))
        else:
            self._cap_orig.grid_forget()
            for field, _label in _FIELDS:
                self._orig_frames[field].grid_forget()
            self._inner.columnconfigure(0, weight=0, uniform="")
            self._orig_btn.configure(text=tr("＋ 原文參照"))
        self._resize()

    def _toggle_third(self):
        self._third_active = not self._third_active
        if self._third_active:
            self._inner.columnconfigure(2, weight=1, uniform="pc")
            self._cap_third.grid(row=0, column=2, sticky="w", padx=4)
            for field, _label in _FIELDS:
                self._third_frames[field].grid(row=self._content_rows[field], column=2,
                                               sticky="nsew", padx=(8, 8), pady=(0, 2))
            self._third_btn.configure(text=tr("－ 移除參照"))
            self._third_lbl.pack(side=tk.LEFT, padx=(12, 2))
            self._third_combo.pack(side=tk.LEFT, padx=(0, 2))
            self._third_load_btn.pack(side=tk.LEFT, padx=(0, 2))
        else:
            self._cap_third.grid_forget()
            for field, _label in _FIELDS:
                self._third_frames[field].grid_forget()
                _set_text(self._third[field], "", readonly=True)
            self._inner.columnconfigure(2, weight=0, uniform="")
            self._third_btn.configure(text=tr("＋ 第三方參照"))
            self._third_lbl.pack_forget()
            self._third_combo.pack_forget()
            self._third_load_btn.pack_forget()
        self._resize()

    def _load_third(self):
        sid = self._third_combo.get_id().strip()
        p = self._sid_to_path.get(sid)
        if not p:
            messagebox.showinfo(tr("第三方參照"),
                                tr("找不到該角色的存檔（可能尚未生成）。"), parent=self.win)
            return
        d = self.app._safe_load_json(p) or {}
        for field, _label in _FIELDS:
            _set_text(self._third[field], str(d.get(field, "") or ""), readonly=True)

    # ── export panel (upward, on the 導出 button) ──────────────────────
    def _build_export_panel(self, body: tk.Frame):
        paint(tk.Label(body, text=tr("選擇導出欄位（複製至剪貼簿）"),
                       font=("Microsoft JhengHei", 10, "bold"), anchor="w"),
              bg=tcol("#FFFFFF"), fg=tcol("#333333")
              ).pack(fill="x", padx=10, pady=(8, 2))
        self._export_vars = {}
        all_var = tk.BooleanVar(value=True)

        def _toggle_all():
            for v in self._export_vars.values():
                v.set(all_var.get())

        def _sync_all():
            all_var.set(all(v.get() for v in self._export_vars.values()))

        paint(tk.Checkbutton(body, text=tr("全選"), variable=all_var,
                             command=_toggle_all, anchor="w"),
              bg=tcol("#FFFFFF"), activebackground=tcol("#FFFFFF")
              ).pack(fill="x", padx=10)
        ttk.Separator(body, orient="horizontal").pack(fill="x", padx=8, pady=2)
        for field, label in _FIELDS:
            v = tk.BooleanVar(value=True)
            self._export_vars[field] = v
            paint(tk.Checkbutton(body, text=tr(label), variable=v,
                                 command=_sync_all, anchor="w"),
                  bg=tcol("#FFFFFF"), activebackground=tcol("#FFFFFF")
                  ).pack(fill="x", padx=10)
        ttk.Button(body, text=tr("導出"), command=self._do_export_panel,
                   style="success.TButton").pack(anchor="e", padx=10, pady=(6, 8))

    def _do_export_panel(self):
        chosen = [f for f, v in self._export_vars.items() if v.get()]
        if not chosen:
            messagebox.showwarning(tr("導出人設"), tr("請至少勾選一個欄位。"), parent=self.win)
            return
        # Export the CURRENT edit text (includes unsaved changes) so the user
        # can tweak then export in one go.
        source = dict(self.data)
        for field, _label in _FIELDS:
            source[field] = self._edit[field].get("1.0", "end-1c")
        js = PT.build_export_json(source, chosen)
        self.win.clipboard_clear()
        self.win.clipboard_append(js)
        self._export_panel.hide()
        show_toast(self.win, tr("已導出人設至剪貼簿"))

    # ── import from clipboard (overwrite edit fields) ──────────────────
    def _import_clipboard(self):
        try:
            text = self.win.clipboard_get()
        except tk.TclError:
            text = ""
        try:
            fields, _kind = PT.parse_import_json(text)
        except ValueError:
            messagebox.showwarning(
                tr("導入人設"),
                tr("剪貼簿內容不是有效的人設 JSON（需含至少一個人設欄位）。"),
                parent=self.win)
            return
        if self._changed_fields():
            if not messagebox.askyesno(
                    tr("導入人設"),
                    tr("將以剪貼簿內容覆蓋對應的編輯欄，繼續？"), parent=self.win):
                return
        for field, val in fields.items():
            if field in self._edit:
                _set_text(self._edit[field], str(val or ""), readonly=False)

    def _changed_fields(self) -> Dict[str, str]:
        out = {}
        for field, _label in _FIELDS:
            new = self._edit[field].get("1.0", "end-1c")
            if new != str(self.data.get(field, "") or ""):
                out[field] = new
        return out

    def _confirm(self):
        changed = self._changed_fields()
        if not changed:
            messagebox.showinfo(tr("角色人設"), tr("沒有任何變更。"), parent=self.win)
            return
        self.app._persona_batch_save(self.path, changed)
        self._close()

    def _cancel(self):
        if self._changed_fields():
            if not messagebox.askyesno(tr("角色人設"),
                                       tr("有未儲存的變更，確定放棄嗎？"), parent=self.win):
                return
        self._close()

    def _close(self):
        try:
            self._canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.win.destroy()


def open_persona_editor(app, path, data, *, import_fields=None) -> None:
    _PersonaEditor(app, Path(path), data, import_fields)


# ── Export field-picker dialog ────────────────────────────────────────────────
def open_persona_export(app, path, data) -> None:
    win = tk.Toplevel(app.root)
    win.title(tr("導出人設"))
    win.transient(app.root)
    win.grab_set()
    center_window(win, 360, 300)
    ttk.Label(win, text=tr("選擇要導出的人設欄位（複製至剪貼簿）："),
              wraplength=320).pack(anchor="w", padx=12, pady=(12, 6))
    vars_by_field = {}
    all_var = tk.BooleanVar(value=True)

    def _toggle_all():
        for v in vars_by_field.values():
            v.set(all_var.get())

    def _sync_all():
        all_var.set(all(v.get() for v in vars_by_field.values()))

    ttk.Checkbutton(win, text=tr("全選"), variable=all_var,
                    command=_toggle_all).pack(anchor="w", padx=14)
    ttk.Separator(win, orient="horizontal").pack(fill="x", padx=12, pady=3)
    for field, label in _FIELDS:
        v = tk.BooleanVar(value=True)
        vars_by_field[field] = v
        ttk.Checkbutton(win, text=tr(label), variable=v,
                        command=_sync_all).pack(anchor="w", padx=18)

    def _do():
        chosen = [f for f, v in vars_by_field.items() if v.get()]
        if not chosen:
            messagebox.showwarning(tr("導出人設"), tr("請至少勾選一個欄位。"), parent=win)
            return
        js = PT.build_export_json(data, chosen)
        win.clipboard_clear()
        win.clipboard_append(js)
        anchor = app.root
        win.destroy()
        show_toast(anchor, tr("已導出人設至剪貼簿"))

    btns = ttk.Frame(win)
    btns.pack(fill=tk.X, padx=12, pady=(10, 10), side=tk.BOTTOM)
    ttk.Button(btns, text=tr("導出"), command=_do, style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(btns, text=tr("取消"), command=win.destroy, style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
