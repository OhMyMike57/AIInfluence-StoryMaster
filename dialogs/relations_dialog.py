"""關聯角色清單 — a character's eavesdroppers or sharers of one 對話歷史 line.

Two views share this window (see :mod:`services.radiation_service`):

* **旁聽者** — who overheard the line, with distance and the distorted text;
* **共用者** — who holds the same line content, with how their copy attributes it.

Both do the same things — list characters, add them to the workspace's selected
list (locked), and clean one out (remove their copy / observation, staged) — so
they share this dialog.  The wording differs per view, so every localized string
is passed in by the opener as a literal ``tr()`` result (never ``tr(variable)``);
the dialog only renders what it is handed.

Laid out like 對話歷史 — a multi-select list on top, a read-only preview of the
focused row below, an action row at the bottom.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Callable, List, Optional, Tuple

from i18n import tr
from ui import msgbox as messagebox
from ui.theme import tcol
from ui.tree_helpers import enable_drag_select, enable_select_all
from widgets.popover_menu import PopoverMenu

_MONO = ("Microsoft JhengHei", 10)


@dataclass
class RelRow:
    """One character row.  ``detail_cols`` aligns to the spec's detail columns."""
    key: str
    name: str
    detail_cols: Tuple[str, ...]
    full_text: str
    token: str          # utterance_id (eaves) or content (share)
    subtitle: str = ""  # e.g. the id line under the name in the preview


@dataclass
class RelSpec:
    """Everything view-specific — all strings already localized by the opener."""
    title: str
    subtitle: str
    name_heading: str
    detail_columns: List[tuple]          # (id, heading, width, anchor, stretch)
    rows: List[RelRow]
    on_add: Callable[[List[str]], int]
    on_clean: Callable[[str, str], dict]
    add_bottom: str
    add_one: str
    add_n: Callable[[int], str]
    clean_bottom: str
    clean_one: str
    clean_n: Callable[[int], str]
    confirm_clean: Callable[[int], str]
    cleaned_msg: Callable[[int], str]
    added_msg: Callable[[int], str]
    info_title: str
    select_first: str
    empty_preview: str
    hint: str = field(default="")


