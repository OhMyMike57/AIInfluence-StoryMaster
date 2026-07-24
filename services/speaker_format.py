"""Speaker-prefix grammar for AI Influence ConversationHistory lines.

Every history line is ``<prefix>: <text>``.  This module owns the *prefix*
grammar so the UI never has to know it; ``json_utils.split_line_prefix`` does
the ``prefix``/``text`` cut, and :func:`parse` / :func:`build` round-trip the
prefix itself.

Grammar (reverse-engineered from every sample campaign — 4.1.0, 5.0.2, 5.0.7
and 6.0.2 — because the mod's format strings are encrypted inside the obfuscated
DLL and appear in no prompt template)::

    [ <wrapper> ] <identity> ( [<relation>, ] `<hero_id>` )
       └ optional    └ name position   └ optional relation marker

**identity** — who the listener thinks is speaking:

===================== ===========================================
``I``                 the character whose file this is (self-line)
a real name           a known character
``Unidentified person`` not yet introduced — the listener has no name for them
``Stranger``          an explicit stranger (only seen with ``as introduced``)
anything else         a claimed / assumed / titled name
===================== ===========================================

**relation** — ``as introduced`` means *the name position holds the name they
gave*, which is why identity and hero_id must stay independently editable: the
samples contain ``Stranger (as introduced, `main_hero`)`` (still anonymous),
``祿肯·赫芬斯汀 (as introduced, `main_hero`)`` (real name given) and
``貝卡 (as introduced, `CharacterObject_6605`)`` (a short name) side by side.
A self-line puts the real name inside the parens: ``I (「釤刀」蘇雷納, `id`)``.

**wrapper** — an optional bracketed context in front:

* ``[Overheard nearby, day <N>, approx. <X.X>m, <channel>]`` — five channels
  observed: ``dialog/player``, ``dialog/npc``, ``group/player``, ``group/npc``,
  ``ambient-npc``.
* ``[BATTLE_ORDER][<engagement>]`` — a commander's battle shout.  The engagement
  string is kept **opaque**: only one engagement shape has been observed in the
  samples (``<faction> vs <hero>'s party``), so parsing it into fields would be
  guessing.  Treating it as a string means the round-trip is exact whatever the
  game writes there.

Lines that are not speech at all — ``[劇情記憶]`` style tags, ``MEMORY (day N)``,
gap notices — are *not* this grammar; :func:`parse` reports them as
``kind="raw"`` and :func:`build` returns them untouched.

Legacy 4.1.0 ``Player`` / ``Event`` prefixes parse (so old saves display and
round-trip correctly) but are deliberately not offered as choices in the UI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Optional

PLAYER_ID = "main_hero"

# Identity placeholders the mod writes (kept as literals — they are data the mod
# reads back, never translated).
IDENTITY_SELF = "I"
IDENTITY_UNIDENTIFIED = "Unidentified person"
IDENTITY_STRANGER = "Stranger"

RELATION_NONE = ""
RELATION_INTRODUCED = "as introduced"

# Overheard channels, in the order the quick-set menu offers them.
CHANNELS = ("dialog/player", "dialog/npc", "group/player", "group/npc", "ambient-npc")

_RE_OVERHEARD_WRAP = re.compile(
    r'^\[Overheard nearby,\s*day\s*(?P<day>[0-9]+(?:\.[0-9]+)?)\s*,\s*'
    r'approx\.\s*(?P<dist>[0-9]+(?:\.[0-9]+)?)m\s*,\s*(?P<chan>[^\]]*)\]\s*')
_RE_BATTLE_WRAP = re.compile(r'^\[BATTLE_ORDER\]\s*(?:\[(?P<ctx>[^\]]*)\]\s*)?')
_RE_SELF = re.compile(r'^I\s*\(\s*(?P<name>[^,`()]*?)\s*,\s*`(?P<id>[^`]+)`\s*\)$')
_RE_INTRODUCED = re.compile(
    r'^(?P<name>.*?)\s*\(\s*as introduced\s*,\s*`(?P<id>[^`]+)`\s*\)$')
_RE_NAMED = re.compile(r'^(?P<name>.*?)\s*\(\s*`(?P<id>[^`]+)`\s*\)$')


@dataclass
class Overheard:
    """The ``[Overheard nearby, …]`` wrapper."""
    day: float = 0.0
    distance: float = 0.0
    channel: str = "dialog/player"

    def render(self) -> str:
        day = int(self.day) if float(self.day).is_integer() else self.day
        return (f"[Overheard nearby, day {day}, "
                f"approx. {self.distance:.1f}m, {self.channel}] ")


@dataclass
class Battle:
    """The ``[BATTLE_ORDER][…]`` wrapper.  *engagement* is opaque by design."""
    engagement: str = ""

    def render(self) -> str:
        return f"[BATTLE_ORDER][{self.engagement}] " if self.engagement else "[BATTLE_ORDER] "


@dataclass
class Speaker:
    """A parsed speaker prefix.

    ``kind``: ``"speech"`` for the grammar above, ``"raw"`` for anything else
    (story tags, MEMORY lines, gap notices) — raw prefixes are carried in
    ``raw`` and rebuilt verbatim.

    ``self_name`` only applies to self-lines: ``I (名字, `id`)`` keeps the real
    name inside the parens, so it needs its own slot rather than the identity
    position (which holds the literal ``I``).
    """
    identity: str = ""
    hero_id: str = ""
    relation: str = RELATION_NONE
    wrapper: Optional[object] = None        # Overheard | Battle | None
    kind: str = "speech"
    raw: str = ""
    self_name: str = ""

    # ── convenience predicates (UI reads these instead of comparing strings) ──
    @property
    def is_self(self) -> bool:
        return self.kind == "speech" and self.identity == IDENTITY_SELF

    @property
    def is_player(self) -> bool:
        return self.hero_id == PLAYER_ID

    @property
    def is_anonymous(self) -> bool:
        return self.identity in (IDENTITY_UNIDENTIFIED, IDENTITY_STRANGER)


def parse(prefix: str) -> Speaker:
    """Parse a speaker prefix.  Never raises — unknown shapes come back raw."""
    if not isinstance(prefix, str) or not prefix.strip():
        return Speaker(kind="raw", raw=prefix or "")
    rest = prefix
    wrapper: Optional[object] = None

    m = _RE_OVERHEARD_WRAP.match(rest)
    if m:
        wrapper = Overheard(day=float(m.group("day")),
                            distance=float(m.group("dist")),
                            channel=m.group("chan").strip())
        rest = rest[m.end():]
    else:
        m = _RE_BATTLE_WRAP.match(rest)
        if m:
            wrapper = Battle(engagement=(m.group("ctx") or "").strip())
            rest = rest[m.end():]

    rest = rest.strip()
    m = _RE_SELF.match(rest)
    if m:
        return Speaker(identity=IDENTITY_SELF, hero_id=m.group("id"),
                       relation=RELATION_NONE, wrapper=wrapper, raw=prefix,
                       self_name=m.group("name").strip())
    m = _RE_INTRODUCED.match(rest)
    if m:
        return Speaker(identity=m.group("name").strip(), hero_id=m.group("id"),
                       relation=RELATION_INTRODUCED, wrapper=wrapper, raw=prefix)
    m = _RE_NAMED.match(rest)
    if m:
        return Speaker(identity=m.group("name").strip(), hero_id=m.group("id"),
                       relation=RELATION_NONE, wrapper=wrapper, raw=prefix)
    # A battle shout names its speaker without an id: "[BATTLE_ORDER][…] 名字".
    if isinstance(wrapper, Battle) and rest:
        return Speaker(identity=rest, hero_id="", wrapper=wrapper, raw=prefix)
    return Speaker(kind="raw", raw=prefix)


def build(sp: Speaker) -> str:
    """Render a :class:`Speaker` back to a prefix (exact for anything parsed)."""
    if sp.kind == "raw":
        return sp.raw
    head = sp.wrapper.render() if sp.wrapper is not None else ""
    if sp.identity == IDENTITY_SELF:
        return f"{head}I ({sp.self_name}, `{sp.hero_id}`)"
    if not sp.hero_id:
        return f"{head}{sp.identity}"
    if sp.relation == RELATION_INTRODUCED:
        return f"{head}{sp.identity} (as introduced, `{sp.hero_id}`)"
    return f"{head}{sp.identity} (`{sp.hero_id}`)"


# ── helpers the UI uses to assemble a speaker ─────────────────────────────

def make_self(name: str, hero_id: str, wrapper=None) -> Speaker:
    """``I (名字, `id`)`` — the file's own character speaking."""
    return Speaker(identity=IDENTITY_SELF, hero_id=hero_id, wrapper=wrapper,
                   self_name=name)


