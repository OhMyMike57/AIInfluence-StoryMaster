"""自訂對話標籤 — the ``(劇情描述):`` / ``[劇情記憶]:`` style prefixes.

AI Influence itself does not define these; players invent them to feed the AI
context that is not any character's speech — narration, a rumour, a character's
inner voice.  A line written this way is stored exactly like a spoken one, with
the tag sitting where the speaker would be, so the AI reads it as context.

Two kinds of tag:

* **built-in** — three the editor ships (narration / inner voice / rumour).
  They are *localised*: the tag written into the save is in the language the
  editor is running in, because the AI reads the save and a Chinese campaign
  should not suddenly contain English markers.  They cannot be edited or
  deleted (they are the editor's own vocabulary) but can be hidden.
* **custom** — whatever the player adds.  Stored verbatim, never translated;
  a tag is data the AI reads, so translating someone's own wording would
  change what their save says.

Persistence lives in the editor settings (``dialogue_tags``), so it survives
updates like every other preference.
"""
from __future__ import annotations

from typing import Any, Dict, List

from i18n import tr

SETTINGS_KEY = "dialogue_tags"

# Built-in ids → the zh-Hant literal used as the tr() key.  The id is what gets
# persisted (hidden lists, ordering), so renaming a label never orphans state.
BUILTIN_IDS = ("scene", "inner", "rumour")


def builtin_label(tag_id: str) -> str:
    """Localised tag text for a built-in id (literal tr(), never tr(var))."""
    if tag_id == "scene":
        return tr("(劇情描述)")
    if tag_id == "inner":
        return tr("(角色心聲)")
    if tag_id == "rumour":
        return tr("(消息傳聞)")
    return ""


def normalize(raw: Any) -> Dict[str, Any]:
    """Coerce stored settings into ``{"custom": [...], "hidden": [...]}``."""
    custom: List[str] = []
    hidden: List[str] = []
    if isinstance(raw, dict):
        for v in raw.get("custom") or []:
            s = str(v).strip()
            if s and s not in custom:
                custom.append(s)
        for v in raw.get("hidden") or []:
            s = str(v).strip()
            if s and s not in hidden:
                hidden.append(s)
    return {"custom": custom, "hidden": hidden}


def visible_tags(raw: Any) -> List[str]:
    """Tag labels to offer in the 快速設定 menu, built-ins first."""
    cfg = normalize(raw)
    out = [builtin_label(t) for t in BUILTIN_IDS if t not in cfg["hidden"]]
    out += [t for t in cfg["custom"] if t not in cfg["hidden"]]
    return [t for t in out if t]


def all_entries(raw: Any) -> List[Dict[str, Any]]:
    """Every tag for the management window: ``{key, label, builtin, hidden}``.

    *key* is the built-in id or, for a custom tag, its own text — the stable
    handle the hidden list and removal work on.
    """
    cfg = normalize(raw)
    out = [{"key": t, "label": builtin_label(t), "builtin": True,
            "hidden": t in cfg["hidden"]} for t in BUILTIN_IDS]
    out += [{"key": t, "label": t, "builtin": False,
             "hidden": t in cfg["hidden"]} for t in cfg["custom"]]
    return out


def add_custom(raw: Any, label: str) -> Dict[str, Any]:
    """Add a custom tag (no-op when blank or already present)."""
    cfg = normalize(raw)
    s = (label or "").strip()
    if s and s not in cfg["custom"] and s not in [builtin_label(t) for t in BUILTIN_IDS]:
        cfg["custom"].append(s)
    return cfg


def remove_custom(raw: Any, key: str) -> Dict[str, Any]:
    """Remove a custom tag.  Built-ins are the editor's own — hide them instead."""
    cfg = normalize(raw)
    cfg["custom"] = [t for t in cfg["custom"] if t != key]
    cfg["hidden"] = [t for t in cfg["hidden"] if t != key]
    return cfg


def set_hidden(raw: Any, key: str, hidden: bool) -> Dict[str, Any]:
    cfg = normalize(raw)
    if hidden and key not in cfg["hidden"]:
        cfg["hidden"].append(key)
    elif not hidden:
        cfg["hidden"] = [t for t in cfg["hidden"] if t != key]
    return cfg
