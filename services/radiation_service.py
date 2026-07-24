"""Dialogue radiation — who overheard, and who shares, a given line (6.0).

Two relations between a line and other characters:

* **Eavesdroppers** — characters who *overheard* the utterance, linked by
  ``utterance_id`` through ``DialogueObservations``; each caught a distorted
  copy (see below).
* **Sharers** — characters whose ConversationHistory holds a line with the
  *same content* (speaker prefix ignored).  This is how group conversations
  (each participant gets the line, attributed ``I (…)`` for their own turns and
  ``名字 (…)`` for others'), battle shouts broadcast to a party, and lines the
  user wrote to several characters at once show up across files.  Verified
  against real 6.0 saves: shared content is substantial (median ~290 chars,
  none under 8), so an exact content match is a clean signal with no
  short-string noise.


Every spoken line writes one ``DialogueObservation`` into each character present
(see :mod:`services.observation_service`), linked campaign-wide by
``utterance_id``.  A *listener* is identified by the file the observation lives
in, not by any field — the observation records only the speaker.  So "who
overheard line N of character A" is answered by scanning every character file
for an ``overheard`` observation carrying the same ``utterance_id``.

Two facts, both verified against real 6.0 saves (``scripts/radiation_service_check``):

* ``DialogueObservations`` is the permanent, complete record; the
  ``[Overheard nearby …]`` lines in ``ConversationHistory`` are a transient
  subset that the mod expires (a campaign had 47 overheard observations but only
  18 surviving CH lines).
* When such a CH line *is* still present, the text after its ``]`` equals the
  observation's ``heard_line`` exactly — so cleanup matches by content, never
  by fuzzy day/distance rounding.

Cleaning a listener therefore removes the ``utterance_id`` observation (always
present, authoritative) and the matching CH overheard line (when it survives);
the RAG index rebuilds itself once the CH changes (the app's write path handles
that), and ``ProcessedDialogueObservationHashes`` is deliberately untouched
(see the observation-service docstring).  This is as clean as the data allows.

Pure and Tk-free so the mapping and cleanup can be unit-tested headless.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from services.json_utils import parse_conversation_line, split_line_prefix
from services.observation_service import ROLE_OVERHEARD, observations

_OVERHEARD_PREFIX = "[Overheard nearby"

# Line kinds that never count as "shared content" (see share_content):
# gap notices and per-character memory lines are not shared dialogue, and an
# overheard copy is distorted (it belongs to the eavesdropping view instead).
_SHARE_SKIP_KINDS = frozenset({"gap", "memory", "overheard"})


@dataclass(frozen=True)
class Eavesdropper:
    """One character who overheard a particular utterance."""
    listener_key: str          # opaque handle the UI maps back to a character
    listener_id: str           # StringId of the listener
    listener_name: str         # display name recorded in the listener's file
    distance: Optional[float]  # metres from the speaker
    heard_line: str            # the distorted text they actually caught
    utterance_id: str


@dataclass(frozen=True)
class Sharer:
    """One character whose history holds a line with the same content."""
    listener_key: str          # opaque handle the UI maps back to a character
    listener_id: str           # StringId of the sharer
    listener_name: str         # display name recorded in the sharer's file
    speaker: str               # how *their* copy attributes it (prefix)
    line: str                  # their full line, verbatim
    content: str               # the shared content (speaker-stripped)


def _obs_role(obs: Dict[str, Any]) -> str:
    return str(obs.get("hearing_role") or "").strip().lower()


def _overheard_tail(line: str) -> str:
    """Text of a ``[Overheard nearby …] speaker: text`` line after the wrapper.

    The wrapper's own ``]`` is the *first* one; the story text may contain more
    (e.g. ``[劇情描述:…]``), so split once.  Non-overheard lines return unchanged.
    """
    if line.startswith(_OVERHEARD_PREFIX) and "]" in line:
        return line.split("]", 1)[1].strip()
    return line


def _own_obs_maps(data: Any) -> Tuple[List[Tuple[str, str]], Dict[str, str]]:
    """From a character's own observations build the anchors for line→utterance.

    Returns ``(canon_pairs, heard_map)``:

    * ``canon_pairs`` — ``(canonical_line, utterance_id)`` sorted longest-first,
      for lines the character spoke or heard directly (their CH holds the
      *undistorted* text, so the canonical line is a substring of it);
    * ``heard_map`` — ``heard_line → utterance_id`` for lines the character
      overheard (their CH holds the distorted text, which equals ``heard_line``).
    """
    canon_pairs: List[Tuple[str, str]] = []
    heard_map: Dict[str, str] = {}
    for o in observations(data):
        utt = str(o.get("utterance_id") or "")
        if not utt:
            continue
        canon = str(o.get("canonical_line") or "").strip()
        if canon:
            canon_pairs.append((canon, utt))
        heard = str(o.get("heard_line") or "").strip()
        if heard:
            heard_map.setdefault(heard, utt)
    canon_pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return canon_pairs, heard_map


def line_to_utterance(line: Any, viewer_data: Any) -> Optional[str]:
    """Resolve a ConversationHistory line to its ``utterance_id``, or None.

    Uses the *viewer's own* observations: the canonical (undistorted) text for
    lines they spoke or heard directly, falling back to an exact ``heard_line``
    match for lines they overheard.  ~14% of lines have no observation (older
    lines, non-dialogue) and return None — the caller treats that as "unknown /
    no eavesdroppers".
    """
    if not isinstance(line, str) or not line:
        return None
    canon_pairs, heard_map = _own_obs_maps(viewer_data)
    for canon, utt in canon_pairs:           # longest-first → most specific wins
        if canon in line:
            return utt
    return heard_map.get(_overheard_tail(line))


def build_index(char_items: Iterable[Tuple[str, Any]]) -> Dict[str, List[Eavesdropper]]:
    """Campaign-wide ``utterance_id → [Eavesdropper]`` map.

    *char_items* is ``(listener_key, data)`` for every character in the campaign;
    ``listener_key`` is whatever handle the caller wants back (a path string).
    Only ``overheard`` observations contribute — direct listeners are the
    speaker and the addressee, not eavesdroppers.
    """
    index: Dict[str, List[Eavesdropper]] = {}
    for key, data in char_items:
        if not isinstance(data, dict):
            continue
        sid = str(data.get("StringId") or "")
        name = str(data.get("Name") or "")
        for o in observations(data):
            if _obs_role(o) != ROLE_OVERHEARD:
                continue
            utt = str(o.get("utterance_id") or "")
            if not utt:
                continue
            dist = o.get("distance")
            try:
                dist = float(dist) if dist is not None else None
            except (TypeError, ValueError):
                dist = None
            index.setdefault(utt, []).append(Eavesdropper(
                listener_key=key, listener_id=sid, listener_name=name,
                distance=dist, heard_line=str(o.get("heard_line") or ""),
                utterance_id=utt))
    # Closest listeners first — most likely to have caught the line intact.
    for lst in index.values():
        lst.sort(key=lambda e: (e.distance is None, e.distance or 0.0))
    return index


def eavesdroppers_for_line(
    line: Any, viewer_data: Any, index: Dict[str, List[Eavesdropper]],
    *, exclude_key: Optional[str] = None,
) -> List[Eavesdropper]:
    """Eavesdroppers of *line* (empty when it maps to no utterance).

    *exclude_key* drops the viewer themselves — relevant only when the viewed
    line is one the viewer overheard, where they are their own eavesdropper.
    """
    utt = line_to_utterance(line, viewer_data)
    if not utt:
        return []
    return [e for e in index.get(utt, []) if e.listener_key != exclude_key]


def line_eaves_counts(
    ch: Any, viewer_data: Any, index: Dict[str, List[Eavesdropper]],
    *, viewer_key: Optional[str] = None,
) -> List[int]:
    """Per-line eavesdropper counts aligned to *ch* (0 where none/unknown)."""
    if not isinstance(ch, list):
        return []
    return [len(eavesdroppers_for_line(line, viewer_data, index,
                                       exclude_key=viewer_key)) for line in ch]


def clean_eavesdropper(listener_data: Dict[str, Any], utterance_id: str) -> Dict[str, int]:
    """Remove a listener's trace of *utterance_id* in place.

    Deletes every ``overheard`` observation for that utterance and any surviving
    ``[Overheard nearby …]`` CH line whose text matches one of their
    ``heard_line`` values.  Returns ``{"observations": n, "history": m}``.
    """
    result = {"observations": 0, "history": 0}
    if not isinstance(listener_data, dict) or not utterance_id:
        return result

    removed_heard: set = set()
    obs = listener_data.get("DialogueObservations")
    if isinstance(obs, list):
        kept = []
        for o in obs:
            if (isinstance(o, dict) and _obs_role(o) == ROLE_OVERHEARD
                    and str(o.get("utterance_id") or "") == utterance_id):
                removed_heard.add(str(o.get("heard_line") or "").strip())
                result["observations"] += 1
            else:
                kept.append(o)
        listener_data["DialogueObservations"] = kept

    ch = listener_data.get("ConversationHistory")
    if isinstance(ch, list) and removed_heard:
        kept_ch = []
        for line in ch:
            if (isinstance(line, str) and line.startswith(_OVERHEARD_PREFIX)
                    and _overheard_tail(line) in removed_heard):
                result["history"] += 1
                continue
            kept_ch.append(line)
        listener_data["ConversationHistory"] = kept_ch

    return result


# ── sharing (identical content across characters) ─────────────────────────────
def share_content(line: Any) -> str:
    """The content that makes a line 'the same' across characters, or ``""``.

    The speaker prefix is stripped so a group line attributed ``I (…)`` in one
    file and ``名字 (…)`` in another counts as the same line.  Gap / memory /
    overheard lines never share (see :data:`_SHARE_SKIP_KINDS`).
    """
    if not isinstance(line, str) or not line:
        return ""
    if parse_conversation_line(line).get("kind") in _SHARE_SKIP_KINDS:
        return ""
    _prefix, content = split_line_prefix(line)
    return (content or "").strip()


def build_share_index(char_items: Iterable[Tuple[str, Any]]) -> Dict[str, List[Sharer]]:
    """Campaign-wide ``content → [Sharer]`` map.

    One entry per character per content (a character who repeats the same line
    still counts once), keyed by the first occurrence so its speaker/line are
    representative.
    """
    index: Dict[str, List[Sharer]] = {}
    for key, data in char_items:
        if not isinstance(data, dict):
            continue
        sid = str(data.get("StringId") or "")
        name = str(data.get("Name") or "")
        seen: set = set()
        for line in data.get("ConversationHistory") or []:
            content = share_content(line)
            if not content or content in seen:
                continue
            seen.add(content)
            prefix, _ = split_line_prefix(line)
            index.setdefault(content, []).append(Sharer(
                listener_key=key, listener_id=sid, listener_name=name,
                speaker=str(prefix or "").strip(), line=str(line), content=content))
    return index


def sharers_for_line(
    line: Any, index: Dict[str, List[Sharer]], *, exclude_key: Optional[str] = None,
) -> List[Sharer]:
    """Other characters holding the same content (empty for a non-shared line)."""
    content = share_content(line)
    if not content:
        return []
    return [s for s in index.get(content, []) if s.listener_key != exclude_key]


def line_share_counts(
    ch: Any, index: Dict[str, List[Sharer]], *, viewer_key: Optional[str] = None,
) -> List[int]:
    """Per-line sharer counts aligned to *ch* (the viewer excluded)."""
    if not isinstance(ch, list):
        return []
    return [len(sharers_for_line(line, index, exclude_key=viewer_key)) for line in ch]


def clean_sharer(sharer_data: Dict[str, Any], content: str) -> Dict[str, int]:
    """Remove a character's copy of a shared line in place.

    Drops every ConversationHistory line whose content matches, and every
    observation whose ``canonical_line`` is that content (a spoken/direct line's
    canonical text is exactly this content) — so the character's record stays
    consistent.  Returns ``{"history": n, "observations": m}``.
    """
    result = {"history": 0, "observations": 0}
    if not isinstance(sharer_data, dict) or not content:
        return result

    ch = sharer_data.get("ConversationHistory")
    if isinstance(ch, list):
        kept = []
        for line in ch:
            if share_content(line) == content:
                result["history"] += 1
            else:
                kept.append(line)
        sharer_data["ConversationHistory"] = kept

    obs = sharer_data.get("DialogueObservations")
    if isinstance(obs, list):
        kept_obs = []
        for o in obs:
            if isinstance(o, dict) and str(o.get("canonical_line") or "").strip() == content:
                result["observations"] += 1
            else:
                kept_obs.append(o)
        sharer_data["DialogueObservations"] = kept_obs

    return result
