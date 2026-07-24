"""Regression: detail-viewer scroll preservation (主工作區預覽分頁).

Verifies that each viewer RESETS scroll on a character switch but PRESERVES it
on a same-character re-render (an edit) — the v0.24.2 "編輯後亂跳" fix.

We record whether the viewer called ``Text.see`` (reset) or ``Text.yview_moveto``
(preserve) on its last render, which captures the control flow without needing
real pixel geometry.

Run: python scripts/detail_scroll_check.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widgets.conversation_history_page import ConversationHistoryPage  # noqa: E402
from widgets.owned_items_viewer import OwnedItemsViewer  # noqa: E402
from widgets.recent_events_viewer import RecentEventsViewer  # noqa: E402
from widgets.summary_card import SummaryCard  # noqa: E402

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} - {label}: {got}")
    if not ok:
        print(f"        want: {want}")
        FAILS.append(label)


def attach_recorder(text):
    calls = []
    text.see = lambda *a, **k: calls.append("reset")
    text.yview_moveto = lambda *a, **k: calls.append("preserve")
    return calls


def attach_tree_recorder(tree):
    """Same idea for Treeview-based viewers (see → reset, yview_moveto → keep)."""
    calls = []
    tree.see = lambda *a, **k: calls.append("reset")
    tree.yview_moveto = lambda *a, **k: calls.append("preserve")
    return calls


def _noop(*a, **k):
    pass


def main():
    root = tk.Tk()
    root.geometry("600x400")

    ev = tk.BooleanVar(value=False)

    # ── Conversation history page (Treeview list since v1.1.0) ───────────────
    cv = ConversationHistoryPage(
        root, on_delete=_noop, on_sync_menu=_noop, on_sync_all=_noop,
        on_insert=_noop, on_edit_line=_noop, edit_variable=ev)
    entries = [f"玩家 (`main_hero`): line {i}" for i in range(40)]
    rec = attach_tree_recorder(cv._tree)
    cv.load(entries, npc_name="alice"); check("conv new char", rec[-1], "reset")
    cv._refresh_list();                  check("conv edit re-render", rec[-1], "preserve")
    cv.load(entries, npc_name="alice");  check("conv same char reload", rec[-1], "preserve")
    cv.load(entries, npc_name="bob");    check("conv switch char", rec[-1], "reset")

    # ── Owned items viewer ────────────────────────────────────────────────────
    ov = OwnedItemsViewer(
        root, kind="info", kind_label="訊息", on_stage_add=_noop, on_stage_remove=_noop,
        on_commit=_noop, on_discard=_noop, get_pending=lambda *a, **k: [], edit_variable=ev)
    items = [{"id": f"i{i}", "description": f"d{i}"} for i in range(40)]
    owned = [f"i{i}" for i in range(40)]
    rec = attach_recorder(ov._text)
    ov.load(owned, items, npc_name="alice"); check("owned new char", rec[-1], "reset")
    ov._render();                            check("owned edit re-render", rec[-1], "preserve")
    ov.load(owned, items, npc_name="alice"); check("owned same char reload", rec[-1], "preserve")
    ov.load(owned, items, npc_name="bob");   check("owned switch char", rec[-1], "reset")

    # ── Recent events viewer ──────────────────────────────────────────────────
    rv = RecentEventsViewer(root, on_delete=_noop, on_clear=_noop, edit_variable=ev)
    events = [{"type": "事件", "description": f"e{i}"} for i in range(40)]
    rec = attach_recorder(rv._text)
    rv.load(events, npc_name="alice"); check("recent new char", rec[-1], "reset")
    rv._render();                      check("recent edit re-render", rec[-1], "preserve")
    rv.load(events, npc_name="alice"); check("recent same char reload", rec[-1], "preserve")
    rv.load(events, npc_name="bob");   check("recent switch char", rec[-1], "reset")

    # ── Summary card ──────────────────────────────────────────────────────────
    sc = SummaryCard(root, on_field_save=_noop, on_quick_clear=lambda k, f: None,
                     on_attr_edit=_noop,
                     resolve_character_name=lambda sid: sid, edit_variable=ev)
    data_a = {"StringId": "alice", "CharacterDescription": "x" * 400}
    data_b = {"StringId": "bob", "CharacterDescription": "y" * 400}
    rec = attach_recorder(sc._text)
    sc.load(data_a); check("summary new char", rec[-1], "reset")
    sc._re_render(); check("summary edit re-render", rec[-1], "preserve")
    sc.load(data_a); check("summary same char reload", rec[-1], "preserve")
    sc.load(data_b); check("summary switch char", rec[-1], "reset")

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] detail_scroll check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] detail_scroll check passed")


if __name__ == "__main__":
    main()
