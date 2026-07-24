"""Regression: 完整編寫／編寫 N 個對話行 line bookkeeping (v1.1.0 R4-S5).

The editor can be opened on a sparse selection of a long history, so the two
things that must never be wrong are:

  1. the line number shown beside a row is the number that line really gets;
  2. everything the user did not load comes back byte-identical.

Both come from ``compose_plan.layout``, so both are checked together over
contiguous selections, sparse selections, insert chains, head/tail inserts,
deleting everything, and deleting a row that other inserts hang off.

Run: python scripts/compose_plan_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.compose_plan import (  # noqa: E402
    AFTER, BEFORE, Row, is_dirty, layout, line_numbers, merge, new_row_beside,
    insert_position,
)

FAILS = []
CH = [f"L{i}" for i in range(10)]      # L0 … L9


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def loaded(*origins):
    return [Row(text=CH[o], origin=o) for o in origins]


def main():
    # ── nothing touched ───────────────────────────────────────────────
    rows = loaded(*range(10))
    check("full load, no edits → identical", merge(rows, CH) == CH)
    check("full load numbers are 1..10", line_numbers(rows, 10) == list(range(1, 11)))
    check("no edits → not dirty", is_dirty(rows, CH) is False)

    rows = loaded(2, 5, 8)
    check("sparse load, no edits → identical", merge(rows, CH) == CH)
    check("sparse load shows real line numbers", line_numbers(rows, 10) == [3, 6, 9])

    # ── editing text ──────────────────────────────────────────────────
    rows = loaded(2, 5, 8)
    rows[1].text = "改過的 L5"
    out = merge(rows, CH)
    check("edit replaces only that line",
          out[5] == "改過的 L5" and out[:5] == CH[:5] and out[6:] == CH[6:])
    check("editing text does not move anything", line_numbers(rows, 10) == [3, 6, 9])
    check("an edit is dirty", is_dirty(rows, CH) is True)

    # ── inserting ─────────────────────────────────────────────────────
    # below line 3 (origin 2) in a sparse selection: lands at 4, not "before 6"
    rows = loaded(2, 5, 8)
    rows.insert(insert_position(rows, 0, AFTER), new_row_beside(rows, 0, AFTER))
    rows[1].text = "新行"
    check("insert below a sparse row lands right after it",
          merge(rows, CH) == CH[:3] + ["新行"] + CH[3:])
    check("numbers shift only after the insert",
          line_numbers(rows, 10) == [3, 4, 7, 10])

    # above line 6 (origin 5) — the other side of the same gap
    rows = loaded(2, 5, 8)
    rows.insert(insert_position(rows, 1, BEFORE), new_row_beside(rows, 1, BEFORE))
    rows[1].text = "新行"
    check("insert above a sparse row lands right before it",
          merge(rows, CH) == CH[:5] + ["新行"] + CH[5:])

    # a chain: three inserts below the same row keep their order
    rows = loaded(2, 5)
    for n, label in enumerate(("A", "B", "C")):
        i = n                        # each new row is added below the previous
        rows.insert(insert_position(rows, i, AFTER), new_row_beside(rows, i, AFTER))
        rows[i + 1].text = label
    check("an insert chain keeps the order it was typed in",
          merge(rows, CH) == CH[:3] + ["A", "B", "C"] + CH[3:])
    check("chained inserts stay anchored to the real line",
          all(r.anchor == 2 for r in rows if r.is_new))
    check("chain numbering is consecutive",
          line_numbers(rows, 10) == [3, 4, 5, 6, 9])

    # head and tail
    rows = loaded(0, 9)
    rows.insert(0, new_row_beside(rows, 0, BEFORE))
    rows[0].text = "開頭"
    rows.append(new_row_beside(rows, len(rows) - 1, AFTER))
    rows[-1].text = "結尾"
    check("insert before the first line", merge(rows, CH)[0] == "開頭")
    check("insert after the last line", merge(rows, CH)[-1] == "結尾")
    check("head/tail numbering", line_numbers(rows, 10) == [1, 2, 11, 12])

    # ── deleting ──────────────────────────────────────────────────────
    rows = loaded(2, 5, 8)
    rows[1].deleted = True
    check("delete removes just that line", merge(rows, CH) == CH[:5] + CH[6:])
    check("a deleted row has no number", line_numbers(rows, 10) == [3, None, 8])

    rows = loaded(*range(10))
    for r in rows:
        r.deleted = True
    check("deleting every loaded row empties the history", merge(rows, CH) == [])
    check("all-deleted rows have no numbers",
          line_numbers(rows, 10) == [None] * 10)

    # inserts survive the deletion of the row they hang off
    rows = loaded(2, 5)
    rows.insert(insert_position(rows, 0, AFTER), new_row_beside(rows, 0, AFTER))
    rows[1].text = "留下來"
    rows[0].deleted = True
    check("an insert survives its anchor being deleted",
          merge(rows, CH) == CH[:2] + ["留下來"] + CH[3:])
    check("numbers after an anchor deletion",
          line_numbers(rows, 10) == [None, 3, 6])

    # …but it does not survive its OWN deletion.  The editor drops an inserted
    # row outright when you press ✗, yet it also marks a row left completely
    # blank as deleted at commit time — that path goes through here.
    rows = loaded(2, 5)
    rows.insert(insert_position(rows, 0, AFTER), new_row_beside(rows, 0, AFTER))
    rows[1].text = "空白被丟掉"
    rows[1].deleted = True
    check("a deleted insert contributes nothing", merge(rows, CH) == CH)
    check("a deleted insert has no number", line_numbers(rows, 10) == [3, None, 6])

    # delete + insert on the same row, mixed
    rows = loaded(1, 4, 7)
    rows[0].deleted = True
    rows.insert(insert_position(rows, 2, BEFORE), new_row_beside(rows, 2, BEFORE))
    rows[2].text = "插在7之前"
    rows[3].text = "改7"
    out = merge(rows, CH)
    check("mixed delete + insert",
          out == ["L0", "L2", "L3", "L4", "L5", "L6", "插在7之前", "改7", "L8", "L9"])
    check("mixed numbering", line_numbers(rows, 10) == [None, 4, 7, 8])

    # ── empty history ─────────────────────────────────────────────────
    rows = [Row(text="第一行", origin=None, anchor=None)]
    check("rows with no anchor append at the end", merge(rows, []) == ["第一行"])
    check("unanchored row is numbered", line_numbers(rows, 0) == [1])

    # ── layout is the single source of truth ──────────────────────────
    rows = loaded(1, 4, 7)
    rows.insert(2, new_row_beside(rows, 1, AFTER))
    rows[2].text = "X"
    rows[0].deleted = True
    nums = line_numbers(rows, 10)
    out = merge(rows, CH)
    ok = all(n is None or out[n - 1] == rows[i].text
             for i, n in enumerate(nums))
    check("every shown number points at that row's own text in the result", ok)
    check("layout length == merged length", len(layout(rows, 10)) == len(out))

    print()
    if FAILS:
        print(f"[FAIL] compose plan check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] compose plan check passed")


if __name__ == "__main__":
    main()
