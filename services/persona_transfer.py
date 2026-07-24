"""Persona (角色人設) clipboard export / import — pure, UI-free.

The 5 AI-generated persona fields can be exported to / imported from the
clipboard as JSON so users can edit them in an external text editor.

Export shape (``_meta`` identifies the source character; only chosen fields)::

    {
      "_meta": {"Name": "…", "StringId": "…", "exported_at": "<ISO-8601>"},
      "CharacterDescription": "…",
      "AIGeneratedPersonality": "…"
    }

Import accepts either that persona JSON (``_meta`` ignored) or a *full* character
JSON (the 5 fields are extracted from it).
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Dict, List, Tuple

# Canonical persona field order (keys match the character JSON schema).
PERSONA_FIELDS: Tuple[str, ...] = (
    "CharacterDescription",
    "AIGeneratedPersonality",
    "AIGeneratedBackstory",
    "AIGeneratedSpeechQuirks",
    "AIGeneratedCognitiveStyle",
)

# Markers that identify a *full* character JSON (vs a persona-only export).
_CHARACTER_MARKERS = ("StringId", "ConversationHistory", "CounterpartySocial",
                      "KnownInfo", "Memories")


def build_export_json(data: Dict[str, Any], fields: List[str]) -> str:
    """Build the export JSON string for *fields* of character *data*."""
    chosen = [f for f in PERSONA_FIELDS if f in fields]  # keep canonical order
    out: Dict[str, Any] = {
        "_meta": {
            "Name": str((data or {}).get("Name", "") or ""),
            "StringId": str((data or {}).get("StringId", "") or ""),
            "exported_at": _dt.datetime.now().astimezone().isoformat(),
        }
    }
    for f in chosen:
        out[f] = str((data or {}).get(f, "") or "")
    return json.dumps(out, ensure_ascii=False, indent=2)


def parse_import_json(text: str) -> Tuple[Dict[str, str], str]:
    """Parse clipboard *text* into ``({field: value}, source_kind)``.

    *source_kind* is ``"character"`` (full character JSON) or ``"persona"``
    (persona export).  Raises ``ValueError`` when the text isn't valid JSON or
    contains none of the persona fields.
    """
    try:
        d = json.loads(text)
    except Exception as ex:
        raise ValueError(f"not valid JSON: {ex}")
    if not isinstance(d, dict):
        raise ValueError("JSON is not an object")

    present = {f: str(d.get(f, "") or "") for f in PERSONA_FIELDS if f in d}
    if not present:
        raise ValueError("no persona fields found")

    kind = "character" if any(m in d for m in _CHARACTER_MARKERS) else "persona"
    return present, kind
