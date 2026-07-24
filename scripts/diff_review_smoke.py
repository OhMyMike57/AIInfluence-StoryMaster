"""Smoke: generic 儲存前對照檢查 dialog + the three tab diff builders (v0.37.3).

Verifies open_diff_review_dialog renders grouped rows headlessly and that the
disease / dynamic / world diff builders produce well-formed [{name,field,old,
new}] rows from representative pending state. Bind the real builder methods to a
Stub (no Tk app) so we exercise the actual logic.

Run: python scripts/diff_review_smoke.py
"""
import os
import sys
import types
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import StoryMaster as A                                 # noqa: E402
from dialogs.staging_commit_dialog import open_diff_review_dialog  # noqa: E402
from services.diff_summary import field_label, summarize_change    # noqa: E402


def _text(field, old, new):
    """Flatten summarize_change segments to a single string for assertions."""
    return "".join(t for t, _tag in summarize_change(field, old, new))


def _tag_of(field, old, new, needle):
    """Return the tag of the first segment whose text contains *needle*."""
    for t, tag in summarize_change(field, old, new):
        if needle in t:
            return tag
    return None

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def _rows_ok(rows):
    return isinstance(rows, list) and all(
        {"name", "field", "old", "new"} <= set(r) for r in rows)


def main():
    root = tk.Tk()
    root.withdraw()

    # ── generic dialog renders grouped rows + fires on_confirm ───────────────
    fired = {"n": 0}
    diff = [
        {"name": "角色A", "field": "浪漫", "old": 0, "new": 40},
        {"name": "角色A", "field": "info", "old": [1, 2], "new": [1, 2, 3]},
        {"name": "角色B", "field": "信任", "old": 0.1, "new": 0.5},
    ]

    class _App:
        pass
    app = _App(); app.root = root
    open_diff_review_dialog(app, title="t", header="h", diff_items=diff,
                            confirm_label="ok", on_confirm=lambda: fired.__setitem__("n", 1))
    tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    check("diff dialog opened a toplevel", bool(tops))
    for w in tops:
        w.destroy()

    Stub = A.AIInfluenceStoryToolsApp

    # ── disease diff builder ────────────────────────────────────────────────
    ds = types.SimpleNamespace(
        disease_pending=[
            {"op": "assign", "hero_display": "埃爾加", "disease_name": "痢疾"},
            {"op": "remove", "hero_display": "貝卡", "disease_name": "熱病", "target_type": 0},
            {"op": "clear_infections", "disease_name": "瘟疫"},
            {"op": "purge_definition", "disease_name": "舊病"},
        ])
    rows = Stub._disease_build_diff_items(ds)
    check("disease builder → 4 well-formed rows", _rows_ok(rows) and len(rows) == 4)
    check("disease assign is a green add (old empty)",
          any(r["field"].endswith("感染") and r["old"] == "" and r["new"] == "痢疾" for r in rows))
    check("disease catalog ops grouped under 疾病目錄",
          sum(1 for r in rows if r["name"] == "疾病目錄") == 2)

    # ── dynamic diff builder ────────────────────────────────────────────────
    dy = types.SimpleNamespace(
        dyn_events_pending={
            "edits": {"evt-123456789": {"title": 1, "severity": 1}},
            "delete_ids": {"evt-dead0001"},
            "new_events": [{"title": "新事件"}],
            "stmt_edits": {}, "stmt_deletes": set(),
            "stmt_new": [{"kingdom_id": "vlandia"}],
            "pressure": {"PressureByKingdomId": {"a": 1, "b": 2}},
        })
    rows = Stub._dyn_build_diff_items(dy)
    check("dynamic builder → well-formed rows", _rows_ok(rows))
    check("dynamic has delete/edit/new event rows + pressure",
          len(rows) == 5)
    check("dynamic pressure row names 回應壓力",
          any(r["name"] == "回應壓力" and "2" in str(r["new"]) for r in rows))

    # ── world diff builder ──────────────────────────────────────────────────
    wd = types.SimpleNamespace(
        world_info_items=[{"id": "i1", "content": "改後內容"}, {"id": "i3", "content": "全新"}],
        world_info_original=[{"id": "i1", "content": "原內容"}, {"id": "i2", "content": "將被移除"}],
        world_secrets_items=[], world_secrets_original=[],
        known_info_owners={}, known_secret_owners={}, characters=[])
    rows = Stub._world_build_diff_items(wd)
    check("world builder → well-formed rows", _rows_ok(rows))
    # i1 edited, i2 removed, i3 added → 3 rows (no owners/secrets here)
    check("world detects add/remove/edit (3 rows)", len(rows) == 3)
    check("world edit row carries old & new content",
          any("i1" in r["field"] and r["old"] == "原內容" and r["new"] == "改後內容" for r in rows))

    # ── diff_summary summariser (v0.37.4) ───────────────────────────────────
    check("field_label translates known keys", field_label("ConversationHistory") == "對話")
    check("field_label passes unknown keys through", field_label("SomeRawKey") == "SomeRawKey")

    # short scalars keep old → new, new value green
    check("scalar keeps old→new", _text("RomanceLevel", 0, 40) == "0  →  40")
    check("scalar new value tagged green", _tag_of("RomanceLevel", 0, 40, "40") == "new")

    # long text → action + count, never dumps the blob
    lt = _text("AIGeneratedPersonality", "甲" * 1024, "乙" * 1187)
    check("long text edit summarised", "編輯文本" in lt and "1024" in lt and "1187" in lt)
    check("long text edit does not dump content", "甲" not in lt and "乙" not in lt)
    check("long text add", "新增文本" in _text("AIGeneratedPersonality", "", "丙" * 100))
    check("long text clear", "清空文本" in _text("AIGeneratedPersonality", "丁" * 100, ""))

    # list: editing one line of 8 reads as「編輯 1 行」(not ＋1／−1)
    base = [f"line{i}" for i in range(8)]
    edited = list(base); edited[3] = "line3-changed"
    check("conversation edit-1-line → 編輯 1 行",
          _text("ConversationHistory", base, edited) == "✏ 編輯 1 行")
    check("list delete → 刪除 N 項",
          _text("KnownInfo", ["a", "b", "c"], ["a", "c"]) == "🗑 刪除 1 項")
    check("list add → 新增 N 項",
          _text("KnownInfo", ["a"], ["a", "b", "c"]) == "➕ 新增 2 項")

    # social nested dict surfaces the scalar change
    st = _text("CounterpartySocial",
               {"main_hero": {"trust_level": 0.1}}, {"main_hero": {"trust_level": 0.5}})
    check("social dict surfaces 信任 0.1→0.5", "信任" in st and "0.1" in st and "0.5" in st)

    # generic dict → 設定 / 清空
    check("dict set", _text("EmotionalState", None, {"Mood": "calm"}) == "設定")
    check("dict clear", _text("EmotionalState", {"Mood": "calm"}, None) == "清空")

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] diff_review smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] diff_review smoke passed")


if __name__ == "__main__":
    main()
