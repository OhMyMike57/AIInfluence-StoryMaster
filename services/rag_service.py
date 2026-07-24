"""Conversation RAG index maintenance for AI Influence 6.0+.

Background
----------
6.0 replaced memory consolidation with retrieval: ConversationHistory is kept in
full, and a per-NPC index at ``<campaign>/rag/<StringId>.json`` holds chunks the
mod retrieves from when the history grows past the prompt window.  Each chunk
records a ``start_line``/``end_line`` range **and embeds the text as it read at
index time**, so editing history behind the mod's back leaves the index stale —
the AI keeps retrieving lines the player already deleted or rewrote.

Invalidation contract
---------------------
``ConversationRagStorage.LoadOrCreate`` treats a missing (or unparseable) index
file as "not indexed yet" and rebuilds it in the background.  Deleting the file
is therefore the supported way to invalidate — it is the on-disk equivalent of
the ``InvalidateCache`` call the in-game Content Editor makes after saving edited
dialogue (AI Influence 6.0.1 fix).

Note the mod also holds an in-memory cache, so deleting the file only takes
effect from the next campaign load.  That matches the tool's existing rule that
campaign data may only be edited at the main menu.

Pre-6.0 campaigns simply have no ``rag/`` folder; every function degrades to a
no-op, so callers never need to branch on the mod version.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

RAG_DIR_NAME = "rag"

CONVERSATION_KEY = "ConversationHistory"
MEMORY_INDEX_KEY = "LastMemoryProcessedIndex"


def rag_index_path(campaign_dir: Optional[Path], string_id: str) -> Optional[Path]:
    """Return the RAG index path for *string_id*, or None when unresolvable."""
    if not campaign_dir or not string_id:
        return None
    try:
        return Path(campaign_dir) / RAG_DIR_NAME / f"{string_id}.json"
    except Exception:
        return None


def has_rag_index(campaign_dir: Optional[Path], string_id: str) -> bool:
    """True when a RAG index exists for *string_id* (i.e. a 6.0+ campaign)."""
    p = rag_index_path(campaign_dir, string_id)
    try:
        return bool(p and p.is_file())
    except Exception:
        return False


def invalidate_rag_index(campaign_dir: Optional[Path], string_id: str) -> bool:
    """Delete the RAG index for *string_id* so the mod rebuilds it.

    Returns True only when a file was actually removed, so callers can report
    "index will be rebuilt" without lying on pre-6.0 saves.
    """
    p = rag_index_path(campaign_dir, string_id)
    if not p:
        return False
    try:
        if not p.is_file():
            return False
        p.unlink()
        return True
    except Exception:
        return False


def clamp_memory_processed_index(data: Dict[str, Any]) -> bool:
    """Clamp ``LastMemoryProcessedIndex`` to the ConversationHistory length.

    The memory system stores how far down the history it has already turned into
    memories.  Trimming history without lowering the pointer leaves it past the
    end, which makes the mod skip everything after the edit (or, on a rewritten
    history, process the wrong lines).  Mutates *data* in place; returns True
    when the value changed.
    """
    if not isinstance(data, dict) or MEMORY_INDEX_KEY not in data:
        return False
    history = data.get(CONVERSATION_KEY)
    if not isinstance(history, list):
        return False
    try:
        current = int(data.get(MEMORY_INDEX_KEY) or 0)
    except (TypeError, ValueError):
        current = 0
    clamped = max(0, min(current, len(history)))
    if clamped == data.get(MEMORY_INDEX_KEY):
        return False
    data[MEMORY_INDEX_KEY] = clamped
    return True


def string_id_of(data: Any) -> str:
    """Return the character's StringId, or "" when *data* isn't a character."""
    if not isinstance(data, dict):
        return ""
    sid = data.get("StringId")
    return sid.strip() if isinstance(sid, str) else ""


def is_character_payload(data: Any) -> bool:
    """True when *data* looks like an AI Influence character JSON."""
    return isinstance(data, dict) and CONVERSATION_KEY in data and bool(string_id_of(data))
