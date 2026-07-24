"""預覽字體設定 — one slider that scales every preview pane, with a live sample.

The editor is where players re-read their story (the in-game HUD crowds the
text), so the preview panes carry most of the reading.  A single delta is
applied to every registered preview rather than per-pane settings: the panes are
read interchangeably, and one number is one decision instead of a dozen.

The sample below the slider re-renders as you drag, because "+4" means nothing
until you see it.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from i18n import tr
from ui import preview_font
from ui.theme import tcol
from widgets.window_center import center_window


def open_preview_font_dialog(app) -> None:
    win = tk.Toplevel(app.root)
    win.title(tr("預覽字體設定"))
    win.transient(app.root)
    win.grab_set()
    center_window(win, 660, 520)

    original = preview_font.current_delta()

    ttk.Label(win, text=tr("調整主工作區、訊息與秘密、動態事件、疾病等各處預覽區的文字大小。"),
              wraplength=610, justify="left",
              foreground=tcol("#5A5A5A")).pack(anchor="w", padx=14, pady=(14, 2))
    ttk.Label(win, text=tr("清單與表單不受影響，只放大用來閱讀的預覽區。"),
              wraplength=610, justify="left",
              foreground=tcol("#9AA0A6")).pack(anchor="w", padx=14, pady=(0, 10))

    row = ttk.Frame(win)
    row.pack(fill=tk.X, padx=14, pady=(0, 4))
    ttk.Label(row, text=tr("字級增減:")).pack(side=tk.LEFT)
    value_var = tk.IntVar(value=original)
    shown = ttk.Label(row, text=preview_font.delta_text(), width=4,
                      font=("Microsoft JhengHei", 11, "bold"),
                      foreground=tcol("#1A3A5C"))
    shown.pack(side=tk.RIGHT)

    scale = ttk.Scale(win, from_=preview_font.MIN_DELTA, to=preview_font.MAX_DELTA,
                      orient=tk.HORIZONTAL)
    scale.pack(fill=tk.X, padx=14)
    ticks = ttk.Frame(win)
    ticks.pack(fill=tk.X, padx=14, pady=(0, 8))
    for i in range(preview_font.MIN_DELTA, preview_font.MAX_DELTA + 1):
        ttk.Label(ticks, text=f"+{i}" if i else "0",
                  foreground=tcol("#9AA0A6")).pack(
            side=tk.LEFT, expand=True)

    # ── live sample: a miniature of a real preview pane ──
    box = ttk.Labelframe(win, text=tr("預覽效果"))
    box.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 8))
    sample = tk.Text(box, wrap="word", relief="flat", padx=10, pady=8,
                     height=8, cursor="arrow")
    sample.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
    _BASE = ("Microsoft JhengHei", 10)
    sample.tag_configure("title", font=("Microsoft JhengHei", 12, "bold"),
                         foreground=tcol("#1A3A5C"), spacing3=4)
    sample.tag_configure("key", font=("Microsoft JhengHei", 10, "bold"),
                         foreground=tcol("#6B5B3E"))
    sample.tag_configure("body", font=_BASE, foreground=tcol("#222222"))
    sample.tag_configure("dim", font=("Microsoft JhengHei", 9, "italic"),
                         foreground=tcol("#999999"))

    def _fill():
        sample.configure(state="normal")
        sample.delete("1.0", "end")
        sample.insert("end", tr("「釤刀」蘇雷納") + "\n", "title")
        sample.insert("end", tr("戰役日") + "：", "key")
        sample.insert("end", "1084 " + tr("年") + "\n\n", "body")
        sample.insert("end", tr("她靠在冰冷的磚牆上，目光在陰影裡靜靜掃過來人，"
                                "半晌才開口——那語氣裡沒有一絲討好，卻讓人不敢移開視線。"),
                      "body")
        sample.insert("end", "\n\n" + tr("（這是預覽區的示意文字）"), "dim")
        sample.configure(state="disabled")

    _fill()

    # Scale the sample by the same rule the real previews use, without
    # registering it (it must not outlive this window).
    base_specs = {"": ("Microsoft JhengHei", 10),
                  "title": ("Microsoft JhengHei", 12, "bold"),
                  "key": ("Microsoft JhengHei", 10, "bold"),
                  "body": ("Microsoft JhengHei", 10),
                  "dim": ("Microsoft JhengHei", 9, "italic")}

    def _restyle(delta: int) -> None:
        for tag, spec in base_specs.items():
            scaled = (spec[0], spec[1] + delta) + tuple(spec[2:])
            if tag:
                sample.tag_configure(tag, font=scaled)
            else:
                sample.configure(font=scaled)

    def _on_move(_v=None):
        delta = int(round(float(scale.get())))
        if delta != value_var.get():
            value_var.set(delta)
        shown.configure(text=f"+{delta}" if delta else "0")
        _restyle(delta)

    scale.configure(command=_on_move)
    scale.set(original)
    _on_move()

    foot = ttk.Frame(win)
    foot.pack(fill=tk.X, padx=14, pady=(0, 12))

    def _reset():
        scale.set(preview_font.DEFAULT_DELTA)
        _on_move()

    ttk.Button(foot, text=tr("恢復預設"), command=_reset,
               style="secondary.TButton").pack(side=tk.LEFT)

    def _apply():
        preview_font.set_delta(app, value_var.get())
        win.destroy()

    ttk.Button(foot, text=tr("套用"), command=_apply,
               style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(foot, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)
