"""Line bookkeeping for the 編寫 N 個對話行 editor.

The editor is opened on a *subset* of the conversation — pick lines 3, 10 and
47, edit them side by side, append a line, delete another.  Everything not loaded must come back untouched, and the line numbers
shown next to the loaded rows must be the numbers those lines will really have
once the edit is committed.

The model is deliberately small:

* a row that came from the history remembers its ``origin`` (0-based index);
* a row the user inserted has ``origin=None`` and instead hangs off a loaded
  row — ``anchor`` (that row's origin) plus ``side`` ("before"/"after"), which
  is exactly the button that created it (⬆＋ / ⬇＋).  A row inserted next to
  another *inserted* row inherits its anchor and takes its place in list order;
* a deleted row keeps its place in the list with ``deleted=True`` so the user
  can see (and undo) the deletion, but contributes no line.

Anchoring rather than absolute positions is what makes a sparse selection work.
"Insert below line 3" is unambiguous even when line 4 was never loaded, whereas
"insert at position 4" would have to guess whether the user meant before or
after the 40 lines they never saw.

:func:`layout` is the single source of truth — both the numbers on screen and
the committed history come from the same walk, so they cannot disagree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

BEFORE = "before"
AFTER = "after"


@dataclass
class Row:
    """One line in the editor.  ``text`` is the finished line (prefix included)."""
    text: str = ""
    origin: Optional[int] = None
    anchor: Optional[int] = None
    side: str = AFTER
    deleted: bool = False

    @property
    def is_new(self) -> bool:
        return self.origin is None


def layout(rows: Sequence[Row], total: int) -> List[Tuple[str, int]]:
    """The committed order, as ``("row", row_index)`` / ``("orig", ch_index)``.

    ``("orig", i)`` means "line i of the original history, which was never
    loaded and is passed through unchanged".
    """
    before: Dict[int, List[int]] = {}
    after: Dict[int, List[int]] = {}
    tail: List[int] = []
    loaded: Dict[int, int] = {}

    for ri, r in enumerate(rows):
        if r.origin is not None:
            loaded[r.origin] = ri
        elif r.anchor is None:
            # Nothing to hang off (an empty history, or "add a line at the end").
            tail.append(ri)
        elif r.side == BEFORE:
            before.setdefault(r.anchor, []).append(ri)
        else:
            after.setdefault(r.anchor, []).append(ri)

    def live(indices):
        # An insert survives the deletion of the row it was anchored to — it is
        # a line the user wrote, not a decoration on the anchor.  It does not
        # survive its own deletion.
        return [("row", ri) for ri in indices if not rows[ri].deleted]

    out: List[Tuple[str, int]] = []
    for o in range(total):
        out.extend(live(before.get(o, ())))
        ri = loaded.get(o)
        if ri is None:
            out.append(("orig", o))
        elif not rows[ri].deleted:
            out.append(("row", ri))
        out.extend(live(after.get(o, ())))
    out.extend(live(tail))
    return out


def line_numbers(rows: Sequence[Row], total: int) -> List[Optional[int]]:
    """1-based final line number per row; ``None`` for a deleted row."""
    numbers: List[Optional[int]] = [None] * len(rows)
    for pos, (kind, ref) in enumerate(layout(rows, total), start=1):
        if kind == "row":
            numbers[ref] = pos
    return numbers


def merge(rows: Sequence[Row], original: Sequence[Any]) -> List[str]:
    """The full new ConversationHistory."""
    src = [e if isinstance(e, str) else str(e) for e in original]
    out: List[str] = []
    for kind, ref in layout(rows, len(src)):
        out.append(src[ref] if kind == "orig" else rows[ref].text)
    return out


def is_dirty(rows: Sequence[Row], original: Sequence[Any]) -> bool:
    """Did anything change — text, insertions or deletions?"""
    src = [e if isinstance(e, str) else str(e) for e in original]
    return merge(rows, src) != src


def new_row_beside(rows: List[Row], index: int, side: str) -> Row:
    """Build the row that ⬆＋ / ⬇＋ on ``rows[index]`` should insert.

    It inherits the neighbour's anchor when that neighbour is itself an
    inserted row, so a chain of inserts stays attached to the same real line.
    (The speaker prefix is copied by the dialog, which owns that widget.)
    """
    ref = rows[index]
    anchor = ref.origin if ref.origin is not None else ref.anchor
    return Row(text="", origin=None, anchor=anchor,
               side=(ref.side if ref.origin is None else side))


def insert_position(rows: List[Row], index: int, side: str) -> int:
    """Where in the *display list* a ⬆＋/⬇＋ row goes.

    Rows anchored to the same line keep display order, and display order is
    what :func:`layout` reads, so inserting at the neighbouring slot is all
    that is needed to make repeated inserts stack in the order they were made.
    """
    return index if side == BEFORE else index + 1
