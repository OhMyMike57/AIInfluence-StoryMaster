"""JSON I/O utilities: safe loading, atomic writing, hashing, and speaker extraction."""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional


# ── Conversation line parsing (AI Influence 5.0.x formats) ────────────────
#
# Confirmed against a real 5.0.7 save (2026-07-04):
#   other speaker : ``名字 (`string_id`): 文本``
#   self speaker  : ``I (名字, `string_id`): 文本``  (the viewed character's own line)
#   overheard     : ``[Overheard nearby, day N, approx. X.Xm, ambient-npc] 名字 (`id`): 文本``
#   gap notice    : ``Your last conversation was 1 day ago.``  (kept in the list)
#   memory        : ``MEMORY (day N): 單行文本``  (appended, never consumed)
#   legacy/story  : ``[劇情記憶]: 文本`` / ``Player: 文本`` / old ``名字: 文本``
_RE_MEMORY = re.compile(
    r'^MEMORY \(day\s*(?P<day>[0-9]+(?:\.[0-9]+)?)\)\s*:\s?(?P<text>.*)$', re.S)
_RE_OVERHEARD = re.compile(
    r'^\[Overheard nearby,\s*day\s*(?P<day>[0-9]+(?:\.[0-9]+)?)\s*,\s*'
    r'approx\.\s*(?P<dist>[0-9]+(?:\.[0-9]+)?)m[^\]]*\]\s*'
    r'(?P<name>.+?)\s*\(`(?P<id>[^`]+)`\)\s*:\s?(?P<text>.*)$', re.S)
_RE_SELF = re.compile(
    r'^I\s*\(\s*(?P<name>[^,`()]+?)\s*,\s*`(?P<id>[^`]+)`\s*\)\s*:\s?(?P<text>.*)$', re.S)
_RE_NAMED = re.compile(
    r'^(?P<name>[^`()\[\]:]{1,64}?)\s*\(`(?P<id>[^`]+)`\)\s*:\s?(?P<text>.*)$', re.S)
_RE_GAP = re.compile(r'^Your last conversation was\b.*$', re.S)
# Story tags come in both bracket styles — ``[劇情記憶]:`` and, since 6.0,
# ``(劇情描述):`` (20 occurrences in the 2026-07-21 capture).  Without the
# parenthesised form those lines fell through to _RE_PLAIN and were shown as an
# ordinary un-linked speaker instead of a narration tag.
_RE_BRACKET = re.compile(
    r'^(?P<name>\[[^\]]+\]|\([^)]+\))\s*:\s?(?P<text>.*)$', re.S)
_RE_PLAIN = re.compile(r'^(?P<name>[^:\n\r]{1,64}):\s?(?P<text>.*)$', re.S)

# ── 6.0 additions (confirmed against a real 6.0.2 campaign, 2026-07-20) ──
#
# introduced : ``名字 (as introduced, `main_hero`): 文本``
#     The player *after* telling this NPC their name.  Before that the mod
#     writes ``Unidentified person (`main_hero`)`` (plain _RE_NAMED).  Without
#     its own pattern this fell through to _RE_PLAIN and rendered as an
#     ordinary third-party NPC, so player lines lost their colour mid-save.
# battle     : ``[BATTLE_ORDER][陣營 vs X's party] 名字: "文本"``
#     A commander's battle shout, carrying the engagement as context.
_RE_INTRODUCED = re.compile(
    r'^(?P<name>[^`()\[\]:]{1,64}?)\s*\(\s*as introduced\s*,\s*'
    r'`(?P<id>[^`]+)`\s*\)\s*:\s?(?P<text>.*)$', re.S)
_RE_BATTLE = re.compile(
    r'^\[BATTLE_ORDER\]\s*(?:\[(?P<ctx>[^\]]*)\])?\s*'
    r'(?P<name>[^:\n\r]{0,64}?)\s*:\s?(?P<text>.*)$', re.S)

PLAYER_ID = "main_hero"


