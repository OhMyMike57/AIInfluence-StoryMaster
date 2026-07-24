"""Pure-function service layer for the disease system.

All functions are side-effect-free (no I/O) and easy to test.
Callers are responsible for reading/writing JSON files.

Disease scope handled in Phase 1 (this module):
  - Hero personal infections: target_type == 0
  - Party and settlement infections are NOT managed here.

disease_instances.json schema (per entry):
  disease_id, disease_name, target_id, target_type,
  infected_at, disease_progress, initial_progress,
  is_recovered, is_dead, is_treated, treatment_effectiveness,
  treatment_quality_bonus, infected_troop_count, total_troop_count,
  troop_tier_distribution, post_treatment_recovery_rate,
  post_treatment_days_remaining, has_prevention_effect,
  prevention_strength, has_used_cheat_death

Character JSON disease fields synced by this service:
  IsSick, IsTreated, CurrentDiseases (list), DiseaseProgress (float)
"""
from __future__ import annotations

from i18n import tr

import uuid
from typing import Any, Dict, List, Optional


# ── Query helpers ─────────────────────────────────────────────────────────────

def hero_instances(all_instances: List[dict]) -> List[dict]:
    """Return only instances with target_type == 0 (hero personal infection)."""
    return [x for x in all_instances if x.get("target_type") == 0]


def instances_for_hero(all_instances: List[dict], hero_string_id: str) -> List[dict]:
    """Return all hero instances for a specific character string ID."""
    return [
        x for x in hero_instances(all_instances)
        if x.get("target_id") == hero_string_id
    ]


def disease_definition(definitions: List[dict], disease_id: str) -> Optional[dict]:
    """Return the disease definition dict for *disease_id*, or None."""
    return next((d for d in definitions if d.get("id") == disease_id), None)


def all_disease_ids(definitions: List[dict]) -> List[str]:
    """Return a list of all disease IDs."""
    return [d.get("id", "") for d in definitions if d.get("id")]


# ── Mutation helpers (return new list, never mutate in place) ─────────────────

def remove_hero_disease(
    instances: List[dict], hero_string_id: str, disease_id: str
) -> List[dict]:
    """Return a new instances list with the matching hero infection removed.

    Does NOT update the character JSON — call sync_character_diseases afterwards.
    """
    return [
        x for x in instances
        if not (
            x.get("target_type") == 0
            and x.get("target_id") == hero_string_id
            and x.get("disease_id") == disease_id
        )
    ]


def remove_disease_instance(
    instances: List[dict], target_id: str, disease_id: str
) -> List[dict]:
    """Return a new instances list with the (target_id, disease_id) match removed.

    Unlike :func:`remove_hero_disease` this does NOT filter on ``target_type``,
    so it removes both hero (0) and party (1 / 2) instances.  Hero and party
    target_id namespaces don't overlap in practice (party ids carry a
    ``_party_<n>`` suffix), so this is safe.

    Does NOT update any character JSON — caller is responsible for that
    when removing hero instances.
    """
    return [
        x for x in instances
        if not (
            x.get("target_id") == target_id
            and x.get("disease_id") == disease_id
        )
    ]


def instances_for_disease(
    all_instances: List[dict], disease_id: str
) -> List[dict]:
    """Return every instance (hero + party) infected with *disease_id*."""
    return [x for x in all_instances if x.get("disease_id") == disease_id]


def remove_all_instances_of_disease(
    instances: List[dict], disease_id: str
) -> List[dict]:
    """Return a new list with every instance of *disease_id* dropped."""
    return [x for x in instances if x.get("disease_id") != disease_id]


def remove_disease_definition(
    definitions: List[dict], disease_id: str
) -> List[dict]:
    """Return a new definitions list with the matching disease entry removed."""
    return [d for d in definitions if d.get("id") != disease_id]


def assign_hero_disease(
    instances: List[dict],
    hero_string_id: str,
    disease_def: dict,
    current_campaign_days: float = 0.0,
) -> List[dict]:
    """Return a new instances list with a fresh hero infection appended.

    Does NOT update the character JSON — call sync_character_diseases afterwards.
    """
    new_instance: Dict[str, Any] = {
        "disease_id":                    disease_def.get("id", str(uuid.uuid4())),
        "disease_name":                  disease_def.get("name", ""),
        "target_id":                     hero_string_id,
        "target_type":                   0,
        "infected_at":                   current_campaign_days,
        "disease_progress":              0.0,
        "initial_progress":              0.0,
        "is_recovered":                  False,
        "is_dead":                       False,
        "is_treated":                    False,
        "treatment_effectiveness":       1.0,
        "treatment_quality_bonus":       1.0,
        "infected_troop_count":          0,
        "total_troop_count":             0,
        "troop_tier_distribution":       {},
        "post_treatment_recovery_rate":  0.0,
        "post_treatment_days_remaining": 0,
        "has_prevention_effect":         False,
        "prevention_strength":           0,
        "has_used_cheat_death":          False,
    }
    return list(instances) + [new_instance]


