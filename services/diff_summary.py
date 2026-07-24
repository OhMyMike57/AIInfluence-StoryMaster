"""Readable summarisation of a staged field change for the review dialog (v0.37.4).

The staging diff yields raw ``(field, old, new)`` triples where a value may be a
scalar, a long text blob, a list, or a nested dict.  Dumping those verbatim gave
opaque rows like ``ConversationHistory [8項]→[8項]（＋1／−1）`` or a full persona
essay.  This module turns each change into a compact, human-readable summary:

* short scalars / strings  → keep ``old → new`` (the new value coloured green)
* long strings            → an action only: ``✏ 編輯文本（1024 → 1187 字）``
* lists                   → a paired add/remove/edit heuristic: editing one line
                             of an 8-line history reads as ``✏ 編輯 1 行`` (not
                             ``＋1／−1``)
* the social nested dicts → the individual scalar changes (``信任 0.1 → 0.5``)
* other dicts             → 設定 / 清空 / 修改（子鍵…）

Pure functions, headless-testable.  ``summarize_change`` returns a list of
``(text, tag)`` segments; the renderer inserts each with the matching Text tag
(``chg`` grey, ``new`` green, ``muted`` grey-small).
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, List, Tuple

from i18n import tr

Segment = Tuple[str, str]

_LONG = 24   # strings longer than this are summarised rather than shown inline

# List items in these fields are conversation「行」; every other list is「項」.
_LINE_FIELDS = {"ConversationHistory"}

# Nested dicts whose meaningful scalars should be surfaced individually rather
# than collapsed to「修改」.  Each entry: field → [(dotted-path, zh-label)].
_SOCIAL_SCALARS = {           # labels are tr()-translated at use (summarize_social)
    "CounterpartySocial": [
        ("main_hero.trust_level", "信任"),            # noqa: cjk
        ("main_hero.interaction_count", "互動次數"),  # noqa: cjk
        ("main_hero.escalation_state", "情緒升降"),   # noqa: cjk
    ],
    "RomancePartners": [("main_hero.level", "浪漫")],  # noqa: cjk
    "PlayerRelation": [("Value", "關係")],             # noqa: cjk
}


def field_label(key: str) -> str:
    """Chinese label for a raw JSON field key; unknown keys pass through as-is.

    The renderer shows ``field_label(key)`` and, when it differs from *key*,
    appends the raw key in a muted tag so power users can still cross-reference.
    """
    labels = {
        "ConversationHistory":     tr("對話"),
        "AIGeneratedPersonality":  tr("人設"),
        "RecentAIResponses":       tr("AI 回應"),
        "KnownInfo":               tr("訊息"),
        "KnownSecrets":            tr("秘密"),
        "DynamicEvents":           tr("事件引用"),
        "EmotionalState":          tr("情緒狀態"),
        "CounterpartySocial":      tr("社交數值"),
        "RomancePartners":         tr("浪漫"),
        "PlayerRelation":          tr("關係"),
        "LastInteractionTimeDays": tr("最後互動"),
        "IsRomanceEligible":       tr("允許浪漫"),
        "IsSick":                  tr("是否生病"),
        "CurrentDiseases":         tr("目前疾病"),
        "DiseaseProgress":         tr("疾病進程"),
        "TrustLevel":              tr("信任"),
        "RomanceLevel":            tr("浪漫"),
        "InteractionCount":        tr("互動次數"),
    }
    return labels.get(key, key)


# ── value formatting ─────────────────────────────────────────────────────────
def _val(v: Any) -> str:
    """Compact single-line preview of a scalar / short value."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v.replace("\n", "⏎")
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)


def _is_long(v: Any) -> bool:
    return isinstance(v, str) and len(v) > _LONG


def _get_path(d: Any, dotted: str) -> Any:
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


# ── per-type summarisers ─────────────────────────────────────────────────────
def _summarize_text(old: Any, new: Any) -> List[Segment]:
    lo = len(old) if isinstance(old, str) else 0
    ln = len(new) if isinstance(new, str) else 0
    unit = tr("字")
    if not lo and ln:
        return [(tr("➕ 新增文本"), "new"), (f"（{ln} {unit}）", "muted")]
    if lo and not ln:
        return [(tr("🗑 清空文本"), "chg"), (f"（{lo} {unit} → 0）", "muted")]
    return [(tr("✏ 編輯文本"), "new"), (f"（{lo} → {ln} {unit}）", "muted")]


def _summarize_list(field: str, old: list, new: list) -> List[Segment]:
    def keys(arr):
        out = []
        for x in arr:
            out.append(x if isinstance(x, str)
                       else json.dumps(x, ensure_ascii=False, sort_keys=True))
        return out

    co, cn = Counter(keys(old)), Counter(keys(new))
    added   = sum((cn - co).values())
    removed = sum((co - cn).values())
    edits   = min(added, removed)
    net_add = added - edits
    net_rem = removed - edits
    unit = tr("行") if field in _LINE_FIELDS else tr("項")

    parts: List[Segment] = []
    if edits:
        parts.append((f"{tr('✏ 編輯')} {edits} {unit}", "new"))
    if net_add:
        parts.append((f"{tr('➕ 新增')} {net_add} {unit}", "new"))
    if net_rem:
        parts.append((f"{tr('🗑 刪除')} {net_rem} {unit}", "chg"))
    if not parts:
        return [(tr("順序或內容微調"), "muted")]

    segs: List[Segment] = []
    for i, seg in enumerate(parts):
        if i:
            segs.append(("、", "muted"))
        segs.append(seg)
    return segs


def _summarize_social(field: str, old: Any, new: Any) -> List[Segment]:
    segs: List[Segment] = []
    for path, label in _SOCIAL_SCALARS[field]:
        ov, nv = _get_path(old, path), _get_path(new, path)
        if ov != nv:
            if segs:
                segs.append(("、", "muted"))
            segs.append((f"{tr(label)} {_val(ov)} → ", "chg"))
            segs.append((_val(nv), "new"))
    return segs or [(tr("修改"), "new")]


def _summarize_dict(old: Any, new: Any) -> List[Segment]:
    o = old if isinstance(old, dict) else None
    n = new if isinstance(new, dict) else None
    if not o and n:
        return [(tr("設定"), "new")]
    if o and not n:
        return [(tr("清空"), "chg")]
    o, n = o or {}, n or {}
    changed = [k for k in set(list(o.keys()) + list(n.keys())) if o.get(k) != n.get(k)]
    if 0 < len(changed) <= 3:
        return [(tr("修改") + "：" + "、".join(changed), "new")]
    return [(tr("修改") + f" {len(changed)} {tr('項')}", "new")]


def summarize_change(field: str, old: Any, new: Any) -> List[Segment]:
    """Return ``[(text, tag)]`` segments summarising *old*→*new* for *field*."""
    if field in _SOCIAL_SCALARS and (isinstance(old, dict) or isinstance(new, dict)):
        return _summarize_social(field, old, new)
    if isinstance(old, list) or isinstance(new, list):
        return _summarize_list(field,
                               old if isinstance(old, list) else [],
                               new if isinstance(new, list) else [])
    if isinstance(old, dict) or isinstance(new, dict):
        return _summarize_dict(old, new)
    if _is_long(old) or _is_long(new):
        return _summarize_text(old, new)
    return [(f"{_val(old)}  →  ", "chg"), (_val(new), "new")]
