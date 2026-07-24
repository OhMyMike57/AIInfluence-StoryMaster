"""Review-and-confirm dialog for the global staging commit (v0.36.0).

Shows the field-level diff of every staged character document, grouped by
character, then hands control back via ``on_confirm`` when the user hits
💾 全部儲存.  All-or-nothing by design — partial commits would silently
re-merge working copies and confuse the "one save writes what you saw" model.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Tuple

from i18n import tr
from services import snapshot_service as svc_snapshot
from services.diff_summary import field_label, summarize_change
from widgets.window_center import center_window
from ui.theme import tcol


def open_diff_review_dialog(app, *, title: str, header: str,
                            diff_items: List[Dict[str, Any]],
                            confirm_label: str,
                            on_confirm: Callable[[], None],
                            options: List[Dict[str, Any]] | None = None,
                            width: int = 860, height: int = 560) -> None:
    """Generic「儲存前對照檢查」dialog, reused by every staged-save flow.

    *diff_items*: ``[{name, field, old, new}]`` — rows are grouped by ``name``
    (a character, a world file, an event…) and each shows an ``old → new``
    field change with the new value coloured green.  ``header`` is the bold
    intro line; ``confirm_label`` is the primary button text.  ``on_confirm``
    runs after the window closes.

    *options*: optional ``[{label, hint, var}]`` rows shown above the buttons.
    With ``var`` (a caller-owned ``tk.BooleanVar``) the row is a checkbox the
    caller reads inside its own ``on_confirm``; without one it is a plain
    informational line.  Either way this function's contract is unchanged.
    """
    win = tk.Toplevel(app.root)
    win.title(title)
    win.transient(app.root)
    win.grab_set()
    # Option rows are fixed-height; grow the window for them rather than letting
    # them eat into the diff body.
    center_window(win, width, height + 58 * len(options or []))

    by_name: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for it in diff_items:
        key = str(it.get("name") or it.get("path"))
        if key not in by_name:
            by_name[key] = []
            order.append(key)
        by_name[key].append(it)

    ttk.Label(win, text=header,
              font=("Microsoft JhengHei", 11, "bold"),
              foreground=tcol("#1A3A5C")).pack(anchor="w", padx=14, pady=(12, 4))

    # Pack the fixed-height furniture (buttons, option rows) BEFORE the diff
    # body: pack hands out space in call order, so whatever is packed last gets
    # squeezed when the window is smaller than the natural sizes — and the Text
    # widget's natural height (24 lines) always makes it smaller.  Options packed
    # last is exactly how their hint text got clipped off the bottom edge.
    def _do():
        win.destroy()
        on_confirm()

    foot = ttk.Frame(win)
    foot.pack(fill=tk.X, padx=12, pady=(4, 12), side=tk.BOTTOM)
    # side=RIGHT packs rightmost-first → confirm first (right), 取消 second (left).
    ttk.Button(foot, text=confirm_label, command=_do,
               style="success.TButton").pack(side=tk.RIGHT, padx=4)
    ttk.Button(foot, text=tr("取消"), command=win.destroy,
               style="secondary.TButton").pack(side=tk.RIGHT, padx=4)

    if options:
        opt_frame = ttk.Frame(win)
        opt_frame.pack(fill=tk.X, padx=14, pady=(8, 2), side=tk.BOTTOM)
        for opt in options:
            var = opt.get("var")
            if var is not None:
                ttk.Checkbutton(opt_frame, text=opt["label"], variable=var).pack(anchor="w")
                indent = 22
            else:
                ttk.Label(opt_frame, text=opt["label"],
                          font=("Microsoft JhengHei", 10, "bold"),
                          foreground=tcol("#1A3A5C")).pack(anchor="w")
                indent = 0
            hint = opt.get("hint")
            if hint:
                ttk.Label(opt_frame, text=hint, foreground=tcol("#9AA0A6"),
                          font=("Microsoft JhengHei", 9), wraplength=width - 60,
                          justify="left").pack(anchor="w", padx=(indent, 0), pady=(1, 0))

    body = ttk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
    txt = tk.Text(body, wrap="none", font=("Microsoft JhengHei", 10),
                  relief="flat", padx=10, pady=8, cursor="arrow")
    vsb = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
    hsb = ttk.Scrollbar(body, orient="horizontal", command=txt.xview)
    txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    hsb.pack(side=tk.BOTTOM, fill=tk.X)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    txt.tag_configure("char", font=("Microsoft JhengHei", 11, "bold"),
                      foreground=tcol("#1A3A5C"), spacing1=8, spacing3=2)
    txt.tag_configure("field", font=("Microsoft JhengHei", 10, "bold"),
                      foreground=tcol("#884EA0"))
    txt.tag_configure("chg", foreground=tcol("#777777"))
    txt.tag_configure("new", foreground=tcol("#1A8A4A"),
                      font=("Microsoft JhengHei", 10, "bold"))
    txt.tag_configure("muted", foreground=tcol("#9AA0A6"),
                      font=("Microsoft JhengHei", 9))

    for key in order:
        txt.insert("end", f"▋ {key}\n", "char")
        for it in by_name[key]:
            field = it["field"]
            lbl = field_label(field)
            txt.insert("end", f"    {lbl}", "field")
            if lbl != field:                       # show raw key for reference
                txt.insert("end", f" ({field})", "muted")
            txt.insert("end", "　", "chg")
            for seg_text, seg_tag in summarize_change(field, it["old"], it["new"]):
                txt.insert("end", seg_text, seg_tag)
            txt.insert("end", "\n")
    txt.configure(state="disabled")


def snapshot_purge_option(app, on_confirm: Callable[[], None]
                          ) -> Tuple[List[Dict[str, Any]], Callable[[], None]]:
    """Tell the user the mod's save-snapshots will be cleared by this save.

    The clearing itself is done by ``app._apply_snapshot_policy`` at the write
    choke point, so it covers the immediate-write paths (conversation editing,
    memory page…) that never open a dialog.  That makes a per-save checkbox
    here a lie — unticking it could not stop the purge — so this contributes an
    informational row instead, and *on_confirm* is passed straight through.

    Returns ``(options, on_confirm)`` for :func:`open_diff_review_dialog`.
    Nothing is shown when the policy is off, or when the campaign has no
    snapshots (5.x saves, or already cleared this session).
    """
    campaign_dir = getattr(app, "campaign_dir", None)
    policy = svc_snapshot.normalize_policy((getattr(app, "settings", None) or {}).get("snapshot_policy"))
    if policy != svc_snapshot.POLICY_AUTO_CLEAR:
        return [], on_confirm
    snapshots = svc_snapshot.list_snapshots(campaign_dir)
    if not snapshots:
        return [], on_confirm

    options = [{
        "label": tr("儲存後將清除此戰役的存檔備份（{n} 個存檔槽）").format(n=len(snapshots)),
        "hint": tr("這是《AI效應》模組在遊戲存檔時自動產生的備份，載入時會覆蓋整個戰役資料夾；"
                   "不清除的話，這次的編輯會在下次載入遊戲時被還原掉。"
                   "（與本工具的備份中心無關；可在 設定 → 偏好設定 → 存檔備份處理 調整）"),
    }]
    return options, on_confirm


def open_staging_commit_dialog(app, diff_items: List[Dict[str, Any]],
                               on_confirm: Callable[[], None]) -> None:
    """*diff_items*: ``[{path, name, field, old, new}]`` from DocStaging.diff_all."""
    n_files = len({str(it.get("name") or it.get("path")) for it in diff_items})
    options, confirm = snapshot_purge_option(app, on_confirm)
    open_diff_review_dialog(
        app,
        title=tr("儲存暫存變更"),
        header=tr("將寫入 {n_files} 個角色檔案（寫入前自動備份）：").format(n_files=n_files),
        diff_items=diff_items,
        confirm_label=tr("💾 全部儲存（{n_files} 檔）").format(n_files=n_files),
        on_confirm=confirm,
        options=options,
    )