def make_named(name: str, hero_id: str, *, introduced: bool = False,
               wrapper=None) -> Speaker:
    return Speaker(identity=name, hero_id=hero_id, wrapper=wrapper,
                   relation=RELATION_INTRODUCED if introduced else RELATION_NONE)


def with_identity(sp: Speaker, identity: str) -> Speaker:
    """Swap the name position, keeping the id, relation and wrapper."""
    if sp.kind == "raw":
        return sp
    return replace(sp, identity=identity, raw="")


def with_relation(sp: Speaker, relation: str) -> Speaker:
    if sp.kind == "raw":
        return sp
    return replace(sp, relation=relation, raw="")


def with_wrapper(sp: Speaker, wrapper) -> Speaker:
    if sp.kind == "raw":
        return sp
    return replace(sp, wrapper=wrapper, raw="")


def format_text_for(sp: Speaker, text: str) -> str:
    """Apply the wrapper's own convention to a line's *text*.

    Battle shouts are always stored quoted — ``… 巴索洛恩: "步兵團，舉起盾牌…"``
    — in every captured sample.  (In the raw JSON that reads as ``\\"…\\"``,
    which is just JSON escaping the quote, not a backslash in the value.)
    Writing an unquoted battle line would make it the only one in the file that
    doesn't match, so the quotes are added here rather than left to the user.
    """
    body = (text or "").strip()
    if isinstance(sp.wrapper, Battle) and body:
        if not (body.startswith('"') and body.endswith('"')):
            body = f'"{body}"'
    return body


def compose(sp: Optional[Speaker], text: str) -> str:
    """Build a complete history line from a speaker (may be None) and its text."""
    body = format_text_for(sp, text) if sp is not None else (text or "").strip()
    if sp is None:
        return body
    prefix = build(sp)
    return f"{prefix}: {body}" if prefix else body


def resolve_for_target(sp: Speaker, target_id: str, target_name: str) -> Speaker:
    """Adapt a speaker for the character file it is being written into.

    Batch writes go to many characters at once.  A line whose speaker *is* the
    receiving character must be written in that file as a self-line
    (``I (名字, `id`)``) — that is how the mod records "this is me talking".
    For every other file the same speaker stays third-person.  This is what
    makes one 寫入劇情 produce the right shape in each target.
    """
    if sp.kind == "raw" or not sp.hero_id or not target_id:
        return sp
    if sp.hero_id == target_id:
        return make_self(target_name or sp.self_name or sp.identity,
                         sp.hero_id, wrapper=sp.wrapper)
    if sp.is_self:
        # A self-line being copied elsewhere becomes third person.
        return make_named(sp.self_name or sp.identity, sp.hero_id,
                          wrapper=sp.wrapper)
    return sp
