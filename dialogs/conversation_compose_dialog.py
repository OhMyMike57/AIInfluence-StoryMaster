"""編寫 N 個對話行 — the multi-line bulk text editor.

Opened from 對話歷史's 編寫 ▾ (or the right-click menu) on a *selection* of
lines.  Its one job is quick text edits across several lines at once:

    行號 │ 內容（整行，自動增高）                                   │ ✗
    ── one scrolling row per selected line ──
    [＋ 在末尾新增一行]                              [取消] [完成]

Deliberately narrow in scope, because the earlier, richer version was slow and
did work the single-line tools already do better:

* **Whole-line editing.** Each box holds the entire line verbatim — prefix and
  all — so旁聽／戰場喊話／長期記憶／標籤 need no special-casing and nothing has to
  be split and rejoined.  Careful speaker work belongs in 編寫對話行 (the
  single-line editor with a proper 說話者 field); this is for tweaking text.
* **No per-line speaker widget and no insert-above/below.** Those made every
  row cost six-plus widgets and a 60 ms display-line measurement, so even a
  handful of lines took seconds to open.  Inserting at an arbitrary spot now
  lives in 對話歷史's 右鍵 →〔在此插入對話行〕.
* **Append-only growth.**〔＋ 在末尾新增一行〕adds a line after the last one
  loaded — the overwhelmingly common case.

Line numbers on the left are the numbers each line will really have once
committed, and everything not loaded is passed through untouched;
:mod:`services.compose_plan` owns that bookkeeping.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, List, Optional, Sequence

from i18n import tr
from services import compose_plan as CP
from ui import msgbox as messagebox
from ui.theme import paint, tcol

# Above this many selected lines the window is still usable but worth a heads-up.
# Set high because the rewrite made loading cheap (~4 ms/row); this is only a
# guard against genuinely huge selections.
_WARN_ROWS = 50
_CHUNK = 12               # rows built per idle tick, so the window appears fast

_COL_NUM, _COL_TEXT, _COL_DEL = range(3)


def _fast_line_count(text: str, cols: int = 46) -> int:
    """Cheap wrapped-line estimate — no Tk layout pass.

    ``Text.count(..., "displaylines")`` is accurate but costs ~60 ms per call
    on this Tk build, which is what made the old editor freeze.  Estimating
    from character width (CJK ≈ 2 columns) is O(chars) and close enough to size
    a box; content that overflows simply scrolls.
    """
    n = 0
    for seg in (text or "").split("\n") or [""]:
        width = sum(2 if ord(c) > 0x2E7F else 1 for c in seg)
        n += max(1, (width + cols - 1) // cols)
    return n


class _Tooltip:
    """Minimal hover tooltip — the ✗ button has no text of its own."""

    def __init__(self, widget, text: str):
        self._w = widget
        self._text = text
        self._tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _e=None):
        if self._tip or not self._text:
            return
        try:
            x = self._w.winfo_rootx() + self._w.winfo_width() + 6
            y = self._w.winfo_rooty()
        except tk.TclError:
            return
        self._tip = tk.Toplevel(self._w)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        paint(tk.Label(self._tip, text=self._text, font=("Microsoft JhengHei", 9),
                       relief="solid", borderwidth=1, padx=6, pady=2),
              background=tcol("#FFFDF0"), foreground=tcol("#333333")).pack()

    def _hide(self, _e=None):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class _RowUI:
    def __init__(self):
        self.num: Optional[ttk.Label] = None
        self.text: Optional[tk.Text] = None
        self.text_bg = ""
        self.delbtn: Optional[ttk.Frame] = None


class _ComposeEditor:
    def __init__(self, app, entries: Sequence[Any], *, npc_name: str, npc_id: str,
                 indices: Sequence[int], on_commit: Callable[[List[str], str], None]):
        self.app = app
        self.entries = [e if isinstance(e, str) else str(e) for e in entries]
        self.npc_name = npc_name or ""
        self.npc_id = npc_id or ""
        self.on_commit = on_commit
        self.origins = sorted(set(i for i in indices if 0 <= i < len(self.entries)))

        self._rows: List[CP.Row] = []
        self._uis: List[_RowUI] = []
        self._rendering = True
        self._closed = False

        self._build()

    # ── construction ──────────────────────────────────────────────────────
    def _build(self) -> None:
        win = tk.Toplevel(self.app.root)
        self.win = win
        win.title(tr("編寫 {n} 個對話行").format(n=len(self.origins))
                  + f" — {self.npc_name or '—'}")
        win.transient(self.app.root)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", self._cancel)
        self._center(1040, 760)

        ttk.Label(win, text=tr("編寫 {n} 個對話行").format(n=len(self.origins)),
                  font=("Microsoft JhengHei", 13, "bold"),
                  foreground=tcol("#1A3A5C")).pack(anchor="w", padx=12, pady=(10, 0))
        ttk.Label(
            win, foreground=tcol("#6B5B3E"), justify="left",
            text=tr("每格是一整行對話（含說話者前綴），直接編輯文字即可；左側行號是寫回存檔後"
                    "的真實行號。\n需要精細調整說話者，或在特定位置插入對話，請用對話歷史頁的"
                    "〔編寫對話行〕〔寫入對話行〕。")).pack(anchor="w", padx=12, pady=(2, 6))

        # ── fixed bottom bar ─────────────────────────────────────────────
        bottom = ttk.Frame(win)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(6, 10))
        ttk.Separator(win, orient="horizontal").pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(bottom, text=tr("＋ 在末尾新增一行"), command=self._append_row,
                   style="secondary.TButton").pack(side=tk.LEFT)
        self._status = ttk.Label(bottom, text="", foreground=tcol("#6B5B3E"))
        self._status.pack(side=tk.LEFT, padx=12)
        self._ok_btn = ttk.Button(bottom, text=tr("完成"), command=self._confirm,
                                  style="success.TButton", state="disabled")
        self._ok_btn.pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text=tr("取消"), command=self._cancel,
                   style="secondary.TButton").pack(side=tk.RIGHT, padx=4)

        # ── scrolling body ───────────────────────────────────────────────
        body = ttk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        self._canvas = tk.Canvas(body, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._inner = ttk.Frame(self._canvas)
        self._inner_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._inner_id, width=e.width))
        self._inner.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        # Bound on the toplevel (not bind_all): a modal must not leave the
        # app-wide wheel binding pointing at its destroyed canvas.
        win.bind("<MouseWheel>", self._on_wheel)
        self._inner.columnconfigure(_COL_TEXT, weight=1)

        for o in self.origins:
            self._rows.append(CP.Row(text=self.entries[o], origin=o))
            self._uis.append(_RowUI())
        self._render_from(0)

    def _center(self, w: int, h: int) -> None:
        """Centre over the main window — not the screen.

        ``winfo_screenwidth`` is the whole virtual desktop on a multi-monitor
        setup, so screen-centring dumped the window on a monitor edge.  The app
        window is always on the monitor the user is looking at.
        """
        self.win.update_idletasks()
        p = self.app.root
        try:
            px, py = p.winfo_rootx(), p.winfo_rooty()
            pw, ph = p.winfo_width(), p.winfo_height()
            if pw <= 1:
                raise tk.TclError
        except tk.TclError:
            px = py = 0
            pw, ph = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w = min(w, self.win.winfo_screenwidth() - 40)
        h = min(h, self.win.winfo_screenheight() - 80)
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _on_wheel(self, e):
        if self._closed:
            return None
        try:
            if isinstance(self.win.winfo_containing(e.x_root, e.y_root), tk.Text):
                return None
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except tk.TclError:
            pass
        return None

    # ── rows ──────────────────────────────────────────────────────────────
    def _render_from(self, start: int) -> None:
        if self._closed:
            return
        end = min(start + _CHUNK, len(self._rows))
        for i in range(start, end):
            self._build_row(i)
        if end < len(self._rows):
            self._status.configure(
                text=tr("展開中… {done}/{total}").format(done=end, total=len(self._rows)))
            self.win.after_idle(lambda: self._render_from(end))
            return
        self._rendering = False
        self._ok_btn.configure(state="normal")
        self._renumber()

    def _build_row(self, i: int) -> None:
        ui = self._uis[i]
        inner = self._inner
        content = self._rows[i].text

        ui.num = ttk.Label(inner, text="", width=5, anchor="ne",
                           foreground=tcol("#6B5B3E"),
                           font=("Microsoft JhengHei", 10, "bold"))
        ui.text = paint(
            tk.Text(inner, wrap="word", height=2, font=("Microsoft JhengHei", 10),
                    undo=True, relief="flat", borderwidth=0, highlightthickness=1,
                    padx=6, pady=3),
            highlightbackground=tcol("#b8b8b8"), highlightcolor=tcol("#c49a2d"))
        ui.text.insert("1.0", content)
        ui.text_bg = ui.text.cget("background")
        ui.text.bind("<KeyRelease>", lambda _e, idx=i: self._autosize(idx))
        ui.text.bind("<Control-a>", self._select_all)
        ui.text.bind("<Control-A>", self._select_all)

        ui.delbtn = ttk.Frame(inner)
        b = ttk.Button(ui.delbtn, text="✗", width=4, style="danger.TButton",
                       command=lambda idx=i: self._toggle_delete(idx))
        b.pack()
        _Tooltip(b, tr("刪除／復原此行"))

        self._grid_row(i)
        self._autosize(i)

    def _grid_row(self, i: int) -> None:
        ui = self._uis[i]
        ui.num.grid(row=i, column=_COL_NUM, sticky="ne", padx=(2, 6), pady=3)
        ui.text.grid(row=i, column=_COL_TEXT, sticky="ew", padx=(0, 6), pady=3)
        ui.delbtn.grid(row=i, column=_COL_DEL, sticky="ne", padx=(0, 2), pady=3)

    def _autosize(self, i: int) -> None:
        txt = self._uis[i].text
        if txt is None:
            return
        n = _fast_line_count(txt.get("1.0", "end-1c"))
        txt.configure(height=max(2, min(8, n)))

    @staticmethod
    def _select_all(event):
        event.widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _append_row(self) -> None:
        if self._rows:
            row = CP.new_row_beside(self._rows, len(self._rows) - 1, CP.AFTER)
        else:
            # No selection loaded (an empty history) → land at the very end.
            row = CP.Row(text="", origin=None, anchor=None)
        self._rows.append(row)
        self._uis.append(_RowUI())
        self._build_row(len(self._rows) - 1)
        self._renumber()
        self._uis[-1].text.focus_set()
        self.win.after_idle(lambda: self._canvas.yview_moveto(1.0))

    def _toggle_delete(self, i: int) -> None:
        row = self._rows[i]
        ui = self._uis[i]
        if row.is_new and not row.deleted:
            # A blank inserted row has nothing to restore — drop it outright.
            for w in (ui.num, ui.text, ui.delbtn):
                if w is not None:
                    w.destroy()
            self._rows.pop(i)
            self._uis.pop(i)
            self._rebind_indices()
            self._regrid_all()
            self._renumber()
            return
        row.deleted = not row.deleted
        ui.text.configure(state="disabled" if row.deleted else "normal",
                          background=tcol("#EDEDED") if row.deleted else ui.text_bg)
        self._renumber()

    def _rebind_indices(self) -> None:
        """Row callbacks close over the list index, so rebind after a removal."""
        for i, ui in enumerate(self._uis):
            if ui.delbtn is None:
                continue
            ui.delbtn.winfo_children()[0].configure(
                command=lambda idx=i: self._toggle_delete(idx))
            ui.text.bind("<KeyRelease>", lambda _e, idx=i: self._autosize(idx))

    def _regrid_all(self) -> None:
        for i in range(len(self._rows)):
            if self._uis[i].num is not None:
                self._grid_row(i)

    # ── numbering / status ────────────────────────────────────────────────
    def _renumber(self) -> None:
        nums = CP.line_numbers(self._rows, len(self.entries))
        for i, n in enumerate(nums):
            if self._uis[i].num is not None:
                self._uis[i].num.configure(text="—" if n is None else str(n))
        if self._rendering:
            return
        live = sum(1 for n in nums if n is not None)
        added = sum(1 for r in self._rows if r.is_new and not r.deleted)
        removed = sum(1 for r in self._rows if r.deleted and not r.is_new)
        new_total = len(self.entries) - len(self.origins) + live
        self._status.configure(
            text=tr("原 {old} 行 → 新 {new} 行（新增 {add}、刪除 {rm}）").format(
                old=len(self.entries), new=new_total, add=added, rm=removed))

    # ── commit ────────────────────────────────────────────────────────────
    def _collect(self) -> List[CP.Row]:
        out: List[CP.Row] = []
        for i, row in enumerate(self._rows):
            ui = self._uis[i]
            text = ui.text.get("1.0", "end-1c").strip() if ui.text is not None else row.text
            if not text:
                # A row emptied out was abandoned, not a request for a blank line.
                out.append(CP.Row(text="", origin=row.origin, anchor=row.anchor,
                                  side=row.side, deleted=True))
            else:
                out.append(CP.Row(text=text, origin=row.origin, anchor=row.anchor,
                                  side=row.side, deleted=row.deleted))
        return out

    def _confirm(self) -> None:
        rows = self._collect()
        if not CP.is_dirty(rows, self.entries):
            messagebox.showinfo(tr("編寫對話"), tr("沒有任何變更。"), parent=self.win)
            return
        merged = CP.merge(rows, self.entries)
        if not messagebox.askyesno(
            tr("編寫對話"),
            tr("確定要寫回這段對話嗎？\n\n原 {old} 行 → 新 {new} 行\n\n"
               "（暫存，按右上「儲存」後才寫入檔案）").format(
                   old=len(self.entries), new=len(merged)),
            parent=self.win,
        ):
            return
        self._closed = True
        self.win.destroy()
        self.on_commit(merged, tr("編寫對話"))

    def _cancel(self) -> None:
        if not self._rendering and CP.is_dirty(self._collect(), self.entries):
            if not messagebox.askyesno(
                    tr("放棄編寫"), tr("尚有未寫回的變更，確定要關閉嗎？"), parent=self.win):
                return
        self._closed = True
        self.win.destroy()


def open_compose_dialog(app, entries, *, npc_name: str = "", npc_id: str = "",
                        indices, on_commit: Callable[[List[str], str], None]) -> None:
    """Open 編寫 N 個對話行 for the selected *indices*."""
    picks = [i for i in (indices or [])]
    if not picks:
        messagebox.showwarning(tr("編寫對話"), tr("請先在清單中選取對話行"))
        return
    if len(picks) > _WARN_ROWS:
        if not messagebox.askyesno(
            tr("編寫對話"),
            tr("您選取了 {n} 行，載入可能較緩慢。\n\n仍要開啟嗎？").format(n=len(picks))):
            return
    _ComposeEditor(app, entries, npc_name=npc_name, npc_id=npc_id,
                   indices=picks, on_commit=on_commit)
