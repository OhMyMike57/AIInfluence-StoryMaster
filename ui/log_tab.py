from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from i18n import tr


def build_log_tab(app, notebook: ttk.Notebook) -> None:
    log_tab = ttk.Frame(notebook)
    notebook.add(log_tab, text=tr("📜 日誌"))

    log_toolbar = ttk.Frame(log_tab)
    log_toolbar.pack(fill=tk.X, padx=8, pady=8)

    ttk.Button(log_toolbar, text=tr("清除"), command=app.clear_log, style="secondary.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(log_toolbar, text=tr("匯出"), command=app.export_log, style="secondary.TButton").pack(side=tk.LEFT, padx=2)

    ttk.Label(log_toolbar, text=tr("搜尋:")).pack(side=tk.LEFT, padx=(20, 5))
    app.log_search_var = tk.StringVar()
    ttk.Entry(log_toolbar, textvariable=app.log_search_var, width=30).pack(side=tk.LEFT)
    ttk.Button(log_toolbar, text="🔍", command=app.search_log, style="secondary.TButton").pack(side=tk.LEFT, padx=2)

    log_container = ttk.Frame(log_tab)
    log_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    app.log_text = tk.Text(log_container, wrap="word", state="disabled")
    app.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll = ttk.Scrollbar(log_container, command=app.log_text.yview)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    app.log_text.configure(yscrollcommand=log_scroll.set)
