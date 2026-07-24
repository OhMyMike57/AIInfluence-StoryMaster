"""Shared i18n display-label maps for AI Influence data values.

One canonical place for translating the mod's English data tokens so the same
term is used everywhere (the 訊息與秘密 card, the dynamic-events detail/editor,
the recent-events viewer, the summary card).  Each map is a function returning
``{token: tr("中文")}`` rebuilt per call so runtime language switches apply, and
the ``tr("…")`` literals are picked up by the i18n coverage checker.

Unknown tokens fall back to the raw value (moods are AI free-form; recent-event
types are a mostly-fixed set but new ones degrade gracefully).
"""
from __future__ import annotations

from typing import Any, Dict

from i18n import tr
from services.dynamic_event_service import normalize_type


# ── Applicable-NPC categories (world info/secret + dynamic events) ────────────
def applicable_npc_labels() -> Dict[str, str]:
    return {
        "all":              tr("全部"),
        "lords":            tr("貴族"),
        "companions":       tr("夥伴"),
        "wanderers":        tr("浪人"),
        "notables":         tr("顯要"),
        "faction_leaders":  tr("陣營領袖"),
        "village_notables": tr("村莊要人"),
        "rural_notables":   tr("鄉村顯要"),
        "merchants":        tr("商人"),
        "artisans":         tr("工匠"),
        "preachers":        tr("傳教士"),
        "headmen":          tr("村莊頭人"),
        "gang_leaders":     tr("幫派頭目"),
        "gangsters":        tr("幫派份子"),
        "mercenaries":      tr("傭兵"),
    }


def applicable_npc_label(tok: Any) -> str:
    return applicable_npc_labels().get(str(tok), str(tok))


# ── Dynamic-event types ───────────────────────────────────────────────────────
def dynamic_event_type_labels() -> Dict[str, str]:
    return {
        "military":        tr("軍事"),
        "political":       tr("政治"),
        "economic":        tr("經濟"),
        "social":          tr("社會"),
        "mysterious":      tr("神秘"),
        "news":            tr("新聞"),
        "local":           tr("地方"),
        "rumor":           tr("謠言"),
        "diseaseoutbreak": tr("疫情爆發"),
        "other":           tr("其它"),
    }


def dynamic_event_type_label(t: Any) -> str:
    key = normalize_type(t)
    return dynamic_event_type_labels().get(key, str(t))


# ── RecentEvents Type (mostly-fixed set; unknowns fall back to raw) ───────────
def recent_event_labels() -> Dict[str, str]:
    return {
        "Battle":            tr("戰鬥"),
        "PrisonerTaken":     tr("擒獲俘虜"),
        "PrisonerReleased":  tr("俘虜獲釋"),
        "Tournament":        tr("競技比武"),
        "Law":               tr("頒布法律"),
        "SettlementCapture": tr("攻佔定居點"),
        "KingdomLeadership": tr("王國領導更迭"),
        "WarDeclared":       tr("宣戰"),
        "PeaceMade":         tr("締結和平"),
        "HeroKilled":        tr("英雄陣亡"),
        "Marriage":          tr("聯姻"),
        "ClanDestroyed":     tr("氏族覆滅"),
        "VillageRaided":     tr("村莊遭劫"),
        "CaravanAttacked":   tr("商隊遇襲"),
        "Default":           tr("事件"),
    }


def recent_event_label(t: Any) -> str:
    return recent_event_labels().get(str(t), str(t))


# ── EmotionalState.Mood (AI free-form; curated common set + raw fallback) ─────
def mood_labels() -> Dict[str, str]:
    return {
        # observed in real 5.0.7 saves
        "calm":         tr("平靜"),
        "proud":        tr("自豪"),
        "competitive":  tr("好勝"),
        "victorious":   tr("勝利"),
        "joyful":       tr("喜悅"),
        "benevolent":   tr("仁慈"),
        "defeated":     tr("挫敗"),
        "relieved":     tr("寬慰"),
        "demoralized":  tr("士氣低落"),
        # common additions
        "happy":        tr("開心"),
        "sad":          tr("悲傷"),
        "angry":        tr("憤怒"),
        "furious":      tr("暴怒"),
        "fearful":      tr("恐懼"),
        "anxious":      tr("焦慮"),
        "nervous":      tr("緊張"),
        "worried":      tr("擔憂"),
        "content":      tr("滿足"),
        "hopeful":      tr("充滿希望"),
        "confident":    tr("自信"),
        "suspicious":   tr("疑心"),
        "curious":      tr("好奇"),
        "excited":      tr("興奮"),
        "bored":        tr("無聊"),
        "grateful":     tr("感激"),
        "jealous":      tr("嫉妒"),
        "ashamed":      tr("羞愧"),
        "melancholic":  tr("憂鬱"),
        "neutral":      tr("平淡"),
        "determined":   tr("堅定"),
        "frustrated":   tr("沮喪"),
    }


def mood_label(m: Any) -> str:
    return mood_labels().get(str(m).strip().lower(), str(m))
