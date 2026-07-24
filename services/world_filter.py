"""Pure candidate-filtering logic for the 訊息與秘密 editor's 篩選範圍 / 延伸範圍.

The dialog (``ui/world_editor_dialog.py``) is widget-heavy; keeping the set math
here makes it unit-testable and keeps the UI thin.  All functions are pure: they
take plain dicts/sets and return plain sets/lists, with no Tk dependency.

``character_meta`` rows are expected to carry (injected by
``services.character_service``):
    HasAttrs : bool   — has companion-mod data (gates faction/clan filtering)
    Kingdom  : str    — kingdom id derived via the hero's clan ("" / None = 無陣營)
    Clan     : str    — clan id
"""
from __future__ import annotations

from i18n import tr

from typing import Dict, Iterable, List, Set, Tuple

MINOR_KEY = "__minor__"   # 無陣營 bucket (clanless / kingdomless heroes)


def faction_rows(character_meta: Dict[str, dict],
                 kingdom_names: Dict[str, str]) -> List[Tuple[str, str, str]]:
    """Kingdoms present among data-bearing heroes → ``[(kind, key, display)]``.

    A 無陣營 bucket (``MINOR_KEY``) is appended when any data-bearing hero has no
    kingdom.  Sorted by display name.
    """
    present: Set[str] = set()
    has_minor = False
    for m in character_meta.values():
        if not m.get("HasAttrs"):
            continue
        k = m.get("Kingdom")
        if k:
            present.add(k)
        else:
            has_minor = True
    rows = [("kingdom", kid, str(kingdom_names.get(kid, kid)))
            for kid in sorted(present, key=lambda x: str(kingdom_names.get(x, x)))]
    if has_minor:
        rows.append(("kingdom", MINOR_KEY, tr("無陣營")))
    return rows


def clan_rows(character_meta: Dict[str, dict], clan_names: Dict[str, str],
              selected_kingdoms: Iterable[str]) -> List[Tuple[str, str]]:
    """Clans present among data-bearing heroes → ``[(clan_id, display)]``.

    Scoped to *selected_kingdoms* (union); when the selection is empty, every
    clan is listed so the user can filter by clan alone.
    """
    ksel = set(selected_kingdoms or ())
    cset: Set[str] = set()
    for m in character_meta.values():
        if not m.get("HasAttrs"):
            continue
        cl = m.get("Clan")
        if not cl:
            continue
        k = m.get("Kingdom") or ""
        if ksel and not ((k in ksel) or (MINOR_KEY in ksel and not k)):
            continue
        cset.add(cl)
    return [(cid, str(clan_names.get(cid, cid)))
            for cid in sorted(cset, key=lambda x: str(clan_names.get(x, x)))]


def faction_candidates(all_names: Iterable[str], character_meta: Dict[str, dict],
                       selected_kingdoms: Iterable[str],
                       selected_clans: Iterable[str]) -> Set[str]:
    """Names matching the faction (and optional clan) scope.

    No kingdom and no clan selected → everyone (the type acts as a no-op until
    the user narrows it).  Otherwise only data-bearing heroes can match.
    """
    ksel = set(selected_kingdoms or ())
    csel = set(selected_clans or ())
    if not ksel and not csel:
        return set(all_names)
    out: Set[str] = set()
    for n in all_names:
        m = character_meta.get(n, {})
        if not m.get("HasAttrs"):
            continue
        k = m.get("Kingdom") or ""
        cl = m.get("Clan") or ""
        if ksel and not ((k in ksel) or (MINOR_KEY in ksel and not k)):
            continue
        if csel and cl not in csel:
            continue
        out.add(n)
    return out


def ref_candidates(items_sel: Iterable[Tuple[str, str]],
                   presets: Dict[str, list],
                   info_owners: Dict[str, list],
                   secret_owners: Dict[str, list],
                   all_names: Iterable[str]) -> Set[str]:
    """Union of the selected reference items (groups / info / secret owners),
    intersected with the known roster.  Empty selection → everyone."""
    items = list(items_sel)
    all_set = set(all_names)
    if not items:
        return set(all_set)
    out: Set[str] = set()
    for kind, key in items:
        if kind == "group":
            raw = presets.get(key, [])
            if isinstance(raw, list):
                out |= {x for x in raw if isinstance(x, str)}
        elif kind == "info":
            out |= set(info_owners.get(key, []))
        elif kind == "secret":
            out |= set(secret_owners.get(key, []))
    return out & all_set
