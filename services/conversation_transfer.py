"""對話歷史 export / import — Markdown files and clipboard payloads.

Pure and Tk-free so the formats can be round-trip tested headless.

Why the Markdown looks the way it does
--------------------------------------
The old export (``export_service.build_export_lines``) stripped the speaker
prefix with ``entry.replace(f"{speaker}:", "")`` and wrote ``**名字:** 內容``.
That is fine to *read* and impossible to import: the prefix shapes AI Influence
actually writes — ``[Overheard nearby, day 91114, approx. 2.7m, dialog/player]
名字 (`id`)``, ``[BATTLE_ORDER][A vs B] 名字``, ``I (名字, `id`)``, ``MEMORY
(day N)`` — cannot be rebuilt from a display name, and prose containing ``*``
or ``_`` came back mangled.

So each line is written as a numbered heading (readable) plus a **fenced block
holding the line verbatim** (importable)::

    ## [4] 💬 其他角色 · 埃爾加

    ~~~
    埃爾加 (`bloodraven_elga`): *坐起身*
    ~~~

Tilde fences, not backticks: every speaker prefix contains backticks around the
id, and a ``~~~`` at the start of a dialogue line is not a thing that happens.
Inside the fence nothing is escaped or interpreted, so ``*坐起身*`` survives as
itself and multi-line entries keep their newlines.

Clipboard payloads
------------------
* **全部** — the exact ``"ConversationHistory": [ … ]`` fragment from the JSON,
  so it can be pasted straight into an editor or back into this tool.
* **選擇行** — ``[#12] 完整原文`` per entry; importing those patches *only*
  those line numbers, which is what you want after asking an AI to rewrite
  three lines out of two hundred.

``parse_clipboard`` accepts all of the above plus a bare JSON array, deciding
by shape rather than asking the user which one they copied.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

FENCE = "~~~"

_MD_HEAD_RE = re.compile(r"^##\s*\[(\d+)\]", re.M)
_CLIP_LINE_RE = re.compile(r"^\[#(\d+)\]\s?(.*)$")
_CH_FRAGMENT_RE = re.compile(r'"ConversationHistory"\s*:\s*\[', re.S)


class TransferError(ValueError):
    """Raised when a payload cannot be understood; the message is user-facing."""


@dataclass
class ImportResult:
    """What a parsed payload asks us to do.

    ``kind`` is ``"replace"`` (*entries* is the whole new ConversationHistory)
    or ``"patch"`` (*updates* maps a 0-based index to its new line).
    """
    kind: str
    entries: List[str] = field(default_factory=list)
    updates: Dict[int, str] = field(default_factory=dict)
    source: str = ""          # a key the UI turns into a literal tr() label


# ── helpers ───────────────────────────────────────────────────────────────────
def _as_text(entry: Any) -> str:
    """A conversation entry as the text we store/transfer.

    Entries are strings in every save we have seen; a stray dict is dumped as
    JSON rather than dropped, and comes back as that JSON string.
    """
    return entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)


def _coerce_entries(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        raise TransferError("not-a-list")
    return [_as_text(e) for e in raw]


# ── Markdown ──────────────────────────────────────────────────────────────────
def build_markdown(
    npc_name: str,
    entries: Sequence[Any],
    *,
    header: str = "",
    note: str = "",
    row_label: Optional[Callable[[int, str], str]] = None,
) -> str:
    """Render *entries* as the importable Markdown described in the module docs.

    *row_label* renders the readable part of each heading (badge, category and
    speaker) — it lives in the UI layer because those strings are localised.
    Without it the headings carry the line number alone, which still imports.
    """
    out: List[str] = []
    out.append(f"# {header or npc_name}")
    out.append("")
    if note:
        out.append(note)
        out.append("")
    for i, entry in enumerate(entries):
        text = _as_text(entry)
        label = ""
        if row_label:
            try:
                label = (row_label(i, text) or "").strip()
            except Exception:
                label = ""
        out.append(f"## [{i + 1}]" + (f" {label}" if label else ""))
        out.append("")
        out.append(FENCE)
        out.append(text)
        out.append(FENCE)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def parse_markdown(text: str) -> List[str]:
    """Read :func:`build_markdown` output back into a ConversationHistory list.

    Entries come back in *heading order*, renumbered on import — so deleting a
    whole ``## [n]`` block deletes that line, and duplicating one duplicates it,
    without the user having to renumber anything by hand.
    """
    if not (text or "").strip():
        raise TransferError("empty")
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    entries: List[str] = []
    i = 0
    seen_heading = False
    while i < len(lines):
        if not _MD_HEAD_RE.match(lines[i]):
            i += 1
            continue
        seen_heading = True
        # Take the first fenced block before the next heading.
        i += 1
        body: Optional[List[str]] = None
        while i < len(lines) and not _MD_HEAD_RE.match(lines[i]):
            if lines[i].strip() == FENCE:
                i += 1
                buf: List[str] = []
                while i < len(lines) and lines[i].strip() != FENCE:
                    buf.append(lines[i])
                    i += 1
                if i >= len(lines):
                    raise TransferError("unclosed-fence")
                i += 1               # consume the closing fence
                body = buf
                break
            i += 1
        if body is None:
            raise TransferError("missing-fence")
        entries.append("\n".join(body).strip("\n"))

    if not seen_heading:
        raise TransferError("no-headings")
    return entries


# ── clipboard ─────────────────────────────────────────────────────────────────
def build_clipboard_all(entries: Sequence[Any]) -> str:
    """The ``"ConversationHistory": [ … ]`` fragment, formatted like the save."""
    body = json.dumps(_coerce_entries(list(entries)), ensure_ascii=False, indent=2)
    return f'"ConversationHistory": {body}'


def build_clipboard_selected(entries: Sequence[Any], indices: Sequence[int]) -> str:
    """``[#n] 原文`` for each selected line, in line order."""
    out: List[str] = []
    for i in sorted(set(indices)):
        if 0 <= i < len(entries):
            out.append(f"[#{i + 1}] {_as_text(entries[i])}")
    return "\n".join(out)


def parse_clipboard(text: str, current_len: int = 0) -> ImportResult:
    """Understand whatever the user pasted.

    Tried in order — full JSON object → ``"ConversationHistory": [ … ]``
    fragment → bare JSON array → ``[#n]`` numbered lines.  The first three
    describe a whole history (replace); the last patches individual lines.
    """
    raw = (text or "").strip()
    if not raw:
        raise TransferError("empty")

    # 1. a whole character JSON (or any object carrying the key)
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            if "ConversationHistory" not in obj:
                raise TransferError("json-without-key")
            return ImportResult("replace",
                                entries=_coerce_entries(obj["ConversationHistory"]),
                                source="json-object")

    # 2. the bare fragment — wrap it back into an object and reuse the parser
    if _CH_FRAGMENT_RE.match(raw) or raw.startswith('"ConversationHistory"'):
        try:
            obj = json.loads("{" + raw.rstrip().rstrip(",") + "}")
        except ValueError as exc:
            raise TransferError("bad-fragment") from exc
        if isinstance(obj, dict) and "ConversationHistory" in obj:
            return ImportResult("replace",
                                entries=_coerce_entries(obj["ConversationHistory"]),
                                source="fragment")

    # 3. a bare JSON array of lines
    if raw.startswith("["):
        try:
            arr = json.loads(raw)
        except ValueError:
            arr = None
        if isinstance(arr, list):
            return ImportResult("replace", entries=_coerce_entries(arr),
                                source="array")

    # 4. [#n] numbered lines — a patch, not a replacement
    updates = _parse_numbered(raw, current_len)
    if updates:
        return ImportResult("patch", updates=updates, source="numbered")

    raise TransferError("unrecognised")


def _parse_numbered(raw: str, current_len: int) -> Dict[int, str]:
    """``[#n] text`` blocks → {0-based index: line}.

    A line that does not start a new ``[#n]`` continues the previous entry, so
    multi-line dialogue survives the round trip.  An out-of-range number is an
    error rather than a silent skip: it means the paste came from a different
    character (or a stale export), and quietly dropping it would leave the user
    thinking their edit applied.
    """
    updates: Dict[int, str] = {}
    order: List[int] = []
    cur: Optional[int] = None
    buf: List[str] = []
    bad: List[int] = []

    def flush():
        if cur is not None:
            updates[cur] = "\n".join(buf).strip("\n")

    for line in raw.replace("\r\n", "\n").split("\n"):
        m = _CLIP_LINE_RE.match(line)
        if m:
            flush()
            n = int(m.group(1))
            if current_len and not (1 <= n <= current_len):
                bad.append(n)
            cur = n - 1
            order.append(n)
            buf = [m.group(2)]
        elif cur is not None:
            buf.append(line)
    flush()

    if bad:
        raise TransferError("out-of-range:" + ",".join(str(n) for n in bad[:5]))
    return updates


def apply_patch(entries: Sequence[Any], updates: Dict[int, str]) -> List[str]:
    """Return a copy of *entries* with *updates* applied by index."""
    out = [_as_text(e) for e in entries]
    for i, text in updates.items():
        if 0 <= i < len(out):
            out[i] = text
    return out
