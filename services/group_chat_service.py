"""Group-chat participant detection (player-anchor heuristic) + repair (pure).

Detection anchors on the player's opening utterance: an AI Influence group chat
is initiated by the player speaking first, so the participants share an
identical ``main_hero`` line in their ConversationHistory.  A 1-on-1 player line
appears in exactly one character file; a group opening appears in ≥2 → the group
is the set of characters sharing the most-common player line.

Caveat (see ``findings/群聊參與者偵測_可行性.md``): the 5.0.x memory system can
consolidate a participant's group-chat lines (including the opening) into a
``MEMORY`` summary, dropping that character from detection.  Detection is
therefore a *suggestion* the user curates (exclude false positives, add missed
participants) before applying.

Repair fixes the two confirmed author-oversight fields (participants who joined a
group chat don't get these updated): ``LastInteractionTimeDays`` and the player
interaction count (``CounterpartySocial.main_hero.interaction_count``).
"""
from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Dict, List, Optional

from services.json_utils import parse_conversation_line

PLAYER_SID = "main_hero"


def _to_int(v: Any) -> int:
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def _player_lines(ch: Any) -> List[str]:
    """Distinct ``main_hero`` line texts in a ConversationHistory (order-preserving)."""
    out: List[str] = []
    seen = set()
    for e in ch or []:
        p = parse_conversation_line(e)
        if p["kind"] in ("dialogue", "self") and p["speaker_id"] == PLAYER_SID and p["text"]:
            t = p["text"]
            if t not in seen:
                out.append(t)
                seen.add(t)
    return out


def detect_group(char_data: Dict[str, dict]) -> Dict[str, Any]:
    """Detect the most likely group-chat participant set.

    *char_data*: ``{display_key -> character_json_dict}``.
    Returns ``{"anchor": <player line or None>, "participants": [display_key,…]}``.
    """
    line_to_displays: Dict[str, set] = defaultdict(set)
    for disp, data in char_data.items():
        if not isinstance(data, dict):
            continue
        for t in _player_lines(data.get("ConversationHistory")):
            line_to_displays[t].add(disp)

    # Group-chat openings are shared by ≥2 characters; pick the largest group,
    # tie-broken by the more-specific (longer) anchor text.
    candidates = [(t, d) for t, d in line_to_displays.items() if len(d) >= 2]
    if not candidates:
        return {"anchor": None, "participants": []}
    candidates.sort(key=lambda x: (len(x[1]), len(x[0])), reverse=True)
    anchor, displays = candidates[0]
    return {"anchor": anchor, "participants": sorted(displays)}


def group_day(char_data: Dict[str, dict], participants: List[str]) -> float:
    """Estimated group-chat day = max ``LastInteractionTimeDays`` among *participants*.

    (Participants who joined but weren't updated read -1.0 / an old value; the
    max is the one that *was* updated — the actual group-chat day.)
    """
    best = 0.0
    for disp in participants:
        d = char_data.get(disp) or {}
        try:
            v = float(d.get("LastInteractionTimeDays", 0) or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > best:
            best = v
    return best


def apply_repair(data: dict, day: float, *, fix_last_interaction: bool,
                 fix_interaction_count: bool) -> dict:
    """Return a repaired copy of a character JSON (pure — input not mutated)."""
    out = copy.deepcopy(data) if isinstance(data, dict) else {}
    if fix_last_interaction:
        out["LastInteractionTimeDays"] = float(day)
    if fix_interaction_count:
        cs = out.get("CounterpartySocial")
        if isinstance(cs, dict) and isinstance(cs.get(PLAYER_SID), dict):
            mh = cs[PLAYER_SID]
            mh["interaction_count"] = _to_int(mh.get("interaction_count", 0)) + 1
        elif "InteractionCount" in out:            # legacy 4.1.0 top-level
            out["InteractionCount"] = _to_int(out.get("InteractionCount", 0)) + 1
        else:                                      # create the 5.0.x location
            cs = cs if isinstance(cs, dict) else {}
            mh = cs.get(PLAYER_SID)
            mh = dict(mh) if isinstance(mh, dict) else {}
            mh["interaction_count"] = _to_int(mh.get("interaction_count", 0)) + 1
            cs[PLAYER_SID] = mh
            out["CounterpartySocial"] = cs
    return out
