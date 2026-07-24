"""DialogueObservations helpers (pure, UI-free) — AI Influence 5.0.x / 6.0.

What observations are
---------------------
Every spoken line writes one observation into **each** character who was present,
including the speaker.  The speaker and the person spoken to get
``hearing_role = "direct"``; bystanders get ``"overheard"`` plus a ``distance``
and a **distorted** ``heard_line`` (characters dropped the further away they were),
while ``canonical_line`` keeps the original text.

They are a permanent log: nothing in the mod prunes or caps
``DialogueObservations`` (unlike the ``[Overheard nearby …]`` lines in
ConversationHistory, which do expire).  Their consumer is the **dynamic-event
generator**, not the dialogue prompt.

About ProcessedDialogueObservationHashes
---------------------------------------
That set marks observations already handed to event analysis.  Each hash is
``SHA-256`` over ``scene_id | utterance_id | hearing_role | heard_line`` joined by
**encrypted separator literals**, so the tool *cannot* recompute it to find which
hash belongs to which observation.  That is fine: the set is only ever consulted
to *skip* work, so a hash left behind by a deleted observation simply never
matches anything again.  Deleting therefore touches ``DialogueObservations``
only — never the hash set.  See ``docs/參考資料/RAG檢索系統說明.md`` §7.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

OBSERVATIONS_KEY = "DialogueObservations"

ROLE_DIRECT = "direct"
ROLE_OVERHEARD = "overheard"


def observations(data: Any) -> List[Dict[str, Any]]:
    """Return the character's observation list (empty when absent/malformed)."""
    if not isinstance(data, dict):
        return []
    obs = data.get(OBSERVATIONS_KEY)
    return [o for o in obs if isinstance(o, dict)] if isinstance(obs, list) else []


def is_overheard(obs: Dict[str, Any]) -> bool:
    """True when this observation was overheard rather than heard directly."""
    return str(obs.get("hearing_role") or "").strip().lower() == ROLE_OVERHEARD


def is_distorted(obs: Dict[str, Any]) -> bool:
    """True when the heard text differs from the original — i.e. the listener
    only caught part of it.  Direct listeners hear the line verbatim."""
    heard = obs.get("heard_line")
    canon = obs.get("canonical_line")
    if not isinstance(heard, str) or not isinstance(canon, str):
        return False
    # heard_line carries a speaker prefix ("Name (`id`): …"); compare on the tail.
    return canon.strip() not in heard


def speaker_label(obs: Dict[str, Any], resolve_name=None) -> str:
    """Human-readable speaker: prefer the recorded name, fall back to the id.

    *resolve_name* (optional) maps a hero StringId to a localized display name,
    letting the caller plug in the terminology database.
    """
    sid = str(obs.get("speaker_hero_id") or "").strip()
    if resolve_name and sid:
        resolved = resolve_name(sid)
        if resolved:
            return resolved
    name = str(obs.get("speaker_name") or "").strip()
    return name or sid or "?"


def distance_of(obs: Dict[str, Any]) -> Optional[float]:
    """Metres between listener and speaker; None for direct conversation."""
    try:
        d = obs.get("distance")
        return float(d) if d is not None else None
    except (TypeError, ValueError):
        return None


def campaign_day_of(obs: Dict[str, Any]) -> Optional[float]:
    try:
        v = obs.get("campaign_days")
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def scene_key(obs: Dict[str, Any]) -> str:
    """Scene this utterance belonged to — groups one conversation together."""
    return str(obs.get("scene_id") or "")


def utterance_key(obs: Dict[str, Any]) -> str:
    """Campaign-unique id of the spoken line; the anchor for cross-character
    lookups (which other characters also heard this same line)."""
    return str(obs.get("utterance_id") or "")


def delete_observation(data: Dict[str, Any], index: int) -> bool:
    """Remove observation *index* from *data* in place.

    The hash set is deliberately left untouched (see the module docstring).
    Returns True when something was removed.
    """
    if not isinstance(data, dict):
        return False
    obs = data.get(OBSERVATIONS_KEY)
    if not isinstance(obs, list) or not (0 <= index < len(obs)):
        return False
    obs.pop(index)
    data[OBSERVATIONS_KEY] = obs
    return True


def summarize(data: Any) -> Dict[str, int]:
    """Counts for the page header: total / direct / overheard / scenes."""
    obs = observations(data)
    overheard = sum(1 for o in obs if is_overheard(o))
    return {
        "total": len(obs),
        "direct": len(obs) - overheard,
        "overheard": overheard,
        "scenes": len({scene_key(o) for o in obs if scene_key(o)}),
    }
