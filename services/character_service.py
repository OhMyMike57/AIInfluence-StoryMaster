from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

from services.settings_service import SortKey


def normalize_display_name(stem: str) -> str:
    return stem.split(" (")[0].strip()


# ── Schema bridge: 4.1.0 top-level fields ↔ 5.0.x CounterpartySocial ──────────
#
# In 5.0.x the per-relationship state (trust, interaction count, escalation,
# claimed/real identity…) moved out of the NPC's top-level fields into
# ``CounterpartySocial[<hero_id>]``.  The player-facing record lives under the
# ``main_hero`` key.  Romance likewise moved to ``RomancePartners[main_hero]``.
# These helpers read the new location first and fall back to the old top-level
# field so the tool keeps working with both 4.1.0 and 5.0.x saves.

PLAYER_SID = "main_hero"


def _player_social(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return the player's ``CounterpartySocial`` entry (5.0.x), or ``{}``."""
    cs = d.get("CounterpartySocial")
    if isinstance(cs, dict):
        p = cs.get(PLAYER_SID)
        if isinstance(p, dict):
            return p
    return {}


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def player_trust_level(d: Dict[str, Any]) -> float:
    """5.0.x ``CounterpartySocial.main_hero.trust_level`` → 4.1.0 ``TrustLevel``."""
    p = _player_social(d)
    if "trust_level" in p:
        return _coerce_float(p.get("trust_level"))
    return _coerce_float(d.get("TrustLevel"))


def player_interaction_count(d: Dict[str, Any]) -> float:
    """5.0.x ``CounterpartySocial.main_hero.interaction_count`` → 4.1.0 ``InteractionCount``."""
    p = _player_social(d)
    if "interaction_count" in p:
        return _coerce_float(p.get("interaction_count"))
    return _coerce_float(d.get("InteractionCount"))


def player_romance_level(d: Dict[str, Any]) -> float:
    """5.0.x ``RomancePartners.main_hero.level`` → 4.1.0 ``RomanceLevel``."""
    rp = d.get("RomancePartners")
    if isinstance(rp, dict):
        p = rp.get(PLAYER_SID)
        if isinstance(p, dict) and "level" in p:
            return _coerce_float(p.get("level"))
    return _coerce_float(d.get("RomanceLevel"))


def player_escalation_state(d: Dict[str, Any]) -> str:
    """5.0.x ``CounterpartySocial.main_hero.escalation_state`` → 4.1.0 ``EscalationState``."""
    p = _player_social(d)
    v = p.get("escalation_state") if "escalation_state" in p else d.get("EscalationState")
    return str(v or "")


# ── Writers (mirror the readers above) ────────────────────────────────────────
#
# Each writer sets the 5.0.x nested location (creating the minimal
# ``CounterpartySocial.main_hero`` / ``RomancePartners.main_hero`` entry if it
# does not exist yet) and, when the legacy 4.1.0 top-level field is *already*
# present, mirrors the value there too so both schemas stay consistent.

def _ensure_player_social(d: Dict[str, Any]) -> Dict[str, Any]:
    cs = d.get("CounterpartySocial")
    if not isinstance(cs, dict):
        cs = d["CounterpartySocial"] = {}
    p = cs.get(PLAYER_SID)
    if not isinstance(p, dict):
        p = cs[PLAYER_SID] = {}
    return p


def _ensure_player_romance(d: Dict[str, Any]) -> Dict[str, Any]:
    rp = d.get("RomancePartners")
    if not isinstance(rp, dict):
        rp = d["RomancePartners"] = {}
    p = rp.get(PLAYER_SID)
    if not isinstance(p, dict):
        p = rp[PLAYER_SID] = {}
    return p


def set_player_trust(d: Dict[str, Any], value: float) -> None:
    _ensure_player_social(d)["trust_level"] = value
    if "TrustLevel" in d:
        d["TrustLevel"] = value


def set_player_interaction(d: Dict[str, Any], value: int) -> None:
    _ensure_player_social(d)["interaction_count"] = value
    if "InteractionCount" in d:
        d["InteractionCount"] = value


def set_player_romance(d: Dict[str, Any], value: float) -> None:
    _ensure_player_romance(d)["level"] = value
    if "RomanceLevel" in d:
        d["RomanceLevel"] = value


def is_never_interacted(d: Dict[str, Any]) -> bool:
    """True when the NPC has never had a real dialogue with the player.

    ``LastInteractionTimeDays`` is the reliable signal across both schemas:
    ``None`` (4.1.0 default) or a negative sentinel such as ``-1.0`` (5.0.x)
    means "never interacted".  Note: 5.0.x may set ``interaction_count`` to 1
    on a mere encounter, so interaction count is NOT a safe discriminator.
    """
    li = d.get("LastInteractionTimeDays")
    if li is None:
        return True
    try:
        return float(li) < 0
    except (TypeError, ValueError):
        return True


def _character_is_sick(d: Dict[str, Any]) -> bool:
    """True if the character JSON marks any active disease (5.0.x disease system)."""
    if bool(d.get("IsSick", False)):
        return True
    cur = d.get("CurrentDiseases")
    return isinstance(cur, list) and len(cur) > 0


def build_characters_and_indexes(
    campaign_dir: Path,
    loader: Callable[[Path], Any],
    hero_attrs: Dict[str, Any] | None = None,
    clan_attrs: Dict[str, Any] | None = None,
) -> Tuple[List[Tuple[str, Path]], Dict[str, Dict[str, Any]], Dict[str, List[str]], Dict[str, List[str]]]:
    chars: List[Tuple[str, Path]] = []
    meta: Dict[str, Dict[str, Any]] = {}
    info_owners: Dict[str, set] = {}
    secret_owners: Dict[str, set] = {}
    # Rich per-hero attributes (clan / kingdom / type / age …) exported by the
    # Story Master companion mod, keyed by StringId; joined onto each character
    # below so the list can filter/sort by faction, clan, role and age.
    hero_attrs = hero_attrs or {}
    # Clan → {kingdom, …} map. The clan's kingdom is the authoritative faction
    # link: it is present in every export version (the per-hero kingdom field
    # was only added later, and is null for many notables/wanderers).
    clan_attrs = clan_attrs or {}

    for f in sorted(campaign_dir.glob("*.json")):
        d = loader(f)
        if not (isinstance(d, dict) and "ConversationHistory" in d):
            continue

        name = None
        for k in ("Name", "CharacterName", "NPCName", "DisplayName"):
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                name = v.strip()
                break

        if name and name.lower() not in f.stem.lower():
            display = f"{name} ({f.stem})"
        else:
            display = f.stem

        chars.append((display, f))
        rel = d.get("PlayerRelation")
        rel_val = rel.get("Value") if isinstance(rel, dict) else 0
        sid = str(d.get("StringId") or f.stem)
        a = hero_attrs.get(sid) if isinstance(hero_attrs.get(sid), dict) else {}
        age_raw = a.get("age")
        clan_id = a.get("clan")
        # Faction = the clan's kingdom (authoritative); fall back to the hero's
        # own kingdom field for clanless heroes / older clan exports.
        kingdom = None
        if clan_id and isinstance(clan_attrs.get(clan_id), dict):
            kingdom = clan_attrs[clan_id].get("kingdom")
        if not kingdom:
            kingdom = a.get("kingdom")
        meta[display] = {
            "Name": name or normalize_display_name(f.stem),
            "StringId": sid,
            "IsInPlayerParty": bool(d.get("IsInPlayerParty", False)),
            "RomanceLevel": player_romance_level(d),
            "TrustLevel": player_trust_level(d),
            "RelationValue": float(rel_val or 0),
            "InteractionCount": player_interaction_count(d),
            "NeverInteracted": is_never_interacted(d),
            # Joined companion-mod attributes (None when no export / no match).
            "HasAttrs": bool(a),
            "Clan": clan_id,
            "Kingdom": kingdom,
            "MapFaction": a.get("map_faction"),
            "Age": int(age_raw) if isinstance(age_raw, (int, float)) else None,
            "IsLord": bool(a.get("is_lord")),
            "IsWanderer": bool(a.get("is_wanderer")),
            "IsNotable": bool(a.get("is_notable")),
            "IsClanLeader": bool(a.get("is_clan_leader")),
            "IsSick": _character_is_sick(d),
        }

        for info_id in d.get("KnownInfo", []) if isinstance(d.get("KnownInfo"), list) else []:
            key = str(info_id).strip()
            if key:
                info_owners.setdefault(key, set()).add(display)
        for secret_id in d.get("KnownSecrets", []) if isinstance(d.get("KnownSecrets"), list) else []:
            key = str(secret_id).strip()
            if key:
                secret_owners.setdefault(key, set()).add(display)

    return chars, meta, {k: sorted(v) for k, v in info_owners.items()}, {k: sorted(v) for k, v in secret_owners.items()}


def character_sort_key(display: str, mode: str, meta: Dict[str, Dict[str, Any]], favorites: set):
    """Return a sort tuple for a character display string under the given mode."""
    m = meta.get(display, {})
    name = str(m.get("Name") or normalize_display_name(display)).lower()
    string_id = str(m.get("StringId") or "").lower()
    if mode == SortKey.ID:
        return (string_id, name)
    if mode == SortKey.FAVORITES:
        return (display not in favorites, name)
    if mode == SortKey.PARTY:
        return (not bool(m.get("IsInPlayerParty", False)), name)
    if mode == SortKey.ROMANCE:
        return (float(m.get("RomanceLevel", 0)), name)
    if mode == SortKey.TRUST:
        return (float(m.get("TrustLevel", 0)), name)
    if mode == SortKey.RELATION:
        return (float(m.get("RelationValue", 0)), name)
    if mode == SortKey.INTERACTION:
        return (float(m.get("InteractionCount", 0)), name)
    if mode == SortKey.SICK:
        # Sick characters first; within each group, by name.
        return (not bool(m.get("IsSick", False)), name)
    if mode == SortKey.AGE:
        # Unknown age (no companion-mod data) sorts last.
        age = m.get("Age")
        return (age is None, float(age) if isinstance(age, (int, float)) else 0.0, name)
    return (name, string_id)


def sorted_displays(values: Sequence[str], mode: str, reverse: bool, meta: Dict[str, Dict[str, Any]], favorites: set) -> List[str]:
    """Sort character display strings by mode, applying default-descending for numeric modes."""
    default_desc = mode in (SortKey.ROMANCE, SortKey.TRUST, SortKey.RELATION, SortKey.INTERACTION)
    final_reverse = (not reverse) if default_desc else reverse
    return sorted(values, key=lambda d: character_sort_key(d, mode, meta, favorites), reverse=final_reverse)


def display_label(display: str, meta: Dict[str, Dict[str, Any]], favorites: set, star: bool = False) -> str:
    sid = str(meta.get(display, {}).get("StringId") or "").strip()
    label = f"{display} [{sid}]" if sid and sid not in display else display
    if star and display in favorites:
        return f"★ {label}"
    return label


def is_visible_character(
    display: str,
    term: str,
    meta: Dict[str, Dict[str, Any]],
    exclude_uninteracted: bool,
    party_only: bool = False,
    type_filters: Dict[str, bool] | None = None,
    faction: str | None = None,
    clan: str | None = None,
) -> bool:
    """Return True if this character should appear in the list under the given filters.

    Filters applied in order (fastest-reject first):
      1. party_only  — hide anyone not in the player's party
      2. exclude_uninteracted — hide characters that never had a real dialogue
         (see :func:`is_never_interacted`)
      3. type_filters — subtractive role toggles (lord/wanderer/notable/leader):
         a character is hidden when it *is* a role the user unchecked;
         uncategorised characters are unaffected
      4. faction / clan — two-level faction → clan narrowing (companion-mod data);
         ``faction == "__minor__"`` means clanless / no-kingdom (在野)
      5. term        — substring search across display name, Name field, and StringId
    """
    m = meta.get(display, {})
    if party_only and not bool(m.get("IsInPlayerParty", False)):
        return False
    if exclude_uninteracted and m.get("NeverInteracted", False):
        return False
    if type_filters:
        if not type_filters.get("lord", True) and m.get("IsLord"):
            return False
        if not type_filters.get("wanderer", True) and m.get("IsWanderer"):
            return False
        if not type_filters.get("notable", True) and m.get("IsNotable"):
            return False
        if not type_filters.get("leader", True) and m.get("IsClanLeader"):
            return False
    if faction:
        # Characters without companion-mod data have no known faction, so any
        # specific faction view (including 在野) excludes them.
        if not m.get("HasAttrs"):
            return False
        ck = m.get("Kingdom")
        if faction == "__minor__":
            if ck:  # has a kingdom → not 在野
                return False
        elif ck != faction:
            return False
    if clan and m.get("Clan") != clan:
        return False
    if not term:
        return True
    values = [display.lower(), str(m.get("Name", "")).lower(), str(m.get("StringId", "")).lower()]
    return any(term in v for v in values)


# ── Character reset / inheritance ─────────────────────────────────────────────
#
# "重置角色" rebuilds a character JSON from a pristine template, carrying only the
# fields the user chooses to preserve (plus identity / creation-intrinsic fields).
# Because the output is built from the template — not the input — any legacy
# 4.1.0-only fields are dropped, so this doubles as a format upgrader and a
# cross-campaign inheritance tool.
#
# The template's key set was diffed against real 6.0.2 save data
# (scripts/reset_character_check): every key it writes is present in 6.0 saves,
# and 6.0 introduces no character-file key the template lacks — so the reset
# output loads cleanly in AI Influence 6.0.

# Fields always carried from the source (intrinsic identity / mod-assigned at
# creation).  Not user-toggleable — resetting them would corrupt the character.
RESET_ALWAYS_KEEP = (
    "Name", "StringId", "Gender", "InformationAccessLevel", "player_bind_string_id",
)

# Preservable fields shown as checkboxes.  Each: (key, 中文說明, 預設保留, 分組).
RESET_PRESERVABLE_FIELDS = [
    # 核心存檔（建議保留）— the 7 defaults
    ("CharacterDescription",   "角色描述（人物設定文字）",                     True,  "核心存檔（建議保留）"),  # noqa: cjk
    ("ConversationHistory",    "對話歷史（與你的完整對話記錄）",               True,  "核心存檔（建議保留）"),  # noqa: cjk
    ("AIGeneratedPersonality", "AI 生成個性",                                  True,  "核心存檔（建議保留）"),  # noqa: cjk
    ("AIGeneratedBackstory",   "AI 生成背景故事",                              True,  "核心存檔（建議保留）"),  # noqa: cjk
    ("AIGeneratedSpeechQuirks","AI 生成說話習慣",                              True,  "核心存檔（建議保留）"),  # noqa: cjk
    ("AIGeneratedCognitiveStyle","AI 生成認知風格（思考方式／對幽默欺騙記仇的反應）", True, "核心存檔（建議保留）"),  # noqa: cjk
    ("Memories",               "長期記憶（記憶之書條目 Memories[]）",            True,  "核心存檔（建議保留）"),  # noqa: cjk
    ("KnownSecrets",           "已知秘密（world_secrets 的 id 清單）",          True,  "核心存檔（建議保留）"),  # noqa: cjk
    ("KnownInfo",              "已知資訊（world_info 的 id 清單）",             True,  "核心存檔（建議保留）"),  # noqa: cjk
    # 知識與關係
    ("KnowledgeGenerated",     "知識生成旗標（true＝鎖定手改的秘密/資訊，不再自動擲骰）", False, "知識與關係"),  # noqa: cjk
    ("PlayerRelation",         "與玩家的關係好感值",                           False, "知識與關係"),  # noqa: cjk
    ("CounterpartySocial",     "社交狀態（信任、互動次數、身分識別、對各 NPC 關係）",   False, "知識與關係"),  # noqa: cjk
    ("RomancePartners",        "戀愛／親密關係狀態",                           False, "知識與關係"),  # noqa: cjk
    ("IsRomanceEligible",      "是否可進入戀愛",                               False, "知識與關係"),  # noqa: cjk
    # 記錄與情境
    ("DialogueObservations",   "對話觀察記錄（旁聽／分析）",                    False, "記錄與情境"),  # noqa: cjk
    ("ProcessedDialogueObservationHashes", "對話觀察去重快取",                 False, "記錄與情境"),  # noqa: cjk
    ("DynamicEvents",          "已知動態事件 id 清單",                         False, "記錄與情境"),  # noqa: cjk
    ("RecentEvents",           "近期事件（戰役相關，如攻城／死亡通報）",         False, "記錄與情境"),  # noqa: cjk
    ("VisitedSettlements",     "造訪過的定居點記錄",                           False, "記錄與情境"),  # noqa: cjk
    ("AdditionalContext",      "額外背景補充（手動／AI 追加說明）",             False, "記錄與情境"),  # noqa: cjk
    ("AssignedTTSVoice",       "指派的 TTS 語音",                              False, "記錄與情境"),  # noqa: cjk
]


def pristine_character_template(existing: Dict[str, Any]) -> Dict[str, Any]:
    """Return a fresh character JSON with default/empty values.

    Identity & creation-intrinsic fields (see :data:`RESET_ALWAYS_KEEP`) are
    carried from *existing*; every other field takes the pristine default — the
    state a freshly created, never-interacted NPC has.  The key set is a superset
    of what 6.0.2 writes (verified against sample saves), so the output loads
    cleanly in AI Influence 6.0.  Field order follows the in-game layout for
    readable diffs.
    """
    e = existing if isinstance(existing, dict) else {}
    return {
        "Name":                              e.get("Name", ""),
        "StringId":                          e.get("StringId", ""),
        "Gender":                            e.get("Gender", "male"),
        "AssignedTTSVoice":                  "",
        "LastTTSPlayedText":                 "",
        "LastTTSInstructions":               "",
        "LastDialogueSceneId":               None,
        "LastDynamicResponseUtteranceId":    None,
        "IsInPlayerParty":                   False,
        "IsWithPlayer":                      False,
        "player_bind_string_id":             e.get("player_bind_string_id", "main_hero"),
        "ConversationHistory":               [],
        "LastMemoryProcessedIndex":          0,
        "DialogueObservations":              [],
        "Memories":                          [],
        "WarStatus":                         None,
        "PlayerRelation":                    {"Value": 0, "Description": "neutral"},
        "CurrentTask":                       "",
        "RecentEvents":                      [],
        "EmotionalState":                    {"Mood": "calm", "Reason": "no specific reason"},
        "LocationType":                      "",
        "TimeContext":                       None,
        "PlayerForces":                      {"PartySize": 0, "WoundedPercentage": 0.0, "HasArmy": False, "TroopDetails": []},
        "NPCForces":                         {"PartySize": 0, "WoundedPercentage": 0.0, "HasArmy": False, "ArmyDetails": None, "TroopDetails": []},
        "Quirks":                            [],
        "InformationAccessLevel":            e.get("InformationAccessLevel", "medium"),
        "CombatResponse":                    None,
        "IsSurrendering":                    False,
        "IsPlayerSurrendering":              False,
        "MarriageResponse":                  None,
        "PendingDeath":                      None,
        "PendingSettlementCombat":           None,
        "SettlementCombatResponse":          None,
        "PendingAttackTargetHeroId":         None,
        "RoleplayDeathReason":               None,
        "KillerStringId":                    None,
        "LastDynamicResponse":               None,
        "PendingAIResponse":                 None,
        "RequestDialogueSceneImage":         False,
        "PendingActionCommandsAfterMission": None,
        "PendingRelationChanges":            None,
        "PendingLiePenalty":                 None,
        "PendingWorkshopSale":               None,
        "PendingMoneyTransfer":              None,
        "PendingItemTransfers":              None,
        "PendingIntimacyNotification":       False,
        "PendingConceptionMotherName":       None,
        "CharacterDescription":              "",
        "AIGeneratedPersonality":            None,
        "AIGeneratedBackstory":              None,
        "AIGeneratedSpeechQuirks":           None,
        "AIGeneratedCognitiveStyle":         None,
        "KnownSecrets":                      [],
        "KnownInfo":                         [],
        "ClanTierRecognitionChecked":        False,
        "KnowledgeGenerated":                False,
        "KnowledgeGenerationDeferred":       False,
        "CounterpartySocial":                {},
        "RomancePartners":                   {},
        "IsRomanceEligible":                 False,
        "SettlementCombatInfo":              None,
        "DynamicEvents":                     [],
        "IsSick":                            False,
        "CurrentDiseases":                   [],
        "DiseaseProgress":                   0.0,
        "IsTreated":                         False,
        "ProcessedDialogueObservationHashes": [],
        "LastSeenFriends":                   {},
        "IsNPCInitiatedConversation":        False,
        "IsHostileInitiative":               False,
        "AllowsLettersFromNPC":              False,
        "AdditionalContext":                 "",
        "ActiveAIQuests":                    [],
        "IncomingAIQuests":                  [],
        "CompletedQuestHistory":             [],
        "BattleCommandHistory":              [],
        "LastInteractionTimeDays":           -1.0,
        "VisitedSettlements":                [],
        "LastAIResponseSummary":             None,
        "LastAIResponseJson":                None,
    }


def reset_character_json(existing: Dict[str, Any], preserve_keys) -> Dict[str, Any]:
    """Return a pristine template with the chosen fields carried over.

    *preserve_keys* is an iterable of keys from :data:`RESET_PRESERVABLE_FIELDS`
    the user opted to keep; each is copied from *existing* when present.  Identity
    / creation-intrinsic fields are always carried via the template.  Any legacy
    field not in the template is dropped — yielding clean, 6.0-compatible output.
    """
    out = pristine_character_template(existing)
    e = existing if isinstance(existing, dict) else {}
    valid = {row[0] for row in RESET_PRESERVABLE_FIELDS}
    for k in preserve_keys:
        if k in valid and k in e:
            out[k] = e[k]
    # LastMemoryProcessedIndex is an internal pointer into ConversationHistory,
    # not something to offer as its own checkbox: it has to follow the history it
    # points at.  Kept history keeps its pointer (clamped, in case the history was
    # also trimmed); discarded history leaves the template's 0.
    if "ConversationHistory" in preserve_keys and "ConversationHistory" in e:
        try:
            idx = int(e.get("LastMemoryProcessedIndex") or 0)
        except (TypeError, ValueError):
            idx = 0
        history = out.get("ConversationHistory")
        out["LastMemoryProcessedIndex"] = max(0, min(idx, len(history) if isinstance(history, list) else 0))
    return out
