"""Read-only summary card for a single world-info / world-secret item.

Replaces the raw-JSON preview on the 訊息與秘密 page: an upper block of
attributes (機率 / 分類 / 適用對象 / 標籤) and a lower block with the item's
body text — styled like the main-workspace summary card for readability.

Drop-in compatible with the previous ``JsonPreview`` usage:

    w = WorldItemSummary(parent)
    w.pack(fill="both", expand=True)
    w.load(item_dict)      # render the structured summary
    w.load_text("…")       # render a plain placeholder message
    w.clear()
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Optional

from i18n import tr
from services.display_labels import applicable_npc_label as _npc_label
from ui import preview_font
from ui.theme import tcol


class WorldItemSummary(ttk.Frame):
    """Structured, read-only viewer for one info/secret dict."""

    def __init__(self, parent, **kwargs):
        # Tolerate (and ignore) the old JsonPreview kwargs e.g. read_only=…
        kwargs.pop("read_only", None)
        kwargs.pop("edit_variable", None)
        super().__init__(parent, **kwargs)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._text = tk.Text(
            body, wrap="word", state="disabled",
            font=("Microsoft JhengHei", 10),
            relief="flat", cursor="arrow",
            padx=8, pady=6, spacing1=2, spacing3=2,
        )
        vsb = ttk.Scrollbar(body, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        self._text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._configure_tags()

    # ── public API ───────────────────────────────────────────────────────────
    def load(self, data: Optional[Dict[str, Any]]) -> None:
        t = self._text
        t.configure(state="normal")
        t.delete("1.0", "end")
        if not isinstance(data, dict) or not data:
            t.insert("end", tr("（無資料）"), "empty")
            t.configure(state="disabled")
            return

        # Header — the item id.
        iid = str(data.get("id", "") or "")
        if iid:
            t.insert("end", iid + "\n", "title")

        # ── Upper block: attributes ──
        chance = data.get("usageChance", data.get("knowledgeChance"))
        category = data.get("category", data.get("accessLevel"))
        npcs = data.get("applicableNPCs") or []
        tags = data.get("tags") or []

        def kv(label: str, val: str) -> None:
            t.insert("end", f"{label}：", "key")
            t.insert("end", str(val) + "\n", "val")

        if chance is not None:
            kv(tr("機率"), chance)
        if category:
            kv(tr("分類"), category)
        if npcs:
            kv(tr("適用對象"), "、".join(_npc_label(x) for x in npcs))
        if tags:
            kv(tr("標籤"), "、".join(str(x) for x in tags))

        # ── Lower block: body text ──
        t.insert("end", "─" * 40 + "\n", "sep")
        t.insert("end", tr("內文") + "\n", "section")
        desc = str(data.get("description", "") or "").strip()
        t.insert("end", (desc if desc else tr("（無內文）")) + "\n",
                 "body" if desc else "empty")

        t.configure(state="disabled")
        t.see("1.0")

    def load_text(self, message: str) -> None:
        t = self._text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", str(message), "empty")
        t.configure(state="disabled")

    def clear(self) -> None:
        self.load_text("")

    # ── internals ────────────────────────────────────────────────────────────
    def _configure_tags(self) -> None:
        t = self._text
        t.tag_configure("title", font=("Microsoft JhengHei", 12, "bold"),
                        foreground=tcol("#1A3A5C"), spacing3=4)
        t.tag_configure("section", font=("Microsoft JhengHei", 11, "bold"),
                        foreground=tcol("#2471A3"), spacing1=6, spacing3=2)
        t.tag_configure("key", font=("Microsoft JhengHei", 10, "bold"),
                        foreground=tcol("#6B5B3E"))
        t.tag_configure("val", font=("Microsoft JhengHei", 10), foreground=tcol("#333333"))
        t.tag_configure("body", font=("Microsoft JhengHei", 10), foreground=tcol("#222222"),
                        lmargin1=8, lmargin2=8, spacing1=2, spacing3=2)
        t.tag_configure("sep", foreground=tcol("#BBBBBB"))
        t.tag_configure("empty", font=("Microsoft JhengHei", 10, "italic"),
                        foreground=tcol("#999999"))
        preview_font.register(t)