def _dict_speaker(entry: dict) -> Optional[str]:
    """Speaker name from a dict-shaped entry (legacy/alternate structures)."""
    for k in ("Speaker", "speaker", "From", "from", "Name", "name", "Author", "author"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    meta = entry.get("Meta") or entry.get("meta")
    if isinstance(meta, dict):
        for k in ("Speaker", "speaker", "Name", "name"):
            v = meta.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    for k in ("Text", "text", "Line", "line", "Message", "message"):
        v = entry.get(k)
        if isinstance(v, str):
            m = re.match(r'^\s*([^:\n\r]{1,64})\s*:\s*', v)
            if m:
                return m.group(1).strip()
    return None


def parse_conversation_line(entry: Any) -> dict:
    """Parse a conversation entry into a structured descriptor.

    Returns a dict with keys: ``kind``, ``speaker``, ``speaker_id``,
    ``is_self``, ``text``, ``day``, ``distance``, ``raw``.
    ``kind`` ∈ {memory, overheard, self, dialogue, gap, tag, plain, dict, unknown}.
    """
    base = {"kind": "unknown", "speaker": None, "speaker_id": None,
            "is_self": False, "text": None, "day": None, "distance": None,
            "context": None, "introduced": False, "raw": entry}
    if isinstance(entry, dict):
        base.update(kind="dict", speaker=_dict_speaker(entry))
        return base
    if not isinstance(entry, str):
        return base

    m = _RE_BATTLE.match(entry)
    if m:
        base.update(kind="battle", speaker=(m.group("name") or "").strip() or None,
                    text=m.group("text"), context=(m.group("ctx") or "").strip() or None)
        return base
    m = _RE_MEMORY.match(entry)
    if m:
        base.update(kind="memory", text=m.group("text"), day=float(m.group("day")))
        return base
    m = _RE_OVERHEARD.match(entry)
    if m:
        base.update(kind="overheard", speaker=m.group("name").strip(),
                    speaker_id=m.group("id"), text=m.group("text"),
                    day=float(m.group("day")), distance=float(m.group("dist")))
        return base
    m = _RE_SELF.match(entry)
    if m:
        base.update(kind="self", speaker=m.group("name").strip(),
                    speaker_id=m.group("id"), is_self=True, text=m.group("text"))
        return base
    m = _RE_INTRODUCED.match(entry)
    if m:
        base.update(kind="dialogue", speaker=m.group("name").strip(),
                    speaker_id=m.group("id"), text=m.group("text"), introduced=True)
        return base
    m = _RE_NAMED.match(entry)
    if m:
        base.update(kind="dialogue", speaker=m.group("name").strip(),
                    speaker_id=m.group("id"), text=m.group("text"))
        return base
    if _RE_GAP.match(entry):
        base.update(kind="gap", text=entry)
        return base
    m = _RE_BRACKET.match(entry)
    if m:
        base.update(kind="tag", speaker=m.group("name").strip(), text=m.group("text"))
        return base
    m = _RE_PLAIN.match(entry)
    if m:
        base.update(kind="plain", speaker=m.group("name").strip(), text=m.group("text"))
        return base
    base.update(text=entry)
    return base


# Semantic categories a conversation line can fall into.  The viewer colours and
# badges rows by these, so the mapping lives here (testable) rather than in the
# widget.  ``note`` = a line with no speaker prefix at all: either a pure prompt
# the user wrote with the speaker left blank, or free text the mod stored.
LINE_CATEGORIES = (
    "player", "self", "other", "plain", "tag",
    "overheard", "battle", "memory", "gap", "note",
)


def line_category(parsed: dict, npc_name: str = "", npc_id: str = "") -> str:
    """Classify a parsed conversation line for display purposes."""
    kind = parsed.get("kind")
    if kind in ("gap", "memory", "overheard", "battle", "tag"):
        return kind
    name = (parsed.get("speaker") or "").strip()
    sid = (parsed.get("speaker_id") or "").strip()

    if sid == PLAYER_ID or name.lower() == "player":
        return "player"
    if kind == "self":
        return "self"
    if (npc_id and sid == npc_id) or (npc_name and name == npc_name):
        return "self"
    if kind == "dialogue" or (kind == "dict" and name):
        return "other"
    if kind == "plain":
        return "plain"
    return "other" if name else "note"


def split_line_prefix(entry: Any) -> tuple:
    """Split a conversation line into ``(prefix, content)``.

    *prefix* is everything the mod put before the ``": "`` — a plain speaker for
    ordinary dialogue, but also the whole ``[Overheard nearby, day N, approx.
    X.Xm, …] 名字 (`id`)`` blob, ``[BATTLE_ORDER][…] 名字``, ``MEMORY (day N)``
    or a ``[劇情記憶]`` tag.  Rejoining with ``f"{prefix}: {content}"``
    reproduces the original byte-for-byte, which is why the editor keeps the
    prefix verbatim instead of trying to rebuild it from parsed parts.

    Lines with no prefix at all (gap notices, un-attributed plain text) come
    back as ``("", whole_line)``.
    """
    if not isinstance(entry, str):
        return ("", "")
    p = parse_conversation_line(entry)
    text = p.get("text")
    if not isinstance(text, str) or not entry.endswith(text):
        return ("", entry)
    head = entry[:len(entry) - len(text)]
    stripped = head.rstrip()
    if not stripped.endswith(":"):
        return ("", entry)          # gap notices and the like
    return (stripped[:-1].rstrip(), text)


def speaker_display(parsed: dict) -> tuple:
    """``(name, note)`` for a parsed line's speaker.

    *note* is a key the UI turns into a literal ``tr()`` label — returning the
    text itself would force ``tr(variable)``, which the i18n gate rejects (and
    which silently falls back to zh-Hant at runtime).  Keys:

    ``"unidentified"`` — the mod's ``Unidentified person`` placeholder: the
    player before they have told this NPC their name.
    ``"introduced"``   — 6.0's ``(as introduced)``: the player after they have.
    """
    name = (parsed.get("speaker") or "").strip()
    sid = (parsed.get("speaker_id") or "").strip()
    if sid == PLAYER_ID and name.lower() == "unidentified person":
        return ("", "unidentified")
    if sid == PLAYER_ID and parsed.get("introduced"):
        return (name, "introduced")
    return (name, "")


def convert_line_perspective(entry: Any, target_id: Any, target_name: Optional[str] = None) -> Any:
    """Rewrite a conversation line into the reading perspective of *target_id*.

    A line spoken *by the target* becomes first-person ``I (名字, `id`): …``;
    a first-person line spoken by *someone else* becomes third-person
    ``名字 (`id`): …``.  Overheard / gap / memory / tag / plain / dict lines and
    lines carrying no ``string_id`` are returned unchanged.  This keeps synced /
    back-filled history in each character's own voice (5.0.x ``I (…)`` format).
    """
    if not isinstance(entry, str) or not target_id:
        return entry
    tid = str(target_id)
    p = parse_conversation_line(entry)
    if p["kind"] == "self" and p["speaker_id"] and p["speaker_id"] != tid:
        return f'{p["speaker"]} (`{p["speaker_id"]}`): {p["text"]}'
    if p["kind"] == "dialogue" and p["speaker_id"] == tid:
        return f'I ({p["speaker"]}, `{p["speaker_id"]}`): {p["text"]}'
    return entry


def entry_speaker(entry: Any) -> Optional[str]:
    """Extract the display speaker name from a conversation entry (str or dict)."""
    if isinstance(entry, str):
        p = parse_conversation_line(entry)
        if p["kind"] in ("self", "dialogue", "overheard", "tag", "plain"):
            return p["speaker"]
        if p["kind"] == "memory":
            return "MEMORY"
        return None
    if isinstance(entry, dict):
        return _dict_speaker(entry)
    return None


def entry_hash(entry: Any) -> str:
    """Return a SHA-1 hex digest for deduplication of conversation entries."""
    s = entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def safe_load_json(path: Path, retries: int = 3, sleep_sec: float = 0.05) -> Optional[dict]:
    """Load a JSON file with retry logic for concurrent access.

    Uses ``utf-8-sig`` so a leading UTF-8 BOM is transparently stripped. AI
    Influence 5.0.x writes its per-campaign world files (world_info/world_secrets)
    with a BOM; strict ``utf-8`` would raise on that byte. ``utf-8-sig`` reads
    both BOM and non-BOM files correctly.
    """
    for _ in range(retries):
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            time.sleep(sleep_sec)
    return None


def safe_write_json(path: Path, data: dict) -> bool:
    """Atomically write JSON via tmp-file swap. Returns True on success."""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception:
        return False


def load_json_file(path: Path) -> dict:
    """Load a JSON file, returning empty dict on any error.

    Reads with ``utf-8-sig`` to tolerate a leading UTF-8 BOM (5.0.x world files).
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def save_json_file(path: Path, data: dict) -> bool:
    """Write a JSON dict to file, creating parent dirs as needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def append_conversation_entries(
    path: Path, entries: list, writer: Any = None
) -> bool:
    """Append conversation entries to a character JSON, deduplicating against the last 12 entries."""
    d = safe_load_json(path)
    if not isinstance(d, dict):
        return False
    ch = d.get("ConversationHistory", [])
    if not isinstance(ch, list):
        ch = []
    tail_hashes = {entry_hash(e) for e in ch[-12:]}
    appended = False
    for e in entries:
        if entry_hash(e) in tail_hashes:
            continue
        ch.append(e)
        appended = True
    if not appended:
        return True
    d["ConversationHistory"] = ch
    if writer is not None:
        return writer(path, d)
    return safe_write_json(path, d)


def parse_last_ai_response(raw: Any) -> Optional[dict]:
    """Parse a character's LastAIResponseJson field into a dict.

    The stored value is typically a JSON string (sometimes double-escaped,
    e.g. when the save pipeline serialises a JSON object into a string
    field that is itself inside a JSON document). Tries increasingly
    permissive decodings and returns None on failure.

    Accepts None / empty string / dict / JSON-encoded string / doubly-encoded string.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    # First pass
    try:
        v = json.loads(text)
    except Exception:
        return None
    # If the first pass yielded a string (double-encoded case), decode again.
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return None
    return v if isinstance(v, dict) else None


def speaker_color(speaker: str, npc_name: str) -> str:
    """Return a display color string for a conversation speaker."""
    sl = speaker.lower()
    if sl == "player":
        return "blue"
    if sl == npc_name.lower():
        return "green"
    if re.match(r'^\[.*\]$', speaker.strip()):
        return "purple"
    if speaker != "未知" and speaker != "Unknown":   # noqa: cjk (sentinel compare)
        return "darkgreen"
    return "red"