class _RelationsDialog:
    def __init__(self, app, spec: RelSpec):
        self.app = app
        self.spec = spec
        self._rows: List[RelRow] = list(spec.rows)
        self._by_iid: dict = {}
        self._ctx = None
        self._build()

    # ── construction ──────────────────────────────────────────────────────
    def _build(self) -> None:
        win = tk.Toplevel(self.app.root)
        self.win = win
        win.title(self.spec.title)
        win.transient(self.app.root)
        win.grab_set()
        self._center(780, 620)

        ttk.Label(win, text=self.spec.title, font=("Microsoft JhengHei", 13, "bold"),
                  foreground=tcol("#1A3A5C")).pack(anchor="w", padx=12, pady=(10, 0))
        sub = self.spec.subtitle.replace("\n", " ")
        if len(sub) > 96:
            sub = sub[:96] + "…"
        ttk.Label(win, text=sub, foreground=tcol("#6B5B3E"),
                  wraplength=740, justify="left").pack(anchor="w", padx=12, pady=(2, 6))

        # ── fixed action row (packed first) ───────────────────────────────
        bar = ttk.Frame(win)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(6, 10))
        ttk.Separator(win, orient="horizontal").pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(bar, text=self.spec.add_bottom, command=self._add_selected,
                   style="info.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text=self.spec.clean_bottom, command=self._clean_selected,
                   style="danger.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text=tr("確認"), command=win.destroy,
                   style="success.TButton").pack(side=tk.RIGHT, padx=4)
        ttk.Button(bar, text=tr("取消"), command=win.destroy,
                   style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
        if self.spec.hint:
            ttk.Label(bar, text=self.spec.hint,
                      foreground=tcol("#9AA0A6")).pack(side=tk.RIGHT, padx=8)

        # ── list + preview ────────────────────────────────────────────────
        panes = ttk.Panedwindow(win, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))

        top = ttk.Frame(panes)
        cols = ["name"] + [c[0] for c in self.spec.detail_columns]
        self._tree = ttk.Treeview(top, columns=cols, show="headings",
                                  selectmode="extended", height=8)
        self._tree.heading("name", text=self.spec.name_heading)
        self._tree.column("name", width=180, anchor="w", stretch=False)
        for cid, heading, w, anchor, stretch in self.spec.detail_columns:
            self._tree.heading(cid, text=heading)
            self._tree.column(cid, width=w, anchor=anchor, stretch=stretch)
        vsb = ttk.Scrollbar(top, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._render_preview())
        self._tree.bind("<Double-Button-1>", self._on_double)
        self._tree.bind("<Button-3>", self._on_right_click)
        enable_select_all(self._tree)
        enable_drag_select(self._tree)
        panes.add(top, weight=7)

        bottom = ttk.Frame(panes)
        self._preview = tk.Text(bottom, wrap="word", font=_MONO, relief="flat",
                                height=4, padx=10, pady=6, state="disabled",
                                cursor="arrow")
        self._preview.tag_configure("key", font=("Microsoft JhengHei", 10, "bold"),
                                    foreground=tcol("#6B5B3E"))
        self._preview.tag_configure("empty", font=("Microsoft JhengHei", 10, "italic"),
                                    foreground=tcol("#999999"))
        self._preview.pack(fill=tk.BOTH, expand=True)
        panes.add(bottom, weight=3)

        self._populate()

    def _center(self, w: int, h: int) -> None:
        self.win.update_idletasks()
        p = self.app.root
        try:
            px, py, pw, ph = (p.winfo_rootx(), p.winfo_rooty(),
                              p.winfo_width(), p.winfo_height())
            if pw <= 1:
                raise tk.TclError
        except tk.TclError:
            px = py = 0
            pw, ph = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    # ── data ──────────────────────────────────────────────────────────────
    def _populate(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._by_iid = {}
        for i, r in enumerate(self._rows):
            iid = f"rel::{i}"
            self._tree.insert("", "end", iid=iid, values=(r.name,) + r.detail_cols)
            self._by_iid[iid] = r
        self._render_preview()

    def _selected(self) -> List[RelRow]:
        return [self._by_iid[i] for i in self._tree.selection() if i in self._by_iid]

    def _focused(self) -> Optional[RelRow]:
        cur = self._tree.focus()
        if cur in self._by_iid:
            return self._by_iid[cur]
        sel = self._selected()
        return sel[0] if sel else None

    def _render_preview(self) -> None:
        r = self._focused()
        t = self._preview
        t.configure(state="normal")
        t.delete("1.0", "end")
        if r is None:
            t.insert("end", self.spec.empty_preview, "empty")
        else:
            t.insert("end", r.name, "key")
            if r.subtitle:
                t.insert("end", f"　{r.subtitle}", "empty")
            t.insert("end", "\n\n")
            t.insert("end", r.full_text or tr("（無內容）"))
        t.configure(state="disabled")

    # ── actions ───────────────────────────────────────────────────────────
    def _on_double(self, _event=None):
        r = self._focused()
        if r is not None:
            self._add([r])
        return "break"

    def _on_right_click(self, event):
        iid = self._tree.identify_row(event.y)
        if iid and iid not in self._tree.selection():
            self._tree.selection_set(iid)
        if iid:
            self._tree.focus(iid)
        picks = self._selected()
        if not picks:
            return "break"
        n = len(picks)
        add_label = self.spec.add_one if n == 1 else self.spec.add_n(n)
        clean_label = self.spec.clean_one if n == 1 else self.spec.clean_n(n)
        items = [
            (add_label, lambda: self._add(picks)),
            (clean_label, lambda: self._clean(picks), "danger"),
        ]
        self._ctx = PopoverMenu(self._tree, items, at=(event.x_root, event.y_root))
        self._ctx.show()
        return "break"

    def _add_selected(self) -> None:
        picks = self._selected()
        if not picks:
            messagebox.showinfo(self.spec.info_title, self.spec.select_first, parent=self.win)
            return
        self._add(picks)

    def _add(self, picks: List[RelRow]) -> None:
        keys = list(dict.fromkeys(r.key for r in picks))
        n = self.spec.on_add(keys)
        if n:
            messagebox.showinfo(self.spec.info_title, self.spec.added_msg(n), parent=self.win)

    def _clean_selected(self) -> None:
        picks = self._selected()
        if not picks:
            messagebox.showinfo(self.spec.info_title, self.spec.select_first, parent=self.win)
            return
        self._clean(picks)

    def _clean(self, picks: List[RelRow]) -> None:
        if not messagebox.askyesno(self.spec.info_title,
                                   self.spec.confirm_clean(len(picks)), parent=self.win):
            return
        cleaned = 0
        for r in picks:
            res = self.spec.on_clean(r.key, r.token)
            if res.get("observations") or res.get("history"):
                cleaned += 1
        cleaned_keys = {r.key for r in picks}
        self._rows = [r for r in self._rows if r.key not in cleaned_keys]
        self._populate()
        messagebox.showinfo(self.spec.info_title, self.spec.cleaned_msg(cleaned), parent=self.win)
        if not self._rows:
            self.win.destroy()


# ── openers ───────────────────────────────────────────────────────────────────
def _dist(distance) -> str:
    return "—" if distance is None else f"{distance:.1f}m"


def open_eavesdropper_dialog(app, *, line_no, line_text, eavesdroppers,
                             on_add, on_clean, display_for=None) -> None:
    """Eavesdropper view for one line."""
    if not eavesdroppers:
        messagebox.showinfo(tr("旁聽者"), tr("這行對話沒有偵測到旁聽者。"), parent=app.root)
        return
    display_for = display_for or (lambda k: None)
    rows = [
        RelRow(key=e.listener_key,
               name=(display_for(e.listener_key) or e.listener_name or e.listener_id or "?"),
               detail_cols=(_dist(e.distance), e.heard_line.replace("\n", " ")[:160]),
               full_text=e.heard_line, token=e.utterance_id,
               subtitle=f"｜ {e.listener_id}　｜ {_dist(e.distance)}")
        for e in eavesdroppers
    ]
    spec = RelSpec(
        title=tr("第 {n} 行對話的旁聽者").format(n=line_no),
        subtitle=tr("原文：") + (line_text or ""),
        name_heading=tr("旁聽者"),
        detail_columns=[("dist", tr("距離"), 80, "e", False),
                        ("heard", tr("聽到的內容（失真）"), 320, "w", True)],
        rows=rows, on_add=on_add, on_clean=on_clean,
        add_bottom=tr("加入至已選角色清單"), clean_bottom=tr("🗑 刪除"),
        add_one=tr("➕ 將旁聽者加入已選角色清單"),
        add_n=lambda n: tr("➕ 將 {n} 個旁聽者加入已選角色清單").format(n=n),
        clean_one=tr("🗑 刪除旁聽者"),
        clean_n=lambda n: tr("🗑 刪除 {n} 個旁聽者").format(n=n),
        confirm_clean=lambda n: tr(
            "確定要清理這 {n} 位角色對本行對話的旁聽嗎？\n"
            "會移除他們的對話觀察，以及（若仍在）對話歷史中的旁聽行。\n"
            "（暫存，按右上「儲存」後才寫入檔案）").format(n=n),
        cleaned_msg=lambda n: tr("已清理 {n} 位旁聽者。").format(n=n),
        added_msg=lambda n: tr("已將 {n} 位旁聽者加入已選角色清單（已鎖定）。").format(n=n),
        info_title=tr("旁聽者"), select_first=tr("請先選取旁聽者。"),
        empty_preview=tr("（選擇一位旁聽者以檢視完整內容）"),
        hint=tr("提示：雙擊加入並鎖定；右鍵開啟操作選單"))
    _RelationsDialog(app, spec)


def open_sharer_dialog(app, *, line_no, line_text, sharers,
                       on_add, on_clean, display_for=None) -> None:
    """Sharer view for one line."""
    if not sharers:
        messagebox.showinfo(tr("共用者"), tr("這行對話沒有其他共用者。"), parent=app.root)
        return
    display_for = display_for or (lambda k: None)
    rows = [
        RelRow(key=s.listener_key,
               name=(display_for(s.listener_key) or s.listener_name or s.listener_id or "?"),
               detail_cols=(s.speaker or tr("（無說話者）"), s.line.replace("\n", " ")[:200]),
               full_text=s.line, token=s.content,
               subtitle=f"｜ {s.listener_id}")
        for s in sharers
    ]
    spec = RelSpec(
        title=tr("第 {n} 行對話的共用者").format(n=line_no),
        subtitle=tr("原文：") + (line_text or ""),
        name_heading=tr("共用者"),
        detail_columns=[("speaker", tr("其對話者"), 190, "w", False),
                        ("line", tr("其對話內容"), 300, "w", True)],
        rows=rows, on_add=on_add, on_clean=on_clean,
        add_bottom=tr("加入至已選角色清單"), clean_bottom=tr("🗑 刪除"),
        add_one=tr("➕ 將共用者加入已選角色清單"),
        add_n=lambda n: tr("➕ 將 {n} 個共用者加入已選角色清單").format(n=n),
        clean_one=tr("🗑 刪除共用者"),
        clean_n=lambda n: tr("🗑 刪除 {n} 個共用者").format(n=n),
        confirm_clean=lambda n: tr(
            "確定要移除這 {n} 位角色的這句共用對話嗎？\n"
            "會刪除他們對話歷史中的該行，並一併移除對應的對話觀察。\n"
            "（暫存，按右上「儲存」後才寫入檔案）").format(n=n),
        cleaned_msg=lambda n: tr("已移除 {n} 位共用者的該行對話。").format(n=n),
        added_msg=lambda n: tr("已將 {n} 位共用者加入已選角色清單（已鎖定）。").format(n=n),
        info_title=tr("共用者"), select_first=tr("請先選取共用者。"),
        empty_preview=tr("（選擇一位共用者以檢視完整內容）"),
        hint=tr("提示：雙擊加入並鎖定；右鍵開啟操作選單"))
    _RelationsDialog(app, spec)