# ── Character JSON synchronisation ───────────────────────────────────────────

def sync_character_diseases(
    character_data: dict,
    instances_for_hero_: List[dict],
    definitions: List[dict],
) -> dict:
    """Rewrite a character dict's disease fields to match the given instances.

    Fields updated in place on the dict (returned for convenience):
      IsSick          — True if any active (not recovered, not dead) instance
      IsTreated       — True if any active instance has is_treated == True
      DiseaseProgress — max disease_progress of active instances (or 0.0)
      CurrentDiseases — list of {name, severity, progress, is_treated,
                                  days_infected, severity_description}

    Does NOT write the file — caller is responsible for that.
    """
    active = [
        x for x in instances_for_hero_
        if not x.get("is_recovered") and not x.get("is_dead")
    ]

    character_data["IsSick"]    = bool(active)
    character_data["IsTreated"] = any(x.get("is_treated") for x in active)
    character_data["DiseaseProgress"] = (
        max((x.get("disease_progress", 0.0) for x in active), default=0.0)
    )

    current_diseases = []
    for inst in active:
        did   = inst.get("disease_id", "")
        defn  = disease_definition(definitions, did)
        sev   = defn.get("severity", 1) if defn else 1
        current_diseases.append({
            "name":                 inst.get("disease_name", ""),
            "severity":             sev,
            "progress":             inst.get("disease_progress", 0.0),
            "is_treated":           bool(inst.get("is_treated")),
            "days_infected":        0.0,   # not tracked per-instance in current schema
            "severity_description": _severity_label(sev),
        })
    character_data["CurrentDiseases"] = current_diseases
    return character_data


def _severity_label(severity: int) -> str:
    """Human-readable severity description."""
    return {1: tr("輕度"), 2: tr("中度"), 3: tr("重度")}.get(
        severity, tr("嚴重度 {n}").format(n=severity))


# ── Validity check ─────────────────────────────────────────────────────────────

def invalid_hero_instances(
    all_instances: List[dict], definitions: List[dict]
) -> List[dict]:
    """Return hero instances whose disease_id doesn't exist in definitions.

    Direction 1 (forward orphan): disease_instances.json → diseases catalog.
    """
    valid_ids = set(all_disease_ids(definitions))
    return [
        x for x in hero_instances(all_instances)
        if x.get("disease_id", "") not in valid_ids
    ]


def stale_disease_characters(
    all_instances: List[dict],
    character_iter,
) -> List[tuple]:
    """Return (display_name, path, sid) tuples where a character's JSON claims
    sickness but no active hero instance exists in disease_instances.json.

    Direction 2 (reverse orphan): character JSON IsSick / CurrentDiseases
    → disease_instances.json.

    ``character_iter`` must yield ``(display_name, path, char_data_dict)``
    triples. Only characters whose StringId is non-empty are checked.
    An instance is considered *active* if ``is_recovered`` and ``is_dead``
    are both falsy.
    """
    # Build a set of hero StringIds that have at least one active instance.
    heroes_with_instance: set = set()
    for inst in hero_instances(all_instances):
        if not inst.get("is_recovered") and not inst.get("is_dead"):
            sid = inst.get("target_id", "")
            if sid:
                heroes_with_instance.add(sid)

    result = []
    for display, path, char_data in character_iter:
        if not isinstance(char_data, dict):
            continue
        is_sick = bool(char_data.get("IsSick", False))
        current_diseases = char_data.get("CurrentDiseases") or []
        disease_progress = float(char_data.get("DiseaseProgress") or 0)
        # Only flag characters that claim to be sick in at least one field.
        if not is_sick and not current_diseases and disease_progress == 0:
            continue
        sid = char_data.get("StringId", "")
        if not sid:
            continue
        if sid not in heroes_with_instance:
            result.append((display, path, sid))
    return result
